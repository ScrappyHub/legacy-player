import sys
import tempfile
import unittest
from pathlib import Path

from adapters.retroarch import NetplayError, build_guest_command, build_host_command, find_core


class RetroArchNetplayTests(unittest.TestCase):
    def test_host_and_guest_commands(self):
        host = build_host_command("ra", "core", "rom.sfc", 55435, "Al")
        self.assertEqual(["ra", "-L", "core", "rom.sfc", "--host", "--port", "55435", "--nick", "Al"], host)
        guest = build_guest_command("ra", "core", "rom.sfc", "10.0.0.5", 55435, "Bo")
        self.assertIn("--connect", guest)
        self.assertEqual("10.0.0.5", guest[guest.index("--connect") + 1])

    def test_rejects_option_injection_and_bad_ports(self):
        with self.assertRaises(NetplayError):
            build_guest_command("ra", "core", "rom", "--command", 55435)
        with self.assertRaises(NetplayError):
            build_guest_command("ra", "core", "rom", "a b", 55435)
        with self.assertRaises(NetplayError):
            build_host_command("ra", "core", "rom", 80)

    def test_nick_is_sanitised(self):
        command = build_host_command("ra", "core", "rom", 55435, "Al;rm -rf /")
        self.assertNotIn(";", command[-1])
        self.assertNotIn("/", command[-1])

    def test_finds_core_next_to_executable_or_explains(self):
        suffix = {"win32": ".dll", "darwin": ".dylib"}.get(sys.platform, ".so")
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "retroarch"
            exe.write_text("x")
            with self.assertRaisesRegex(NetplayError, "No RetroArch core"):
                find_core(str(exe), "snes")
            (Path(d) / "cores").mkdir()
            core = Path(d) / "cores" / f"snes9x_libretro{suffix}"
            core.write_text("c")
            self.assertTrue(core.samefile(find_core(str(exe), "snes")))
            with self.assertRaisesRegex(NetplayError, "not set up"):
                find_core(str(exe), "ps2")


if __name__ == "__main__":
    unittest.main()
