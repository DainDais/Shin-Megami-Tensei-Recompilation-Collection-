/* add to plugins/gpulib/gpu.c in pcsx_rearmed, then rebuild with make -f Makefile.libretro */
void *retro_dbg_vram(void) { return gpu.vram; }
