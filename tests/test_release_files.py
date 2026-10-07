"""Guards for the release plumbing, which cannot be run off Windows: names, versions and copies that must agree."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def text(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class ReleaseFilesTests(unittest.TestCase):
    def test_version_is_plain_semver(self):
        v = re.search(r'^VERSION\s*=\s*"([^"]+)"', text("launcher/version.py"), re.M).group(1)
        self.assertRegex(v, r"^\d+\.\d+\.\d+$")

    def test_workflow_copy_matches_the_live_workflow(self):
        live, copy = ROOT / ".github/workflows/release.yml", ROOT / "tools/release.workflow.yml"
        if not (live.exists() and copy.exists()):
            self.skipTest("workflow files not in this checkout")
        self.assertEqual(copy.read_text(encoding="utf-8"), live.read_text(encoding="utf-8"))

    def test_only_one_release_workflow_exists(self):
        self.assertFalse((ROOT / "tools/build-exe.workflow.yml").exists(), "a second release workflow would publish twice")

    def test_installer_and_packager_agree_on_asset_names(self):
        pack, inst = text("tools/package_release.ps1"), text("install.ps1")
        self.assertIn("LegacyPlayer-$version-win64.zip", pack)
        self.assertIn("LegacyPlayer-$version-win64.exe", pack)
        self.assertIn("SHA256SUMS.txt", pack)
        self.assertIn("'LegacyPlayer-*-win64.zip'", inst)           # the installer takes the zip, never the bare exe
        self.assertIn("'LegacyPlayer-*-win64.zip.sha256'", inst)
        self.assertRegex(inst, r'throw "This release has no checksum file')

    def test_workflow_publishes_everything_in_the_release_folder_and_checks_the_tag(self):
        wf = text("tools/release.workflow.yml")
        self.assertIn("dist/release/*", wf)
        self.assertIn("does not match VERSION", wf)

    def test_cli_has_its_commands(self):
        lp = text("lp.ps1")
        for word in ("install", "update", "run", "version", "path", "uninstall", "source"):
            self.assertIn(f"'{word}'", lp)
        self.assertTrue((ROOT / "lp.cmd").exists())

    def test_gitignore_keeps_build_output_out(self):
        gi = text(".gitignore")
        for pat in ("dist/", "build/", "*.spec", "_to_delete/"):
            self.assertIn(pat, gi)


if __name__ == "__main__":
    unittest.main()
