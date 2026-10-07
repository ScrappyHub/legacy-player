"""Release hardening, round 5: per-address lockouts, IPv6/name server codes, scrubber, hosted-server kit."""
import ipaddress
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from launcher import servercode
from launcher.reports import Scrubber
from server.lobby import LobbyError, LobbyService
from server.lobby.invites import InviteBook, InviteError
from server.lobby.throttle import FailureThrottle, key_for

ROOT = Path(__file__).resolve().parents[1]
FP = "ab" * 16
KEY = "0102030405"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class ThrottleTests(unittest.TestCase):
    def test_locks_one_address_not_others_and_unlocks(self):
        clock = Clock()
        t = FailureThrottle(max_failures=3, window=60, lockout=300, clock=clock)
        for _ in range(3):
            t.fail("8.8.8.8")
        self.assertGreater(t.blocked("8.8.8.8"), 0)
        self.assertEqual(0, t.blocked("9.9.9.9"))
        clock.now += 301
        self.assertEqual(0, t.blocked("8.8.8.8"))

    def test_this_computer_is_never_locked_and_ipv6_counts_by_network(self):
        t = FailureThrottle(max_failures=1)
        t.fail("127.0.0.1"); t.fail("::1"); t.fail(None); t.fail("not an address")
        self.assertEqual(0, t.blocked("127.0.0.1"))
        self.assertEqual(key_for("2001:db8:1:2:aaaa::1"), key_for("2001:db8:1:2:bbbb::9"))
        self.assertNotEqual(key_for("2001:db8:1:2::1"), key_for("2001:db8:1:3::1"))

    def test_table_stays_bounded(self):
        t = FailureThrottle(max_failures=100)
        for i in range(6000):
            t.fail(str(ipaddress.IPv4Address(0x08000000 + i)))
        self.assertLessEqual(len(t._fails), 4200)


class InviteLockoutTests(unittest.TestCase):
    def test_wrong_guesses_lock_that_address_but_a_real_code_still_works_for_others(self):
        book = InviteBook(pepper=b"x" * 32)
        code, _ = book.create("s1")
        for _ in range(5):
            with self.assertRaises(InviteError):
                book.redeem_ex("AAAAA-AAAAA", "6.6.6.6")
        with self.assertRaises(InviteError) as ctx:
            book.redeem_ex(code, "6.6.6.6")                    # even the right code, while locked out
        self.assertIn("Try again", str(ctx.exception))
        self.assertEqual("s1", book.redeem_ex(code, "7.7.7.7")[0])


class AccessKeyThrottleTests(unittest.TestCase):
    def test_wrong_key_attempts_lock_the_address(self):
        svc = LobbyService()
        svc.access_key = "0a0b0c0d0e"
        for _ in range(8):
            with self.assertRaises(PermissionError):
                svc.dispatch({"operation": "browse", "access_key": "nope", "_peer": "5.5.5.5"})
        with self.assertRaises(PermissionError) as ctx:
            svc.dispatch({"operation": "browse", "access_key": "0a0b0c0d0e", "_peer": "5.5.5.5"})
        self.assertIn("Too many", str(ctx.exception))
        svc.dispatch({"operation": "browse", "access_key": "0a0b0c0d0e", "_peer": "5.5.5.6"})   # someone else is fine
        svc.dispatch({"operation": "browse", "access_key": "0a0b0c0d0e", "_peer": "127.0.0.1"})  # this computer is fine


class ServerCodeTests(unittest.TestCase):
    def test_round_trips_ipv4_ipv6_and_names(self):
        for host, expect in (("1.2.3.4", "1.2.3.4"), ("2001:db8::5", "2001:db8::5"), ("[fe80::1]", "fe80::1"),
                             ("Home.DuckDNS.org", "home.duckdns.org"), ("localhost", "localhost")):
            code = servercode.encode(host, 8765, FP, KEY)
            self.assertEqual((expect, 8765, KEY), (lambda d: (d["host"], d["port"], d["key"]))(servercode.decode(code)), host)
            self.assertTrue(code.startswith("LP-" if host == "1.2.3.4" else "LP2-"))

    def test_typos_and_bad_names_are_caught(self):
        code = servercode.encode("home.duckdns.org", 8765, FP, KEY)
        flipped = code[:9] + ("A" if code[9] != "A" else "B") + code[10:]
        with self.assertRaises(servercode.CodeError):
            servercode.decode(flipped)
        with self.assertRaises(servercode.CodeError):
            servercode.encode("bad_name.org", 1, FP)
        with self.assertRaises(servercode.CodeError):
            servercode.decode("LP2-0000")

    def test_old_codes_still_decode(self):
        self.assertEqual("10.0.0.9", servercode.decode(servercode.encode("10.0.0.9", 9000, FP, KEY))["host"])


class ScrubberTests(unittest.TestCase):
    def test_new_shapes_are_removed(self):
        sc = Scrubber({})
        for text in ("failed ::1", "peer fe80::1%eth0", "[2001:db8::5]:8765", "::ffff:1.2.3.4", "mac aa:bb:cc:dd:ee:ff",
                     "https://my.site.org/x?k=1", "my.site.org:8765", "access_key=abc123", "token: zzz",
                     "LP2-01GG-E1P6-2Y9E", "code abcd1-2efgh", "0123456789abcdef0123"):
            out = sc.text(text)
            for leak in ("::1", "fe80", "2001", "ffff", "aa:bb", "my.site.org", "abc123", "zzz", "01GG", "abcd1", "0123456789abcdef"):
                self.assertNotIn(leak, out, (text, out))

    def test_ordinary_text_survives(self):
        sc = Scrubber({})
        for text in ("at 12:30:45 it ran", "ratio 3:1", "launcher/app.py:120 in run", "right-click the game"):
            self.assertEqual(text, sc.text(text))


class DeployKitTests(unittest.TestCase):
    def test_files_exist_and_compose_parses(self):
        for rel in ("deploy/Dockerfile", "deploy/docker-compose.yml", "deploy/Caddyfile", "deploy/.env.example",
                    "deploy/legacy-player-server.service", "deploy/README.md", "tools/check_deployment.py"):
            self.assertTrue((ROOT / rel).is_file(), rel)
        text = (ROOT / "deploy/docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("server.cli", (ROOT / "deploy/Dockerfile").read_text(encoding="utf-8"))
        self.assertIn("no-new-privileges", text)
        self.assertNotIn("REPORT_TOKEN=", (ROOT / "deploy/.env.example").read_text(encoding="utf-8").replace("REPORT_TOKEN=\n", ""))

    def test_cli_prints_a_code_that_decodes_and_keeps_it_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = lambda: subprocess.run([sys.executable, "-m", "server.cli", "code", "--state-dir", tmp, "--address", "play.example.org"],
                                         cwd=ROOT, capture_output=True, text=True, timeout=60).stdout.strip()
            first = run()
            self.assertTrue(first.startswith("LP2-"), first)
            self.assertEqual("play.example.org", servercode.decode(first)["host"])
            self.assertEqual(first, run())          # same certificate and key: same code

    def test_signing_and_attestation_are_wired_but_optional(self):
        wf = (ROOT / "tools/release.workflow.yml").read_text(encoding="utf-8")
        self.assertIn("attest-build-provenance", wf)
        self.assertIn("WINDOWS_SIGN_PFX_BASE64", wf)
        self.assertEqual(wf, (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"))
        ps = (ROOT / "tools/package_release.ps1").read_text(encoding="utf-8")
        self.assertIn("Set-AuthenticodeSignature", ps)
        self.assertIn("NOT code-signed", ps)


if __name__ == "__main__":
    unittest.main()
