#!/usr/bin/env python3
"""Minimal headless libretro frontend (ctypes) for automated PS1 testing.

Emu(core_so, cue_path): .run(frames, buttons), .shot(png), .ram(), .save(path), .load(path)
Uses PCSX-ReARMed with HLE BIOS, so no BIOS file is required.
"""
import ctypes as C
import os

RETRO_DEVICE_JOYPAD = 1
BTN = {'B': 0, 'Y': 1, 'SELECT': 2, 'START': 3, 'UP': 4, 'DOWN': 5, 'LEFT': 6, 'RIGHT': 7,
       'A': 8, 'X': 9, 'L': 10, 'R': 11, 'L2': 12, 'R2': 13}
# PS1 mapping in libretro: B=Cross, A=Circle, Y=Square, X=Triangle
PS = {'CROSS': 'B', 'CIRCLE': 'A', 'SQUARE': 'Y', 'TRIANGLE': 'X'}


class retro_game_info(C.Structure):
    _fields_ = [('path', C.c_char_p), ('data', C.c_void_p), ('size', C.c_size_t), ('meta', C.c_char_p)]


class retro_variable(C.Structure):
    _fields_ = [('key', C.c_char_p), ('value', C.c_char_p)]


class retro_system_av_info(C.Structure):
    _fields_ = [('base_width', C.c_uint), ('base_height', C.c_uint), ('max_width', C.c_uint),
                ('max_height', C.c_uint), ('aspect_ratio', C.c_float),
                ('fps', C.c_double), ('sample_rate', C.c_double)]


ENV_CB = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO_CB = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUDIO_CB = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDIOB_CB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL_CB = C.CFUNCTYPE(None)
STATE_CB = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)


class Emu:
    def __init__(self, core, game, sysdir='/home/claude/emu/system', options=None):
        os.makedirs(sysdir, exist_ok=True)
        self.lib = C.CDLL(core)
        self.sysdir = C.c_char_p(sysdir.encode())
        self.opts = {b'pcsx_rearmed_bios': b'HLE', b'pcsx_rearmed_show_bios_bootlogo': b'disabled',
                     b'pcsx_rearmed_drc': b'enabled', b'pcsx_rearmed_frameskip_type': b'disabled'}
        if options:
            self.opts.update({k.encode(): v.encode() for k, v in options.items()})
        self._keep = []
        self.fmt = 0
        self.frame = None
        self.pressed = set()
        self.cb_env = ENV_CB(self._env)
        self.cb_video = VIDEO_CB(self._video)
        self.cb_audio = AUDIO_CB(lambda l, r: None)
        self.cb_audiob = AUDIOB_CB(lambda d, n: n)
        self.cb_poll = POLL_CB(lambda: None)
        self.cb_state = STATE_CB(self._state)
        L = self.lib
        L.retro_set_environment(self.cb_env)
        L.retro_set_video_refresh(self.cb_video)
        L.retro_set_audio_sample(self.cb_audio)
        L.retro_set_audio_sample_batch(self.cb_audiob)
        L.retro_set_input_poll(self.cb_poll)
        L.retro_set_input_state(self.cb_state)
        L.retro_init()
        gi = retro_game_info(game.encode(), None, 0, None)
        L.retro_load_game.restype = C.c_bool
        if not L.retro_load_game(C.byref(gi)):
            raise RuntimeError('load_game failed')
        L.retro_get_memory_data.restype = C.c_void_p
        L.retro_get_memory_size.restype = C.c_size_t
        L.retro_serialize_size.restype = C.c_size_t
        L.retro_serialize.restype = C.c_bool
        L.retro_unserialize.restype = C.c_bool
        L.retro_set_controller_port_device(0, RETRO_DEVICE_JOYPAD)

    # --- callbacks
    def _env(self, cmd, data):
        if cmd in (9, 31):  # system / save directory
            C.cast(data, C.POINTER(C.c_char_p))[0] = self.sysdir.value
            return True
        if cmd == 10:  # pixel format
            self.fmt = C.cast(data, C.POINTER(C.c_int))[0]
            return True
        if cmd == 15:  # get variable
            var = C.cast(data, C.POINTER(retro_variable))[0]
            v = self.opts.get(var.key)
            if v is None:
                return False
            buf = C.c_char_p(v)
            self._keep.append(buf)
            C.cast(data, C.POINTER(retro_variable))[0].value = buf.value
            return True
        if cmd == 17:  # variable update
            C.cast(data, C.POINTER(C.c_bool))[0] = False
            return True
        if cmd == 52:  # core options version
            C.cast(data, C.POINTER(C.c_uint))[0] = 0
            return True
        return False

    def _video(self, data, w, h, pitch):
        if data:
            self.frame = (C.string_at(data, pitch * h), w, h, pitch)

    def _state(self, port, device, index, idn):
        if port == 0 and device == RETRO_DEVICE_JOYPAD:
            return 1 if idn in self.pressed else 0
        return 0

    # --- API
    def run(self, frames, *buttons):
        self.pressed = {BTN[PS.get(b, b)] for b in buttons}
        for _ in range(frames):
            self.lib.retro_run()
        self.pressed = set()

    def tap(self, button, hold=3, after=20):
        self.run(hold, button)
        self.run(after)

    def ram(self):
        p = self.lib.retro_get_memory_data(2)
        n = self.lib.retro_get_memory_size(2)
        return C.string_at(p, n)

    def write_ram(self, addr, data):
        p = self.lib.retro_get_memory_data(2)
        C.memmove(p + (addr & 0x1fffff), data, len(data))

    def save(self, path):
        n = self.lib.retro_serialize_size()
        buf = C.create_string_buffer(n)
        assert self.lib.retro_serialize(buf, n)
        open(path, 'wb').write(buf.raw)

    def load(self, path):
        b = open(path, 'rb').read()
        assert self.lib.retro_unserialize(b, len(b))

    def image(self):
        from PIL import Image
        data, w, h, pitch = self.frame
        if self.fmt == 1:  # XRGB8888
            img = Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB')
        else:  # RGB565 (fmt 2) or 0RGB1555
            import numpy as np
            a = np.frombuffer(data, dtype='<u2').reshape(h, pitch // 2)[:, :w].astype(np.uint32)
            if self.fmt == 2:
                r, g, b = (a >> 11) & 31, (a >> 5) & 63, a & 31
                rgb = np.dstack([r * 255 // 31, g * 255 // 63, b * 255 // 31]).astype(np.uint8)
            else:
                r, g, b = (a >> 10) & 31, (a >> 5) & 31, a & 31
                rgb = np.dstack([r * 255 // 31, g * 255 // 31, b * 255 // 31]).astype(np.uint8)
            img = Image.fromarray(rgb)
        return img

    def shot(self, path, scale=2):
        from PIL import Image
        img = self.image()
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
        img.save(path)
        return path


def vram(self):
    import ctypes as C
    self.lib.retro_dbg_vram.restype = C.c_void_p
    p = self.lib.retro_dbg_vram()
    return C.string_at(p, 1024 * 512 * 2)


Emu.vram = vram
