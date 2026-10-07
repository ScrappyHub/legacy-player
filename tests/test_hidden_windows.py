import subprocess
import unittest

from launcher import selfuninstall


class HiddenWindowTests(unittest.TestCase):
    def test_cleanup_script_is_not_detached(self):
        # DETACHED_PROCESS makes Windows ignore CREATE_NO_WINDOW; every command in the script then opens a console
        flags = selfuninstall._hidden_flags()
        self.assertEqual(0, flags & 0x00000008)
        self.assertEqual(0x08000000, flags & 0x08000000)


if __name__ == "__main__":
    unittest.main()
