#!/bin/bash
set -e
cd /home/claude/emu
[ -d pcsx_rearmed ] || git clone -q --depth 1 https://github.com/libretro/pcsx_rearmed.git
cd pcsx_rearmed && git submodule update -q --init --depth 1
grep -q retro_dbg_vram plugins/gpulib/gpu.c || cat >> plugins/gpulib/gpu.c <<'C'

/* debug: expose VRAM for automated translation testing */
void *retro_dbg_vram(void) { return gpu.vram; }
C
python3 - <<'PY'
p='libpcsxcore/cdrom.c'
s=open(p).read()
if 'retro_dbg_cdlog' not in s:
    s=s.replace("""	ret = cdra_readTrack(time);
	if (ret == 0)
		memcpy(cdr.Prev, time, 3);""","""	ret = cdra_readTrack(time);
	if (dbg_cd_n < 65536)
		dbg_cd_lba[dbg_cd_n++] = msf2sec(time) - 150;
	if (ret == 0)
		memcpy(cdr.Prev, time, 3);""")
    decl="static int ReadTrack(const u8 *time)\n{"
    s=s.replace(decl,"""static unsigned int dbg_cd_lba[65536];
static unsigned int dbg_cd_n;
unsigned int retro_dbg_cdlog(unsigned int *out, unsigned int max)
{
	unsigned int n = dbg_cd_n < max ? dbg_cd_n : max, i;
	for (i = 0; i < n; i++) out[i] = dbg_cd_lba[i];
	dbg_cd_n = 0;
	return n;
}

"""+decl,1)
    open(p,'w').write(s)
PY
make -f Makefile.libretro -j2 > ../build.log 2>&1
nm -D pcsx_rearmed_libretro.so | grep dbg_
