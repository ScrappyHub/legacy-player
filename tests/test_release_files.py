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
        self.assertIn("Get-ChildItem dist/release", wf)
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


class VersionExamplesTests(unittest.TestCase):
    def test_version_examples_match_version(self):
        import re
        from launcher.version import VERSION
        for rel in ("README.md", "docs/RELEASE.md", "lp.ps1", "install.ps1"):
            for m in re.findall(r"v\d+\.\d+\.\d+", text(rel)):
                self.assertEqual(m, "v" + VERSION, rel)


class FirewallExactPortTests(unittest.TestCase):
    def test_short_port_does_not_match_longer_one(self):
        from unittest import mock
        from launcher import firewall
        out = mock.Mock(returncode=0, stdout="LocalPort:                           8765\n")
        with mock.patch.object(firewall, "supported", return_value=True):
            self.assertFalse(firewall.status(87, run=lambda *a, **k: out)["allowed"])


class InstallCommandsTests(unittest.TestCase):
    def test_readme_has_a_command_for_every_shell(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
        raw = "https://raw.githubusercontent.com/Alpallyoop/legacy-player/main/install.ps1"
        self.assertIn(f"irm {raw} | iex", text)
        self.assertIn(f'powershell -NoProfile -ExecutionPolicy Bypass -Command "irm {raw} | iex"', text)
        self.assertIn("powershell.exe", text)


class UpdaterTargetsRunningCopyTests(unittest.TestCase):
    def test_installer_can_target_a_folder_and_stays_open_on_failure(self):
        text = (ROOT / "install.ps1").read_text(encoding="utf-8")
        self.assertIn("[string]$Dest", text)
        updater = (ROOT / "launcher" / "selfupdate.py").read_text(encoding="utf-8")
        self.assertIn("Path(sys.executable).resolve().parent", updater)     # the in-app update replaces the copy that is running
        self.assertIn("The update did not finish", updater)
        self.assertIn("did not finish", text)


class ReleaseGateTests(unittest.TestCase):
    def test_only_tested_commits_on_main_are_built_and_published(self):
        wf = text("tools/release.workflow.yml")
        main_check, tests, build = (wf.index(x) for x in ("merge-base --is-ancestor", "tools/release_check.py", "-BuildOnly"))
        self.assertLess(main_check, build)
        self.assertLess(tests, build)
        self.assertIn("fetch-depth: 0", wf)            # a shallow clone cannot answer the ancestry question

    def test_publishing_is_a_draft_first_and_can_run_again(self):
        wf = text("tools/release.workflow.yml")
        publish = wf[wf.index("- name: Publish the release"):]
        self.assertIn("--draft", publish)
        self.assertIn("--clobber", publish)
        self.assertIn("--draft=false", publish)
        self.assertLess(publish.index("gh release upload"), publish.index("--draft=false"))

    def test_smoke_check_requires_real_answers(self):
        wf = text("tools/release.workflow.yml")
        smoke = wf[wf.index("- name: Check the built app starts"):wf.index("- name: Attest build provenance")]
        for needle in ("LegacyPlayerUI", "--social-run", "legacy-player-friends", "--server-run", "18765"):
            self.assertIn(needle, smoke)


class InstallerNeverClosesTheWindowTests(unittest.TestCase):
    def test_no_exit_through_iex(self):
        inst = text("install.ps1")
        self.assertNotIn("trap", inst)
        exits = [line for line in inst.splitlines() if re.search(r"\bexit\b", line) and not line.lstrip().startswith("#")]
        self.assertEqual(["if ($lpFailed -and -not $lpViaIex) { exit 1 }"], [e.strip() for e in exits])
        self.assertIn("$ProgressPreference = 'SilentlyContinue'", inst)
        self.assertIn("WaitForExit(5000)", inst)
