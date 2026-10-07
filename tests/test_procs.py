import os
import subprocess
import sys
import unittest

from launcher import procs


@unittest.skipIf(sys.platform == "win32", "uses sleep")
class ProcsTests(unittest.TestCase):
    def test_alive_start_time_and_reuse_guard(self):
        p = subprocess.Popen(["sleep", "30"])
        self.addCleanup(lambda: (p.kill(), p.wait()))
        t = procs.start_time(p.pid)
        self.assertTrue(procs.is_alive(p.pid, t))
        self.assertFalse(procs.is_alive(p.pid, (t or 0) + 1))          # same number, different process: not ours
        self.assertIn(p.pid, procs.children(os.getpid()))
        p.kill(); p.wait()
        self.assertFalse(procs.is_alive(p.pid))


if __name__ == "__main__":
    unittest.main()
