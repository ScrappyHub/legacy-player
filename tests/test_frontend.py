import os
import tempfile
import unittest
from pathlib import Path

from frontend.core import Core, core_suffix

CANDIDATES = [Path(p) for p in (
    "/usr/lib/x86_64-linux-gnu/libretro/nestopia_libretro.so", "/usr/lib/libretro/nestopia_libretro.so",
    Path.home() / ".config/retroarch/cores" / f"nestopia_libretro{core_suffix()}",
    Path(os.environ.get("APPDATA", "")) / "RetroArch/cores" / f"nestopia_libretro{core_suffix()}",
)]
CORE = next((p for p in CANDIDATES if p.is_file()), None)


def tiny_nes_rom(path: Path) -> None:
    """A minimal iNES file: 1 PRG bank of NOPs with a reset vector, 1 CHR bank."""
    header = b"NES\x1a\x01\x01\x00\x00" + b"\x00" * 8
    prg = bytearray(b"\xea" * 16384)
    prg[0x3FFC:0x3FFE] = (0x8000).to_bytes(2, "little")
    path.write_bytes(header + bytes(prg) + b"\x00" * 8192)


@unittest.skipUnless(CORE, "no nestopia libretro core on this machine")
class CoreLoaderTests(unittest.TestCase):
    def test_core_boots_runs_and_saves_state_in_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "t.nes"
            tiny_nes_rom(rom)
            core = Core(CORE, tmp, tmp)
            try:
                self.assertEqual("Nestopia", core.info()["name"])
                av = core.load(rom)
                self.assertEqual((256, 240), (av["width"], av["height"]))
                core.run(30)
                self.assertEqual(30, core.frames)
                self.assertGreater(core.audio_samples, 1000)
                width, height, rgb = core.frame_rgb()
                self.assertEqual(len(rgb), width * height * 3)
                state = core.save_state()
                core.press(0, "start")
                core.run(5)
                core.load_state(state)
                self.assertGreater(len(state), 1000)
            finally:
                core.close()


class EnvironmentStringTests(unittest.TestCase):
    """Strings handed to a core must be long-lived C buffers held by the Core, not temporaries."""

    def _core(self, system="/sys/dir", save="/save/dir"):
        import ctypes
        from unittest import mock
        with mock.patch.object(ctypes, "CDLL"), mock.patch.object(Core, "_bind"):
            return Core("fake-core", system, save)

    def test_directories_point_at_buffers_the_core_keeps(self):
        import ctypes
        import gc
        from frontend import core as fc
        core = self._core()
        for cmd, buf, want in ((fc.ENV_GET_SYSTEM_DIRECTORY, core._system_buf, b"/sys/dir"),
                               (fc.ENV_GET_SAVE_DIRECTORY, core._save_buf, b"/save/dir")):
            out = ctypes.c_void_p()
            self.assertTrue(core._environment(cmd, ctypes.addressof(out)))
            self.assertEqual(ctypes.addressof(buf), out.value)
            gc.collect()
            junk = [bytes(64) for _ in range(1000)]        # churn the heap; the pointer must still read the same
            self.assertEqual(want, ctypes.string_at(out.value))
            del junk

    def test_variable_value_stays_valid_and_follows_changes(self):
        import ctypes
        import gc
        from frontend import core as fc
        core = self._core()
        core.variables = {"nestopia_palette": "cxa2025as"}
        var = fc.retro_variable(b"nestopia_palette", None)
        self.assertTrue(core._environment(fc.ENV_GET_VARIABLE, ctypes.addressof(var)))
        first = ctypes.c_void_p.from_buffer(var, fc.retro_variable.value.offset).value
        gc.collect()
        self.assertEqual(b"cxa2025as", ctypes.string_at(first))
        self.assertEqual(ctypes.addressof(core._var_bufs["nestopia_palette"]), first)
        self.assertTrue(core._environment(fc.ENV_GET_VARIABLE, ctypes.addressof(var)))      # same value: same buffer
        self.assertEqual(first, ctypes.c_void_p.from_buffer(var, fc.retro_variable.value.offset).value)
        core.variables["nestopia_palette"] = "raw"
        core._environment(fc.ENV_GET_VARIABLE, ctypes.addressof(var))
        self.assertEqual(b"raw", var.value)
        self.assertEqual(b"cxa2025as", ctypes.string_at(first))       # the old pointer the core may hold is still good
        unknown = fc.retro_variable(b"nope", None)
        self.assertFalse(core._environment(fc.ENV_GET_VARIABLE, ctypes.addressof(unknown)))


class WindowArgsTests(unittest.TestCase):
    def test_one_or_two_optional_folders(self):
        from unittest import mock
        from frontend import window
        for extra, want in (([], ("", "")), (["sysdir"], ("sysdir", "")), (["sysdir", "savedir"], ("sysdir", "savedir")),
                            (["a", "b", "c"], ("a", "b"))):
            with mock.patch.object(window, "run", return_value=0) as run:
                self.assertEqual(0, window.main(["window", "core.so", "rom.nes"] + extra))
            run.assert_called_once_with("core.so", "rom.nes", *want)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(2, window.main(["window", "core.so"]))
        self.assertIn("usage", out.getvalue())


if __name__ == "__main__":
    unittest.main()
