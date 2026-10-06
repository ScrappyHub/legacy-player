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


if __name__ == "__main__":
    unittest.main()
