import socket
import threading
import unittest

from adapters.retroarch import tunnel
from launcher.lobby_client import LobbyClient, LobbyClientError
from tests.test_community_lobby import PROFILE
from tests.test_launcher import ServerThread


def echo_server():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)

    def run():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return

            def h(c=c):
                try:
                    while d := c.recv(4096):
                        c.sendall(d)
                except OSError:
                    pass
                c.close()
            threading.Thread(target=h, daemon=True).start()
    threading.Thread(target=run, daemon=True).start()
    return srv


@unittest.skipUnless(tunnel.available(), "TLS-PSK needs Python 3.13+")
class RelayTests(unittest.TestCase):
    def setUp(self):
        self.server = ServerThread().start()
        self.addCleanup(self.server.stop)
        self.client = LobbyClient("127.0.0.1", self.server.port)
        created = self.client.call({"operation": "create", "participant_id": "host", "profile": PROFILE,
                                    "adapter_id": "retroarch", "game_pack_id": "generic", "max_players": 3})
        self.sid = created["session"]["session_id"]
        self.host_auth = {"session_id": self.sid, "participant_id": "host", "credential": created["credential"]}
        joined = self.client.call({"operation": "join", "invite_code": created["invite_code"], "participant_id": "g1", "profile": PROFILE})
        self.guest_auth = {"session_id": self.sid, "participant_id": "g1", "credential": joined["credential"]}
        self.echo = echo_server()
        self.addCleanup(self.echo.close)

    def test_bytes_flow_host_to_guest_through_the_server_without_addresses(self):
        key = tunnel.new_key()
        host = tunnel.RelayHost(key, lambda: self.client.open_relay("host", self.host_auth, wait_paired=True),
                                "127.0.0.1", self.echo.getsockname()[1], slots=2).start()
        self.addCleanup(host.stop)
        guest = tunnel.Tunnel("guest", key, "127.0.0.1", 0, "", 0,
                              dial=lambda: self.client.open_relay("guest", self.guest_auth, wait_paired=True)).start()
        self.addCleanup(guest.stop)
        import time
        time.sleep(0.3)  # let the host park its connections
        with socket.create_connection(("127.0.0.1", guest.port), timeout=10) as s:
            for i in range(50):
                s.sendall(b"frame-%03d" % i)
                self.assertEqual(s.recv(64), b"frame-%03d" % i)
        # a second guest connection also works (another parked slot)
        with socket.create_connection(("127.0.0.1", guest.port), timeout=10) as s:
            s.sendall(b"again")
            self.assertEqual(s.recv(64), b"again")
        self.assertEqual([], host.errors)

    def test_outsiders_and_wrong_keys_are_refused(self):
        with self.assertRaisesRegex(LobbyClientError, "credential"):
            self.client.open_relay("guest", {**self.guest_auth, "credential": "nope"}, wait_paired=True)
        with self.assertRaisesRegex(LobbyClientError, "only the host"):
            self.client.open_relay("host", self.guest_auth, wait_paired=False)
        with self.assertRaisesRegex(LobbyClientError, "not ready"):
            self.client.open_relay("guest", self.guest_auth, wait_paired=True)
        # wrong PSK: the relay pairs them, but the TLS handshake fails and no bytes cross
        host = tunnel.RelayHost(tunnel.new_key(), lambda: self.client.open_relay("host", self.host_auth, wait_paired=True),
                                "127.0.0.1", self.echo.getsockname()[1], slots=1).start()
        self.addCleanup(host.stop)
        guest = tunnel.Tunnel("guest", tunnel.new_key(), "127.0.0.1", 0, "", 0,
                              dial=lambda: self.client.open_relay("guest", self.guest_auth, wait_paired=True)).start()
        self.addCleanup(guest.stop)
        import time
        time.sleep(0.3)
        with socket.create_connection(("127.0.0.1", guest.port), timeout=5) as s:
            s.settimeout(3)
            try:
                s.sendall(b"secret")
                data = s.recv(64)
            except OSError:
                data = b""
            self.assertEqual(b"", data)

    def test_endpoint_kind_relay_hides_the_address(self):
        self.client.call({"operation": "validate", **self.host_auth})
        self.client.call({"operation": "set_endpoint", "kind": "relay", "psk": "ab" * 32, **self.host_auth})
        ep = self.client.call({"operation": "get_endpoint", **self.guest_auth})["endpoint"]
        self.assertEqual({"kind": "relay", "address": "relay", "psk": "ab" * 32}, ep)


if __name__ == "__main__":
    unittest.main()
