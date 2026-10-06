import tempfile
import unittest
from pathlib import Path

from adapters.dolphin.configurator import (
    ManagedDolphinConfig,
    install_dsu_into_existing_user,
    restore_dsu_backup,
)


class DolphinConfiguratorTests(unittest.TestCase):
    def test_managed_config_is_complete_and_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "ManagedUser"
            manifest = ManagedDolphinConfig(root, pad_count=4).create()
            config = root / "Config"
            self.assertEqual(4, manifest["pad_count"])
            self.assertIn("Enabled = True", (config / "DSUClient.ini").read_text())
            pads = (config / "GCPadNew.ini").read_text()
            self.assertIn("Device = DSUClient/0/LegacyPlayer", pads)
            self.assertIn("Device = DSUClient/3/LegacyPlayer", pads)
            self.assertTrue((root / "legacy-player.json").is_file())

    def test_existing_config_install_is_reversible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "Config"
            config.mkdir()
            target = config / "DSUClient.ini"
            target.write_text("[Server]\nEnabled = False\n", encoding="utf-8")
            backup = install_dsu_into_existing_user(root)
            self.assertIn("Enabled = True", target.read_text(encoding="utf-8"))
            restore_dsu_backup(backup)
            self.assertEqual("[Server]\nEnabled = False\n", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
