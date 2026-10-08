import socket
import threading
import time
import unittest

from adapters.retroarch import tunnel
from launcher import punch
from launcher.lobby_client import LobbyClient, LobbyClientError
from tests.test_community_lobby import PROFILE
from tests.test_launcher import ServerThread
from tests.test_relay import echo_server


class PunchBase(unittest.TestCase):
    def setUp(self):
        self.server = ServerThread().start()
        self.addCleanup(self.server.stop)
        self.client = LobbyClient("127.0.0.1", self.server.port)
        created = self.client.call({"operation": "create", "participant_id": "host", "profile": PROFILE,
                                    "adapter_id": "retroarch", "game_pack_id": "generic", "max_players": 3})
        sid = created["session"]["session_id"]
        self.host_auth = {"session_id": sid, "participant_id": "host", "credential": created["credential"]}
        joined = self.client.call({"operation": "join", "invite_code": created["invite_code"], "participant_id": "g1", "profile": PROFILE})
        self.guest_auth = {"session_id": sid, "participant_id": "g1", "credential": joined["credential"]}


class IntroductionTests(PunchBase):
    def test_server_introduces_host_and_guest_and_each_sees_the_others_port(self):
        got = {}
        t = threading.Thread(target=lambda: got.update(zip(("port", "peer"), self.client.open_punch("host", self.host_auth))), daemon=True)
        t.start()
        time.sleep(0.4)
        gport, gpeer = self.client.open_punch("guest", self.guest_auth)
        t.join(5)
        self.assertEqual(got["peer"], ["127.0.0.1", gport])      # the host was told the guest's port
        self.assertEqual(gpeer, ["127.0.0.1", got["port"]])      # and the guest the host's

    def test_guest_is_refused_at_once_when_the_host_is_not_waiting(self):
        with self.assertRaises(LobbyClientError):
            self.client.open_punch("guest", self.guest_auth)

    def test_both_sides_must_agree_and_strangers_are_refused(self):
        import json
        with socket.create_connection(("127.0.0.1", self.server.port), timeout=5) as s:
            s.sendall(json.dumps({"operation": "punch", "role": "host", **self.host_auth}).encode() + b"\n")
            self.assertFalse(json.loads(s.makefile().readline())["ok"])
        bad = {**self.guest_auth, "credential": "x" * 40}
        with self.assertRaises(LobbyClientError):
            self.client.open_punch("guest", bad)


@unittest.skipUnless(tunnel.available(), "TLS-PSK needs Python 3.13+")
class DirectMatchTests(PunchBase):
    def setUp(self):
        super().setUp()
        self.echo = echo_server()
        self.addCleanup(self.echo.close)
        self.key = tunnel.new_key()

    def _guest(self, direct):
        relay = lambda: self.client.open_relay("guest", self.guest_auth, wait_paired=True)
        dialer = punch.GuestDialer(direct, relay)
        guest = tunnel.Tunnel("guest", self.key, "127.0.0.1", 0, "", 0, dial=dialer).start()
        self.addCleanup(guest.stop)
        return guest, dialer

    def _ping(self, guest):
        with socket.create_connection(("127.0.0.1", guest.port), timeout=20) as s:
            for i in range(20):
                s.sendall(b"frame-%02d" % i)
                self.assertEqual(s.recv(64), b"frame-%02d" % i)

    def test_game_traffic_goes_computer_to_computer_when_the_route_works(self):
        host = tunnel.RelayHost(self.key, lambda track: punch.dial(self.client, "host", self.host_auth, on_socket=track),
                                "127.0.0.1", self.echo.getsockname()[1], slots=1).start()
        self.addCleanup(host.stop)
        time.sleep(0.4)
        guest, dialer = self._guest(lambda: punch.dial(self.client, "guest", self.guest_auth))
        self._ping(guest)
        self.assertEqual("direct", dialer.path)
        self.assertEqual(1, host.served)

    def test_falls_back_to_the_relay_when_the_host_is_not_waiting_directly(self):
        relay_host = tunnel.RelayHost(self.key, lambda track: self.client.open_relay("host", self.host_auth, wait_paired=True, on_socket=track),
                                      "127.0.0.1", self.echo.getsockname()[1], slots=2).start()
        self.addCleanup(relay_host.stop)
        time.sleep(0.4)
        guest, dialer = self._guest(lambda: punch.dial(self.client, "guest", self.guest_auth))
        self._ping(guest)
        self.assertEqual("relay", dialer.path)
        self.assertFalse(dialer.use_direct)       # later connections skip the direct attempt

    def test_blocked_route_falls_back_and_direct_off_uses_the_relay(self):
        relay_host = tunnel.RelayHost(self.key, lambda track: self.client.open_relay("host", self.host_auth, wait_paired=True, on_socket=track),
                                      "127.0.0.1", self.echo.getsockname()[1], slots=2).start()
        self.addCleanup(relay_host.stop)
        time.sleep(0.4)

        def blocked():
            raise OSError("the routers did not let a direct connection through")
        guest, dialer = self._guest(blocked)
        self._ping(guest)
        self.assertEqual("relay", dialer.path)
        guest2, dialer2 = self._guest(None)
        self._ping(guest2)
        self.assertEqual("relay", dialer2.path)


if __name__ == "__main__":
    unittest.main()
