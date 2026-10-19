#!/usr/bin/env python3
"""SMT Recomp Launcher: build and play PlayStation games natively with PSXRecomp.

Give it a PS1 disc image (.cue or .bin) and it scaffolds a PSXRecomp project, adds the
in-game menu (F1: save states, key bindings, controls, guide), recompiles the game's
code to C and compiles a native program. Built games are listed so you can start them
with one click.

    python3 smt_launcher.py                      # opens the launcher in your browser
    python3 smt_launcher.py list
    python3 smt_launcher.py add DISC.cue [--name NAME]
    python3 smt_launcher.py build NAME
    python3 smt_launcher.py play NAME

The library lives in ~/SMT-Recomp (or $SMT_RECOMP_HOME / --library). Only the Python
standard library is used. Needs git, cmake, ninja, pkg-config and a C/C++ compiler
(macOS: Xcode command-line tools + Homebrew).

Only the game that was tested end to end is Shin Megami Tensei if... (SLPM-87153).
Other discs go through the same PSXRecomp pipeline, but whether a given game boots
and plays correctly depends on PSXRecomp, not on this launcher.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import struct
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
VERSION = '1.0'

# Framework versions this launcher was tested with.
PINS = {
    'psxrecomp': ('https://github.com/mstan/psxrecomp.git', '53a057f548cd1f93f1b4d8300caaeded72f4160d'),
    'recomp-ui': ('https://github.com/RetroPortingToolKit/recomp-ui.git', '0546fbcb0126bb14bf88d2128b4fe8a4229570a3'),
}
PIN_BRANCH = 'smt-launcher-pin'

# Display names for discs we have checked. Anything else is named after its serial
# (you can type a name when adding it).
KNOWN = {
    'SLPM-87153': ('SMTif', 'Shin Megami Tensei if... (Anniversary Pack)'),
    'SLPM-86924': ('SMT2', 'Shin Megami Tensei II'),
}
SMTIF_SERIALS = {'SLPM-87153'}

MENU_SNIPPET = '''
# In-game menu (F1): save states, key bindings, controls diagram, guide.
# Added by the SMT Recomp launcher; game_menu_content.h holds this game's text.
if(PSX_RECOMP_UI AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/game_menu.cpp")
    target_sources(psx-runtime PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/game_menu.cpp")
endif()
'''


# ------------------------------------------------------------------ paths
def library_dir():
    return Path(os.environ.get('SMT_RECOMP_HOME', Path.home() / 'SMT-Recomp')).expanduser()


class Lib:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.fw = self.root / '.framework'
        self.games = self.root / 'games'
        self.logs = self.root / 'logs'
        self.discs = self.root / 'discs'
        for d in (self.games, self.logs, self.discs):
            d.mkdir(parents=True, exist_ok=True)

    def project(self, name):
        return self.games / f'{name}Recomp'

    def meta_path(self, name):
        return self.project(name) / 'smt_launcher.json'

    def load(self, name):
        p = self.meta_path(name)
        return json.loads(p.read_text()) if p.exists() else None

    def save(self, meta):
        self.meta_path(meta['name']).write_text(json.dumps(meta, indent=2))

    def all(self):
        out = []
        for p in sorted(self.games.glob('*Recomp/smt_launcher.json')):
            try:
                out.append(json.loads(p.read_text()))
            except (OSError, ValueError):
                pass
        return out


# ------------------------------------------------------------------ disc probing
def cue_bins(cue):
    """-> list of (bin path, track mode) from a .cue sheet."""
    out, cur = [], None
    for line in Path(cue).read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.match(r'\s*FILE\s+"?(.*?)"?\s+BINARY', line, re.I)
        if m:
            p = Path(m.group(1))
            cur = p if p.is_absolute() else Path(cue).parent / p
            continue
        m = re.match(r'\s*TRACK\s+\d+\s+(\S+)', line, re.I)
        if m and cur is not None:
            out.append((cur, m.group(1).upper()))
            cur = None
    return out


def sector_reader(path, mode):
    size, off = {'MODE2/2352': (2352, 24), 'MODE1/2352': (2352, 16), 'MODE1/2048': (2048, 0),
                 'MODE2/2336': (2336, 8)}.get(mode, (2352, 24))
    f = open(path, 'rb')

    def read(lba, n=1):
        out = b''
        for k in range(n):
            f.seek((lba + k) * size + off)
            out += f.read(2048)
        return out
    return read


def iso_find(read, name):
    pvd = read(16)
    if pvd[1:6] != b'CD001':
        raise ValueError('not a PlayStation data disc (no ISO 9660 volume)')
    root = pvd[156:156 + 34]
    lba, size = struct.unpack_from('<I', root, 2)[0], struct.unpack_from('<I', root, 10)[0]
    data = read(lba, (size + 2047) // 2048)
    pos = 0
    while pos < len(data):
        ln = data[pos]
        if ln == 0:
            pos = (pos // 2048 + 1) * 2048
            continue
        flba, fsize = struct.unpack_from('<I', data, pos + 2)[0], struct.unpack_from('<I', data, pos + 10)[0]
        nlen = data[pos + 32]
        fname = data[pos + 33:pos + 33 + nlen].decode('ascii', 'replace').split(';')[0]
        if fname.upper() == name.upper():
            return read(flba, (fsize + 2047) // 2048)[:fsize]
        pos += ln
    return None


def probe(disc):
    """Identify a disc image -> dict(serial, boot, cue, bins)."""
    disc = Path(disc).expanduser().resolve()
    if disc.suffix.lower() == '.cue':
        tracks = cue_bins(disc)
        if not tracks:
            raise ValueError(f'{disc.name}: no tracks in the cue sheet')
        for b, _ in tracks:
            if not b.exists():
                raise ValueError(f'the cue sheet points to a missing file: {b}')
        data_bin, mode = tracks[0]
    else:
        tracks, data_bin, mode = None, disc, 'MODE2/2352'
        if disc.stat().st_size % 2352:
            mode = 'MODE1/2048' if disc.stat().st_size % 2048 == 0 else mode
    read = sector_reader(data_bin, mode)
    cnf = iso_find(read, 'SYSTEM.CNF')
    if cnf is None:
        raise ValueError('no SYSTEM.CNF on the disc: is this a PlayStation game?')
    m = re.search(rb'BOOT\s*=\s*cdrom:\\?([^;\s]+)', cnf, re.I)
    if not m:
        raise ValueError('SYSTEM.CNF has no BOOT line')
    boot = m.group(1).decode('ascii').lstrip('\\')
    serial = boot.upper().replace('_', '-').replace('.', '')
    return {'serial': serial, 'boot': boot, 'disc': str(disc), 'data_bin': str(data_bin), 'mode': mode,
            'cue': str(disc) if tracks else None}


def ensure_cue(lib, info, name):
    """PSXRecomp wants a .cue: write one next to a symlink of a bare .bin."""
    if info['cue']:
        return info['cue']
    d = lib.discs / name
    d.mkdir(parents=True, exist_ok=True)
    link = d / f'{name}.bin'
    if link.exists() or link.is_symlink():
        link.unlink()
    try:
        link.symlink_to(info['data_bin'])
    except OSError:
        shutil.copyfile(info['data_bin'], link)
    cue = d / f'{name}.cue'
    cue.write_text(f'FILE "{link.name}" BINARY\n  TRACK 01 {info["mode"]}\n    INDEX 01 00:00:00\n')
    return str(cue)


# ------------------------------------------------------------------ jobs
class Job:
    """One long-running task (add/build) with a log file. One at a time."""
    lock = threading.Lock()
    current = None

    def __init__(self, lib, name, kind):
        self.lib, self.name, self.kind = lib, name, kind
        self.log = lib.logs / f'{name}.log'
        self.state = 'running'
        self.step = ''
        self.started = time.time()

    def write(self, text):
        with open(self.log, 'a', encoding='utf-8', errors='replace') as f:
            f.write(text)

    def say(self, text):
        self.step = text
        self.write(f'\n==> {text}\n')
        print(f'==> {text}', flush=True)

    def run(self, cmd, cwd=None, env=None):
        self.write('$ ' + ' '.join(shlex.quote(str(c)) for c in cmd) + '\n')
        e = dict(os.environ)
        e.update(env or {})
        p = subprocess.Popen([str(c) for c in cmd], cwd=cwd, env=e, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        with open(self.log, 'ab') as f:
            for line in p.stdout:
                f.write(line)
                f.flush()
                if os.environ.get('SMT_LAUNCHER_ECHO') == '1':
                    sys.stdout.buffer.write(line)
        if p.wait() != 0:
            tail = self.log.read_bytes()[-4000:].decode('utf-8', 'replace')
            hint = ''
            if p.returncode in (-9, 137) or 'exit -9' in tail or 'Killed' in tail:
                hint = (' The computer ran out of memory (the recompile step needs about 6 GB):'
                        ' close other apps and press Rebuild.')
            raise RuntimeError(f'command failed ({p.returncode}): {cmd[0]} ... (see {self.log}).{hint}')


def tools_report():
    rows = []
    for t in ('git', 'cmake', 'ninja', 'pkg-config', 'python3'):
        rows.append((t, shutil.which(t) is not None))
    if sys.platform == 'darwin':
        ok = subprocess.run(['xcode-select', '-p'], capture_output=True).returncode == 0
        rows.append(('Xcode command-line tools', ok))
    else:
        rows.append(('C/C++ compiler', bool(shutil.which('cc') or shutil.which('gcc') or shutil.which('clang'))))
    return rows


def check_tools():
    missing = [t for t, ok in tools_report() if not ok]
    if missing:
        hint = ('Install them with:  xcode-select --install  and  brew install cmake ninja pkg-config git python'
                if sys.platform == 'darwin' else 'Install them with your package manager.')
        raise RuntimeError('missing tools: ' + ', '.join(missing) + '. ' + hint)


def ensure_framework(job):
    for name, (url, sha) in PINS.items():
        d = job.lib.fw / name
        if (d / '.git').exists():
            head = subprocess.run(['git', '-C', str(d), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
            if head == sha:
                continue
            shutil.rmtree(d)
        job.say(f'Downloading {name} ({sha[:8]})')
        d.parent.mkdir(parents=True, exist_ok=True)
        job.run(['git', 'init', '-q', d])
        job.run(['git', '-C', d, 'remote', 'add', 'origin', url])
        job.run(['git', '-C', d, 'fetch', '-q', '--depth', '1', 'origin', sha])
        job.run(['git', '-C', d, 'checkout', '-q', '-B', PIN_BRANCH, 'FETCH_HEAD'])


def c_str(s):
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    return '"' + s.replace('\n', '\\n"\n"') + '"'


def guide_sections(text):
    """'# Title' lines start sections; the rest is the body."""
    secs, title, body = [], None, []
    for line in text.splitlines():
        if line.startswith('# '):
            if title is not None:
                secs.append((title, '\n'.join(body).strip()))
            title, body = line[2:].strip(), []
        else:
            body.append(line)
    if title is not None:
        secs.append((title, '\n'.join(body).strip()))
    return secs


def menu_content(meta, project):
    """game_menu_content.h for a game: SMT if... ships its own; others get a generic one,
    with the guide taken from guide.txt in the project folder if there is one."""
    if meta['serial'] in SMTIF_SERIALS:
        return (HERE / 'menu' / 'smtif_content.h').read_text()
    guide = project / 'guide.txt'
    secs = guide_sections(guide.read_text(encoding='utf-8', errors='replace')) if guide.exists() else []
    if not secs:
        secs = [('About this guide',
                 f'{meta["title"]} ({meta["serial"]}) was built with the SMT Recomp launcher.\n\n'
                 f'No guide has been written for it yet. To add one, put a text file named guide.txt in\n'
                 f'{project}\n'
                 'with a line "# Section title" before each section, then press Rebuild in the launcher.'),
                ('Native build keys',
                 'F1: this menu.  F7: save-state browser.  Tab (hold): fast-forward.  F8: rewind.\n'
                 'Alt+Enter or Ctrl+F: fullscreen.  F6: scanlines.\n'
                 'Controller: Select + R1 save states, Select + L1 fast-forward, Select + L3 this menu.')]
    pad = [('PSX_KB_UP', 'Up'), ('PSX_KB_DOWN', 'Down'), ('PSX_KB_LEFT', 'Left'), ('PSX_KB_RIGHT', 'Right'),
           ('PSX_KB_CIRCLE', 'Circle'), ('PSX_KB_CROSS', 'Cross'), ('PSX_KB_TRIANGLE', 'Triangle'),
           ('PSX_KB_SQUARE', 'Square'), ('PSX_KB_L1', 'L1'), ('PSX_KB_R1', 'R1'), ('PSX_KB_L2', 'L2'),
           ('PSX_KB_R2', 'R2'), ('PSX_KB_START', 'Start'), ('PSX_KB_SELECT', 'Select')]
    actions = meta.get('pad_actions', {})
    out = ['// game_menu_content.h -- written by the SMT Recomp launcher.', '#pragma once',
           f'#define GM_TITLE {c_str(meta["title"].upper())}',
           f'#define GM_PROVIDER_NAME {c_str(meta["name"] + " menu")}', '',
           'static const ManualSection kManual[] = {']
    out += [f'{{{c_str(t)},\n{c_str(b)}}},' for t, b in secs]
    out += ['};', '', 'static const PadButton kPad[] = {']
    out += [f'    {{{k}, {c_str(n)}, {c_str(actions.get(n, ""))}}},' for k, n in pad]
    out += ['};', '']
    return '\n'.join(out)


def install_menu(job, meta):
    proj = job.lib.project(meta['name'])
    shutil.copyfile(HERE / 'menu' / 'game_menu.cpp', proj / 'game_menu.cpp')
    (proj / 'game_menu_content.h').write_text(menu_content(meta, proj))
    cm = proj / 'CMakeLists.txt'
    text = cm.read_text()
    if 'game_menu.cpp' not in text:
        cm.write_text(text.rstrip('\n') + '\n' + MENU_SNIPPET)


def do_add(job, disc, name=None, title=None):
    check_tools()
    job.say('Reading the disc')
    info = probe(disc)
    known = KNOWN.get(info['serial'])
    name = re.sub(r'[^A-Za-z0-9]', '', name or (known[0] if known else info['serial'])) or 'Game'
    if name[0].isdigit():
        name = 'G' + name
    job.name = name
    title = title or (known[1] if known else info['serial'])
    job.write(f'serial {info["serial"]}, boot file {info["boot"]}\n')
    proj = job.lib.project(name)
    if proj.exists():
        raise RuntimeError(f'{proj} already exists. Remove it first, or pick another name.')
    cue = ensure_cue(job.lib, info, name)
    ensure_framework(job)
    job.say('Creating the PSXRecomp project')
    env = {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'protocol.file.allow', 'GIT_CONFIG_VALUE_0': 'always',
           'PSXRECOMP_URL': str(job.lib.fw / 'psxrecomp'), 'RECOMP_UI_URL': str(job.lib.fw / 'recomp-ui')}
    job.run(['sh', job.lib.fw / 'psxrecomp' / 'tools' / 'new_project_layout' / 'setup_project.sh',
             '--disc', cue, '--dir', job.lib.games, '--name', f'{name}Recomp', '--yes', '--players', '1',
             '--no-netplay', '--no-ci', '--no-github', '--no-fetch-boxart', '--enable-recomp-ui', '--no-wizard',
             '--no-generate', '--psxrecomp-ref', PIN_BRANCH, '--recomp-ui-ref', PIN_BRANCH], env=env)
    meta = {'name': name, 'title': title, 'serial': info['serial'], 'boot': info['boot'], 'disc': cue,
            'added': time.strftime('%Y-%m-%d %H:%M'), 'status': 'created', 'exe': None}
    job.lib.save(meta)
    do_build(job, name)


def do_build(job, name):
    check_tools()
    meta = job.lib.load(name)
    if not meta:
        raise RuntimeError(f'no game named {name}')
    proj = job.lib.project(name)
    meta['status'] = 'building'
    job.lib.save(meta)
    try:
        install_menu(job, meta)
        job.say('Recompiling the game code to C (a few minutes)')
        job.run([sys.executable, proj / 'psxrecomp' / 'psxrecomp_cli.py', 'generate', '--config', 'game.toml',
                 '--project-root', '.', '--disc', meta['disc'], '--no-toolchain-download',
                 # re-read the disc every time (it may have been re-patched); the user picked it
                 '--force-prepare', '--skip-hash-check'], cwd=proj)
        job.say('Compiling the native program (usually 5-20 minutes)')
        extra = shlex.split(os.environ.get('EXTRA_CMAKE_ARGS', ''))
        job.run(['cmake', '-S', '.', '-B', 'build', '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release'] + extra, cwd=proj)
        job.run(['cmake', '--build', 'build', '--target', 'psx-runtime'], cwd=proj)
        exe_txt = proj / 'build' / 'psxrecomp_exe_name-psx-runtime.txt'
        exe = exe_txt.read_text().strip() if exe_txt.exists() else None
        if not exe or not (proj / 'build' / exe).exists():
            raise RuntimeError('the build finished but the program is missing')
        meta.update(status='ready', exe=exe, built=time.strftime('%Y-%m-%d %H:%M'))
        job.say(f'Done: {proj / "build" / exe}')
    except Exception:
        meta['status'] = 'failed'
        raise
    finally:
        job.lib.save(meta)


def start_job(lib, kind, name, fn, *args):
    with Job.lock:
        if Job.current and Job.current.state == 'running':
            raise RuntimeError(f'busy: {Job.current.kind} {Job.current.name} is still running')
        job = Job(lib, name, kind)
        job.log.write_text(f'SMT Recomp launcher {VERSION}: {kind} {name} at {time.ctime()}\n')
        Job.current = job

    def body():
        try:
            fn(job, *args)
            job.state = 'done'
        except Exception as e:
            job.state = 'failed'
            job.step = str(e)
            job.write('\nERROR: ' + str(e) + '\n' + traceback.format_exc())
            print('ERROR:', e, file=sys.stderr)
    t = threading.Thread(target=body, daemon=True)
    t.start()
    return job, t


def play(lib, name, extra=()):
    meta = lib.load(name)
    if not meta or meta.get('status') != 'ready':
        raise RuntimeError(f'{name} is not built yet')
    bdir = lib.project(name) / 'build'
    cmd = [str(bdir / meta['exe']), '--game', 'game.toml', '--no-launcher', *extra]
    return subprocess.Popen(cmd, cwd=bdir)


# ------------------------------------------------------------------ web UI
PAGE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SMT Recomp</title>
<style>
:root{--bg:#0f1a1c;--panel:#16272a;--line:#24403f;--ink:#e6efee;--dim:#8fa9a6;--acc:#e5603f;--ok:#5fc39a;--bad:#e06464}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{padding:22px 28px 14px;border-bottom:1px solid var(--line)}h1{margin:0;font-size:22px;letter-spacing:.06em}
h1 b{color:var(--acc)}header p{margin:4px 0 0;color:var(--dim);font-size:13px}
main{max-width:980px;margin:0 auto;padding:20px 16px 60px}
section{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:18px}
h2{margin:0 0 10px;font-size:15px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim)}
.game{display:flex;gap:14px;align-items:center;padding:10px 0;border-top:1px solid var(--line)}.game:first-of-type{border-top:0}
.game .t{flex:1;min-width:0}.game .t b{display:block;font-size:16px}.game .t span{color:var(--dim);font-size:12.5px}
button{background:#23413f;color:var(--ink);border:1px solid #2f5754;border-radius:7px;padding:7px 14px;font:inherit;cursor:pointer}
button:hover{background:#2c524f}button.go{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600}
button:disabled{opacity:.45;cursor:default}
input{background:#0c1517;border:1px solid var(--line);color:var(--ink);border-radius:7px;padding:8px 10px;font:inherit;width:100%}
.row{display:flex;gap:10px;align-items:center;margin-top:8px;flex-wrap:wrap}.row input{flex:1;min-width:220px}
.tag{font-size:11.5px;padding:2px 8px;border-radius:20px;border:1px solid var(--line);color:var(--dim)}
.tag.ready{color:var(--ok);border-color:#2f6a55}.tag.failed{color:var(--bad);border-color:#6a2f2f}
pre{background:#081012;border:1px solid var(--line);border-radius:8px;padding:10px;max-height:340px;overflow:auto;font-size:12px;white-space:pre-wrap;margin:10px 0 0}
.note{color:var(--dim);font-size:13px}.tools span{margin-right:14px}.ok{color:var(--ok)}.bad{color:var(--bad)}
pre:empty{display:none}
@media (max-width:600px){.game{flex-wrap:wrap}.game .t{flex-basis:100%}header{padding:16px}}
</style></head><body>
<header><h1><b>SMT</b> RECOMP</h1><p>Native PlayStation builds with PSXRecomp. Everything happens on this computer.</p></header>
<main>
<section><h2>Library</h2><div id="games" class="note">Loading...</div></section>
<section><h2>Add a game</h2>
<p class="note">Pick a PlayStation disc image (.cue, or a single-track .bin). For a fan translation, apply the patch first and add the patched image.</p>
<div class="row"><input id="disc" placeholder="/path/to/game.cue"><button id="browse">Browse...</button></div>
<div class="row"><input id="name" placeholder="Short name (optional, letters and digits)" style="max-width:340px"><button class="go" id="add">Recompile</button></div>
<p class="note">The first build downloads PSXRecomp (about 200 MB) and takes 10 to 30 minutes.</p>
</section>
<section><h2>Progress</h2><div id="step" class="note">Nothing running.</div><pre id="log"></pre></section>
<section><h2>Tools</h2><div id="tools" class="tools note"></div>
<p class="note">Library folder: <span id="lib"></span></p></section>
</main>
<script>
const $=s=>document.querySelector(s);
async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const j=await r.json();if(!r.ok)throw new Error(j.error||r.statusText);return j}
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
async function refresh(){
  const s=await api('/api/state');
  $('#lib').textContent=s.library;
  $('#tools').innerHTML=s.tools.map(([t,ok])=>`<span class="${ok?'ok':'bad'}">${ok?'&#10003;':'&#10007;'} ${esc(t)}</span>`).join('');
  const busy=s.job&&s.job.state==='running';
  $('#add').disabled=busy;
  $('#games').innerHTML=s.games.length?s.games.map(g=>`<div class="game"><div class="t"><b>${esc(g.title)}</b>
    <span>${esc(g.serial)} &middot; ${esc(g.name)} &middot; added ${esc(g.added)}${g.built?' &middot; built '+esc(g.built):''}</span></div>
    <span class="tag ${esc(g.status)}">${esc(g.status)}</span>
    <button onclick="act('build','${esc(g.name)}')" ${busy?'disabled':''}>Rebuild</button>
    <button onclick="act('folder','${esc(g.name)}')">Folder</button>
    <button class="go" onclick="act('play','${esc(g.name)}')" ${g.status!=='ready'?'disabled':''}>Play</button></div>`).join('')
    :'No games yet. Add one below.';
  if(s.job){$('#step').textContent=`${s.job.kind} ${s.job.name}: ${s.job.state}${s.job.step?' - '+s.job.step:''}`;$('#log').textContent=s.log;$('#log').scrollTop=1e9}
}
async function act(a,name){try{await api('/api/'+a,{name});refresh()}catch(e){alert(e.message)}}
$('#add').onclick=async()=>{try{await api('/api/add',{disc:$('#disc').value.trim(),name:$('#name').value.trim()});refresh()}catch(e){alert(e.message)}};
$('#browse').onclick=async()=>{try{const r=await api('/api/browse',{});if(r.path)$('#disc').value=r.path}catch(e){alert(e.message)}};
refresh();setInterval(refresh,2000);
</script></body></html>'''


def browse_dialog():
    if sys.platform == 'darwin':
        r = subprocess.run(['osascript', '-e', 'POSIX path of (choose file with prompt "Choose a PlayStation disc image (.cue or .bin)")'],
                           capture_output=True, text=True)
        return r.stdout.strip() or None
    for cmd in (['zenity', '--file-selection', '--title=Choose a disc image', '--file-filter=*.cue *.bin'],
                ['kdialog', '--getopenfilename', '.', '*.cue *.bin']):
        if shutil.which(cmd[0]):
            r = subprocess.run(cmd, capture_output=True, text=True)
            return r.stdout.strip() or None
    raise RuntimeError('no file dialog available here: paste the path instead')


def open_folder(path):
    opener = 'open' if sys.platform == 'darwin' else ('explorer' if os.name == 'nt' else 'xdg-open')
    subprocess.Popen([opener, str(path)])


def make_handler(lib):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, obj, ctype='application/json'):
            data = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode()
            self.send_response(code)
            self.send_header('Content-Type', ctype + '; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == '/':
                return self.send(200, PAGE, 'text/html')
            if u.path == '/api/state':
                j = Job.current
                log = ''
                if j and j.log.exists():
                    log = j.log.read_text(encoding='utf-8', errors='replace')[-20000:]
                return self.send(200, {'library': str(lib.root), 'games': lib.all(), 'tools': tools_report(),
                                       'job': j and {'kind': j.kind, 'name': j.name, 'state': j.state, 'step': j.step},
                                       'log': log})
            self.send(404, {'error': 'not found'})

        def do_POST(self):
            # Only accept requests from the launcher's own page.
            origin = self.headers.get('Origin')
            host = self.headers.get('Host', '')
            if origin and urlparse(origin).netloc != host:
                return self.send(403, {'error': 'forbidden'})
            n = int(self.headers.get('Content-Length') or 0)
            try:
                body = json.loads(self.rfile.read(n) or b'{}')
                path = urlparse(self.path).path
                if path == '/api/add':
                    disc = os.path.expanduser(body.get('disc', '').strip().strip('"\''))
                    if not disc or not os.path.exists(disc):
                        raise RuntimeError('choose a disc image first (the path does not exist)')
                    start_job(lib, 'add', body.get('name') or Path(disc).stem, do_add, disc, body.get('name') or None)
                elif path == '/api/build':
                    start_job(lib, 'build', body['name'], do_build, body['name'])
                elif path == '/api/play':
                    play(lib, body['name'])
                elif path == '/api/folder':
                    open_folder(lib.project(body['name']))
                elif path == '/api/browse':
                    return self.send(200, {'path': browse_dialog()})
                else:
                    return self.send(404, {'error': 'not found'})
                self.send(200, {'ok': True})
            except Exception as e:
                self.send(400, {'error': str(e)})
    return H


def serve(lib, port, open_browser=True):
    srv = ThreadingHTTPServer(('127.0.0.1', port), make_handler(lib))
    url = f'http://127.0.0.1:{srv.server_address[1]}/'
    print(f'SMT Recomp launcher: {url}  (library {lib.root}; Ctrl+C to quit)', flush=True)
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


# ------------------------------------------------------------------ CLI
def main():
    ap = argparse.ArgumentParser(description='Build and play PlayStation games natively with PSXRecomp.')
    ap.add_argument('--library', default=str(library_dir()), help='library folder (default ~/SMT-Recomp)')
    sub = ap.add_subparsers(dest='cmd')
    s = sub.add_parser('serve', help='open the launcher in a browser (default)')
    s.add_argument('--port', type=int, default=8765)
    s.add_argument('--no-browser', action='store_true')
    sub.add_parser('list', help='list games')
    a = sub.add_parser('add', help='add and build a disc')
    a.add_argument('disc')
    a.add_argument('--name')
    a.add_argument('--title')
    b = sub.add_parser('build', help='rebuild a game')
    b.add_argument('name')
    p = sub.add_parser('play', help='start a built game')
    p.add_argument('name')
    p.add_argument('extra', nargs=argparse.REMAINDER)
    i = sub.add_parser('probe', help='show what a disc image is')
    i.add_argument('disc')
    args = ap.parse_args()
    lib = Lib(args.library)
    if args.cmd in (None, 'serve'):
        serve(lib, getattr(args, 'port', 8765), not getattr(args, 'no_browser', False))
    elif args.cmd == 'list':
        for g in lib.all():
            print(f"{g['name']:12} {g['serial']:12} {g['status']:9} {g['title']}")
    elif args.cmd == 'probe':
        print(json.dumps(probe(args.disc), indent=2))
    elif args.cmd in ('add', 'build'):
        os.environ['SMT_LAUNCHER_ECHO'] = os.environ.get('SMT_LAUNCHER_ECHO', '1')
        if args.cmd == 'add':
            job, t = start_job(lib, 'add', args.name or Path(args.disc).stem, do_add, args.disc, args.name, args.title)
        else:
            job, t = start_job(lib, 'build', args.name, do_build, args.name)
        t.join()
        print(f'{job.kind} {job.name}: {job.state}  (log: {job.log})')
        sys.exit(0 if job.state == 'done' else 1)
    elif args.cmd == 'play':
        sys.exit(play(lib, args.name, args.extra).wait())


if __name__ == '__main__':
    main()
