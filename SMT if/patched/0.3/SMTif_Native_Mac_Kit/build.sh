#!/bin/bash
# Builds Shin Megami Tensei if... (English patch v0.3) as a native program with PSXRecomp.
#
#   bash build.sh                      # asks for your patched .bin
#   bash build.sh /path/to/patched.bin # or pass it (a .cue works too)
#
# Needs: Xcode command-line tools, and Homebrew's cmake, ninja, pkg-config, git, python.
# Your disc is read locally. The game's code is recompiled on your machine and never leaves it.
set -eu

PSXRECOMP_URL="https://github.com/mstan/psxrecomp.git"
PSXRECOMP_COMMIT="53a057f548cd1f93f1b4d8300caaeded72f4160d"   # the version this kit was tested with
RECOMP_UI_URL="https://github.com/RetroPortingToolKit/recomp-ui.git"
RECOMP_UI_COMMIT="0546fbcb0126bb14bf88d2128b4fe8a4229570a3"   # settings UI + Dear ImGui for the F1 menu
EXPECTED_CRC="F27A4461"                                        # English patch v0.3 applied to the Anniversary Pack disc

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- tools
say "Checking tools"
missing=""
for t in git cmake ninja python3 pkg-config; do
    command -v "$t" >/dev/null 2>&1 || missing="$missing $t"
done
if [ "$(uname)" = "Darwin" ]; then
    xcode-select -p >/dev/null 2>&1 ||
        die "Xcode command-line tools are missing. Run:  xcode-select --install  then run this script again."
fi
if [ -n "$missing" ]; then
    brew_names=$(echo "$missing" | sed 's/python3/python/')
    die "Missing:$missing
Install them with Homebrew (https://brew.sh):  brew install$brew_names"
fi
echo "ok: $(cmake --version | head -1), ninja $(ninja --version), $(python3 --version)"

# ---------------------------------------------------------------- disc
DISC="${1:-}"
if [ -z "$DISC" ]; then
    echo
    echo "Drag your English-patched .bin file into this window, then press Return:"
    read -r DISC
fi
# Terminal drag-and-drop adds quotes, backslash-escaped spaces and a trailing space.
DISC=$(printf '%s' "$DISC" | sed -e 's/[[:space:]]*$//' -e "s/^'\(.*\)'$/\1/" -e 's/^"\(.*\)"$/\1/' -e 's/\\\(.\)/\1/g')
DISC=$(python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$DISC")
[ -f "$DISC" ] || die "File not found: $DISC"

case "$DISC" in
    *.cue|*.CUE)
        BIN=$(python3 - "$DISC" <<'PY'
import os, re, sys
cue = sys.argv[1]
for line in open(cue, encoding="utf-8", errors="replace"):
    m = re.match(r'\s*FILE\s+"?(.*?)"?\s+BINARY', line, re.I)
    if m:
        p = m.group(1)
        print(p if os.path.isabs(p) else os.path.join(os.path.dirname(cue), p))
        break
PY
)
        [ -f "$BIN" ] || die "The .cue points to a .bin that doesn't exist: $BIN"
        DISC="$BIN" ;;
esac

say "Checking the disc image (this reads all 256 MB)"
CRC=$(python3 - "$DISC" <<'PY'
import sys, zlib
c = 0
with open(sys.argv[1], "rb") as f:
    while True:
        b = f.read(1 << 22)
        if not b:
            break
        c = zlib.crc32(b, c)
print("%08X" % c)
PY
)
SKIP_HASH=""
if [ "$CRC" != "$EXPECTED_CRC" ]; then
    if [ "${FORCE:-0}" = "1" ]; then
        echo "CRC32 is $CRC, expected $EXPECTED_CRC. Continuing because FORCE=1."
        SKIP_HASH="--skip-hash-check"
    else
        die "This disc image's CRC32 is $CRC, but the English-patched disc should be $EXPECTED_CRC.
Apply SMTif_PS1_English_v0.3.xdelta to the ORIGINAL Japanese .bin (CRC32 D77E3D8F) and use that output.
(To build from a different image anyway, run:  FORCE=1 bash build.sh)"
    fi
else
    echo "ok: CRC32 $CRC (English patch v0.3)"
fi

# ---------------------------------------------------------------- PSXRecomp
say "Getting PSXRecomp (${PSXRECOMP_COMMIT:0:8})"
if [ -d psxrecomp/.git ] && [ "$(git -C psxrecomp rev-parse HEAD 2>/dev/null)" = "$PSXRECOMP_COMMIT" ]; then
    echo "already present"
else
    rm -rf psxrecomp
    git init -q psxrecomp
    git -C psxrecomp remote add origin "$PSXRECOMP_URL"
    git -C psxrecomp fetch -q --depth 1 origin "$PSXRECOMP_COMMIT"
    git -C psxrecomp checkout -q FETCH_HEAD
fi
git -C psxrecomp submodule update -q --init --recursive --depth 1

say "Getting recomp-ui (${RECOMP_UI_COMMIT:0:8})"
if [ -d recomp-ui/.git ] && [ "$(git -C recomp-ui rev-parse HEAD 2>/dev/null)" = "$RECOMP_UI_COMMIT" ]; then
    echo "already present"
else
    rm -rf recomp-ui
    git init -q recomp-ui
    git -C recomp-ui remote add origin "$RECOMP_UI_URL"
    git -C recomp-ui fetch -q --depth 1 origin "$RECOMP_UI_COMMIT"
    git -C recomp-ui checkout -q FETCH_HEAD
fi
git -C recomp-ui submodule update -q --init --recursive --depth 1

# ---------------------------------------------------------------- recompile
say "Recompiling the game's code to C (builds the recompiler first; a few minutes)"
# --force-prepare: always copy this disc into disc/, so a rebuild after re-patching never
# reuses an older copy of the game.
python3 psxrecomp/psxrecomp_cli.py generate --config game.toml --project-root . \
    --disc "$DISC" --no-toolchain-download --force-prepare $SKIP_HASH
[ -f generated/SLPM_871.53_dispatch.c ] || die "Recompilation did not produce generated/SLPM_871.53_dispatch.c"
[ -f disc/SMTif.cue ] || die "Disc preparation did not produce disc/SMTif.cue"

# Point the runtime at the prepared copy of your disc.
python3 - "$HERE/disc/SMTif.cue" <<'PY'
import re, sys
path = "game.toml"
text = open(path, encoding="utf-8").read()
text = re.sub(r'^disc = .*$', 'disc = "%s"' % sys.argv[1].replace("\\", "/"), text, count=1, flags=re.M)
open(path, "w", encoding="utf-8").write(text)
PY

# ---------------------------------------------------------------- build
say "Compiling the native game (the slow part: usually 5-20 minutes)"
# EXTRA_CMAKE_ARGS is only for unusual setups (e.g. pre-downloaded dependencies).
# shellcheck disable=SC2086
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release ${EXTRA_CMAKE_ARGS:-}
cmake --build build --target psx-runtime

EXE="$HERE/build/SMTif_Recompiled"
[ -x "$EXE" ] || die "The build finished but $EXE is missing"

cat > "$HERE/play.command" <<'SH'
#!/bin/bash
# Double-click to play. F1 opens the in-game menu (save states, key bindings, controls, guide).
# Keyboard: arrows = D-pad, S = Circle (confirm), X = Cross (cancel), A = Triangle, Z = Square,
# Q/W = L1/R1, E/R = L2/R2, Return = Start, Right Shift = Select.
cd "$(dirname "$0")/build" && exec ./SMTif_Recompiled --game game.toml --no-launcher "$@"
SH
chmod +x "$HERE/play.command"

say "Done!"
echo "Play by double-clicking play.command in this folder, or run:  ./play.command"
echo "In the game, press F1 for the menu: save states, key bindings, controls and the guide."
echo "If the picture is black or wrong, try the software renderer:  ./play.command --renderer software"
