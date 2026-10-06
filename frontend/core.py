"""Minimal libretro core loader using only ctypes.

Implements the environment, video, audio and input callbacks a core needs to boot and run
frames. Verified against nestopia_libretro.so: load, retro_load_game, retro_run x N frames,
256x240 XRGB8888 output, serialize/unserialize (save states).
"""
from __future__ import annotations

import ctypes as C
import sys
from pathlib import Path

# retro_environment commands we answer (libretro.h)
ENV_GET_OVERSCAN = 2
ENV_GET_CAN_DUPE = 3
ENV_SET_PIXEL_FORMAT = 10
ENV_GET_VARIABLE = 15
ENV_SET_VARIABLES = 16
ENV_GET_VARIABLE_UPDATE = 17
ENV_GET_SYSTEM_DIRECTORY = 9
ENV_GET_SAVE_DIRECTORY = 31
ENV_GET_LOG_INTERFACE = 27
ENV_SET_INPUT_DESCRIPTORS = 11
ENV_GET_INPUT_BITMASKS = 51 | 0x10000
ENV_SET_CORE_OPTIONS_V2 = 67
ENV_SET_CORE_OPTIONS_V2_INTL = 68
ENV_GET_CORE_OPTIONS_VERSION = 52
ENV_SET_GEOMETRY = 37
ENV_GET_LANGUAGE = 39

PIXEL_0RGB1555, PIXEL_XRGB8888, PIXEL_RGB565 = 0, 1, 2
DEVICE_JOYPAD = 1
# RetroPad ids
JOYPAD = {"b": 0, "y": 1, "select": 2, "start": 3, "up": 4, "down": 5, "left": 6, "right": 7,
          "a": 8, "x": 9, "l": 10, "r": 11, "l2": 12, "r2": 13, "l3": 14, "r3": 15}


class retro_game_info(C.Structure):
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_char_p)]


class retro_game_geometry(C.Structure):
    _fields_ = [("base_width", C.c_uint), ("base_height", C.c_uint), ("max_width", C.c_uint),
                ("max_height", C.c_uint), ("aspect_ratio", C.c_float)]


class retro_system_timing(C.Structure):
    _fields_ = [("fps", C.c_double), ("sample_rate", C.c_double)]


class retro_system_av_info(C.Structure):
    _fields_ = [("geometry", retro_game_geometry), ("timing", retro_system_timing)]


class retro_system_info(C.Structure):
    _fields_ = [("library_name", C.c_char_p), ("library_version", C.c_char_p), ("valid_extensions", C.c_char_p),
                ("need_fullpath", C.c_bool), ("block_extract", C.c_bool)]


class retro_variable(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


ENV_CB = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO_CB = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUDIO_CB = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDIO_BATCH_CB = C.CFUNCTYPE(C.c_size_t, C.POINTER(C.c_int16), C.c_size_t)
INPUT_POLL_CB = C.CFUNCTYPE(None)
INPUT_STATE_CB = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)


class Core:
    """One loaded libretro core. Not thread-safe; drive it from one thread."""

    def __init__(self, library: str | Path, system_dir: str | Path, save_dir: str | Path) -> None:
        self.lib = C.CDLL(str(library))
        self.system_dir = str(system_dir).encode()
        self.save_dir = str(save_dir).encode()
        self.pixel_format = PIXEL_0RGB1555
        self.frame: bytes | None = None
        self.frame_size = (0, 0, 0)       # width, height, pitch
        self.frames = 0
        self.audio_samples = 0
        self.buttons: dict[int, set[int]] = {0: set(), 1: set(), 2: set(), 3: set()}
        self.variables: dict[str, str] = {}
        self.log: list[str] = []
        self._keep = []                   # ctypes callbacks must outlive the core
        self._bind()

    # -- callbacks ---------------------------------------------------------------
    def _environment(self, cmd: int, data) -> bool:
        if cmd == ENV_SET_PIXEL_FORMAT:
            self.pixel_format = C.cast(data, C.POINTER(C.c_int)).contents.value
            return True
        if cmd in (ENV_GET_SYSTEM_DIRECTORY, ENV_GET_SAVE_DIRECTORY):
            value = self.system_dir if cmd == ENV_GET_SYSTEM_DIRECTORY else self.save_dir
            buf = C.c_char_p(value)
            self._keep.append(buf)
            C.cast(data, C.POINTER(C.c_char_p))[0] = buf.value
            return True
        if cmd == ENV_GET_CAN_DUPE:
            C.cast(data, C.POINTER(C.c_bool))[0] = True
            return True
        if cmd == ENV_GET_OVERSCAN:
            C.cast(data, C.POINTER(C.c_bool))[0] = False
            return True
        if cmd == ENV_GET_VARIABLE:
            var = C.cast(data, C.POINTER(retro_variable)).contents
            key = var.key.decode() if var.key else ""
            value = self.variables.get(key)
            if value is None:
                return False
            buf = C.c_char_p(value.encode())
            self._keep.append(buf)
            var.value = buf.value
            return True
        if cmd == ENV_GET_VARIABLE_UPDATE:
            C.cast(data, C.POINTER(C.c_bool))[0] = False
            return True
        if cmd == ENV_GET_CORE_OPTIONS_VERSION:
            C.cast(data, C.POINTER(C.c_uint))[0] = 0   # plain SET_VARIABLES is enough for us
            return True
        if cmd == ENV_GET_LANGUAGE:
            C.cast(data, C.POINTER(C.c_uint))[0] = 0
            return True
        if cmd in (ENV_SET_VARIABLES, ENV_SET_INPUT_DESCRIPTORS, ENV_SET_GEOMETRY):
            return True
        return False

    def _video(self, data, width, height, pitch) -> None:
        self.frames += 1
        if data:
            self.frame_size = (width, height, pitch)
            self.frame = C.string_at(data, pitch * height)

    def _audio_batch(self, data, frames) -> int:
        self.audio_samples += frames
        return frames

    def _audio(self, left, right) -> None:
        self.audio_samples += 1

    def _input_state(self, port, device, index, id_) -> int:
        if device == DEVICE_JOYPAD and port in self.buttons:
            return 1 if id_ in self.buttons[port] else 0
        return 0

    def _bind(self) -> None:
        lib = self.lib
        lib.retro_api_version.restype = C.c_uint
        lib.retro_serialize_size.restype = C.c_size_t
        lib.retro_serialize.restype = C.c_bool
        lib.retro_unserialize.restype = C.c_bool
        lib.retro_load_game.restype = C.c_bool
        self.cbs = [ENV_CB(self._environment), VIDEO_CB(self._video), AUDIO_CB(self._audio),
                    AUDIO_BATCH_CB(self._audio_batch), INPUT_POLL_CB(lambda: None), INPUT_STATE_CB(self._input_state)]
        lib.retro_set_environment(self.cbs[0])
        lib.retro_set_video_refresh(self.cbs[1])
        lib.retro_set_audio_sample(self.cbs[2])
        lib.retro_set_audio_sample_batch(self.cbs[3])
        lib.retro_set_input_poll(self.cbs[4])
        lib.retro_set_input_state(self.cbs[5])
        lib.retro_init()

    # -- API -------------------------------------------------------------------
    def info(self) -> dict:
        si = retro_system_info()
        self.lib.retro_get_system_info(C.byref(si))
        return {"name": si.library_name.decode(), "version": si.library_version.decode(),
                "extensions": si.valid_extensions.decode(), "need_fullpath": si.need_fullpath,
                "api": self.lib.retro_api_version()}

    def load(self, rom: str | Path) -> dict:
        rom = Path(rom)
        data = rom.read_bytes()
        self._rom_buffer = C.create_string_buffer(data, len(data))
        self._rom_path = str(rom).encode()
        game = retro_game_info(self._rom_path, C.cast(self._rom_buffer, C.c_void_p), len(data), None)
        if not self.lib.retro_load_game(C.byref(game)):
            raise RuntimeError("the core refused this game file")
        av = retro_system_av_info()
        self.lib.retro_get_system_av_info(C.byref(av))
        return {"width": av.geometry.base_width, "height": av.geometry.base_height, "fps": av.timing.fps,
                "sample_rate": av.timing.sample_rate, "pixel_format": self.pixel_format}

    def run(self, frames: int = 1) -> None:
        for _ in range(frames):
            self.lib.retro_run()

    def press(self, port: int, *names: str) -> None:
        self.buttons[port] = {JOYPAD[n] for n in names}

    def save_state(self) -> bytes:
        size = self.lib.retro_serialize_size()
        buf = C.create_string_buffer(size)
        if not self.lib.retro_serialize(buf, size):
            raise RuntimeError("the core could not save its state")
        return buf.raw

    def load_state(self, state: bytes) -> None:
        buf = C.create_string_buffer(state, len(state))
        if not self.lib.retro_unserialize(buf, len(state)):
            raise RuntimeError("the core rejected that save state")

    def frame_rgb(self) -> tuple[int, int, bytes]:
        """Current frame as packed RGB bytes (for a viewer). Handles the three libretro formats."""
        width, height, pitch = self.frame_size
        if not self.frame or not width:
            return 0, 0, b""
        out = bytearray(width * height * 3)
        src = self.frame
        if self.pixel_format == PIXEL_XRGB8888:
            for y in range(height):
                row = src[y * pitch:y * pitch + width * 4]
                base = y * width * 3
                for x in range(width):
                    out[base + 3 * x] = row[4 * x + 2]
                    out[base + 3 * x + 1] = row[4 * x + 1]
                    out[base + 3 * x + 2] = row[4 * x]
        else:
            bits565 = self.pixel_format == PIXEL_RGB565
            for y in range(height):
                row = src[y * pitch:y * pitch + width * 2]
                base = y * width * 3
                for x in range(width):
                    v = row[2 * x] | (row[2 * x + 1] << 8)
                    if bits565:
                        r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
                        out[base + 3 * x:base + 3 * x + 3] = bytes((r << 3, g << 2, b << 3))
                    else:
                        r, g, b = (v >> 10) & 31, (v >> 5) & 31, v & 31
                        out[base + 3 * x:base + 3 * x + 3] = bytes((r << 3, g << 3, b << 3))
        return width, height, bytes(out)

    def close(self) -> None:
        try:
            self.lib.retro_unload_game()
            self.lib.retro_deinit()
        except Exception:
            pass


def core_suffix() -> str:
    return {"win32": ".dll", "darwin": ".dylib"}.get(sys.platform, ".so")
