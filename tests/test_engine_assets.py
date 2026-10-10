"""Every engine's download pattern must pick the Windows package out of the file names its project publishes today.

The lists below are the real asset names of each project's latest release (read from api.github.com on 2026-10-10).
When a project renames its files the pattern in launcher/engines.py has to follow, and this test says which one broke
before a player sees "no Windows package this app recognises"."""
import unittest

from launcher.engines import ENGINES
from launcher.installer import pick_asset

RELEASES = {
    "pcsx2": ("pcsx2-v2.8.2-windows-x64-Qt.7z", ["pcsx2-v2.8.2-linux-appimage-x64-Qt.AppImage", "pcsx2-v2.8.2-macos-Qt.tar.xz",
                                                   "pcsx2-v2.8.2-windows-x64-installer.exe", "pcsx2-v2.8.2-windows-x64-Qt-symbols.7z",
                                                   "pcsx2-v2.8.2-windows-x64-Qt.7z"]),
    "ppsspp": ("PPSSPP-v1.20.4-Windows-x64.zip", ["ppsspp-1.20.4.tar.xz", "PPSSPP-iOS-v1.20.4.ipa", "PPSSPP-v1.20.4-anylinux-x86_64.AppImage",
                                                   "PPSSPP-v1.20.4-Windows-ARM64.zip", "PPSSPP-v1.20.4-Windows-x64.zip", "PPSSPPSDL-macOS-v1.20.4.zip"]),
    "azahar": ("azahar-windows-msvc-2126.2.zip", ["azahar-android-vanilla-2126.2.apk", "azahar-libretro-windows-x86_64-2126.2.zip",
                                                   "azahar-macos-universal-2126.2.zip", "azahar-windows-msvc-2126.2-installer.exe",
                                                   "azahar-windows-msvc-2126.2.zip", "azahar-windows-msys2-2126.2.zip", "azahar-windows-mxe-2126.2.zip"]),
    "mgba": ("mGBA-0.10.5-win64.7z", ["mGBA-0.10.5-3ds.7z", "mGBA-0.10.5-macos.dmg", "mGBA-0.10.5-win32-installer.exe", "mGBA-0.10.5-win32.7z",
                                       "mGBA-0.10.5-win64-installer.exe", "mGBA-0.10.5-win64.7z"]),
    "melonds": ("melonDS-1.1-windows-x86_64.zip", ["melonDS-1.1-appimage-x86_64.zip", "melonDS-1.1-macOS-universal.zip",
                                                    "melonDS-1.1-windows-aarch64.zip", "melonDS-1.1-windows-x86_64.zip"]),
    "duckstation": ("duckstation-windows-x64-release.zip", ["DuckStation-arm64.AppImage", "duckstation-mac-release.zip",
                                                             "duckstation-windows-arm64-release.zip", "duckstation-windows-x64-installer.exe",
                                                             "duckstation-windows-x64-release-symbols.7z", "duckstation-windows-x64-release.zip",
                                                             "duckstation-windows-x64-sse2-release.zip"]),
    "bsnes": ("bsnes_v115-windows.zip", ["bsnes_v115-windows.zip"]),
    "snes9x": ("snes9x-1.63-win32-x64.zip", ["snes9x-1.63-libretro-x64.zip", "Snes9x-1.63-Mac.zip", "snes9x-1.63-win32-x64.zip",
                                              "snes9x-1.63-win32.zip", "Snes9x-1.63-x86_64.AppImage"]),
    "mesen": ("Mesen_2.1.1_Windows.zip", ["Mesen_2.1.1_Linux_ARM64.zip", "Mesen_2.1.1_Linux_x64.zip", "Mesen_2.1.1_macOS_ARM64_AppleSilicon.zip",
                                           "Mesen_2.1.1_macOS_x64_Intel.zip", "Mesen_2.1.1_Windows.zip"]),
    "xemu": ("xemu-win-x86_64-release.zip", ["xemu-0.8.136-aarch64.AppImage", "xemu-0.8.136-dbg-windows-x86_64.zip", "xemu-0.8.136-macos-universal.zip",
                                              "xemu-0.8.136-windows-arm64.zip", "xemu-0.8.136-windows-x86_64-pdb.zip", "xemu-0.8.136-windows-x86_64.zip",
                                              "xemu-win-aarch64-release.zip", "xemu-win-x86_64-release.zip"]),
    "xenia": ("xenia_canary_windows_.zip", ["xenia_canary_linux.tar_.xz", "xenia_canary_windows_.zip"]),
    "rpcs3": ("rpcs3-v0.0.43-20275-68e0d602_win64_msvc.7z", ["rpcs3-v0.0.43-20275-68e0d602_win64_msvc.7z",
                                                              "rpcs3-v0.0.43-20275-68e0d602_win64_msvc.7z.sha256"]),
}


class EngineAssetPatterns(unittest.TestCase):
    def test_every_github_engine_is_covered_here(self):
        github = {k for k, v in ENGINES.items() if v["source"]["kind"] == "github"}
        self.assertEqual(github, set(RELEASES), "add the new engine's current release files to RELEASES")

    def test_patterns_pick_the_windows_package(self):
        for engine_id, (want, names) in RELEASES.items():
            with self.subTest(engine=engine_id):
                assets = [{"name": n, "url": "", "size": 1} for n in names]
                got = pick_asset(assets, ENGINES[engine_id]["source"]["asset"])
                self.assertIsNotNone(got, f"{engine_id}: pattern matched nothing in {names}")
                self.assertEqual(got["name"], want)

    def test_old_names_still_match(self):
        """Projects that used to publish under the older names must keep working if they go back."""
        for engine_id, old in {"mesen": "Mesen_Windows.zip", "ppsspp": "ppsspp_win.zip", "melonds": "melonDS-windows-x86_64.zip",
                               "azahar": "azahar-2120.1-windows-msvc.zip", "xenia": "xenia_canary_windows.zip"}.items():
            with self.subTest(engine=engine_id):
                self.assertIsNotNone(pick_asset([{"name": old, "url": "", "size": 1}], ENGINES[engine_id]["source"]["asset"]))


if __name__ == "__main__":
    unittest.main()
