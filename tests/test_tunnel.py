import socket
import sys
import threading
import unittest

from adapters.retroarch import tunnel


def echo_server():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)

    def run():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            def h(c=c):
                while d := c.recv(4096):
                    c.sendall(d)
                c.close()
            threading.Thread(target=h, daemon=True).start()
    threading.Thread(target=run, daemon=True).start()
    return srv


@unittest.skipUnless(tunnel.available(), "TLS-PSK needs Python 3.13+")
class TunnelTests(unittest.TestCase):
    def setUp(self):
        self.echo = echo_server()
        self.key = tunnel.new_key()
        self.host = tunnel.Tunnel("host", self.key, "127.0.0.1", 0, "127.0.0.1", self.echo.getsockname()[1]).start()

    def tearDown(self):
        self.host.stop()
        self.echo.close()

    def test_round_trip_is_encrypted_on_the_wire(self):
        guest = tunnel.Tunnel("guest", self.key, "127.0.0.1", 0, "127.0.0.1", self.host.port).start()
        self.addCleanup(guest.stop)
        with socket.create_connection(("127.0.0.1", guest.port), timeout=5) as s:
            s.sendall(b"hello netplay")
            self.assertEqual(s.recv(100), b"hello netplay")
        # a plain (non-TLS) client talking to the public port gets nothing useful
        with socket.create_connection(("127.0.0.1", self.host.port), timeout=5) as raw:
            raw.sendall(b"hello netplay")
            raw.settimeout(3)
            try:
                data = raw.recv(100)
            except (socket.timeout, OSError):
                data = b""
            self.assertNotEqual(data, b"hello netplay")

    def _assert_cut(self, s):
        s.settimeout(5)
        try:
            data = s.recv(100)
        except ConnectionError:
            data = b""
        self.assertEqual(b"", data)                      # the match ended instead of hanging on

    def test_stop_cuts_matches_that_are_still_running(self):
        guest = tunnel.Tunnel("guest", self.key, "127.0.0.1", 0, "127.0.0.1", self.host.port).start()
        self.addCleanup(guest.stop)
        s = socket.create_connection(("127.0.0.1", guest.port), timeout=5)
        self.addCleanup(s.close)
        s.sendall(b"ping")
        self.assertEqual(b"ping", s.recv(100))
        self.assertTrue(any(isinstance(x, tunnel.ssl.SSLSocket) for x in self.host.open_sockets))
        self.assertTrue(any(isinstance(x, tunnel.ssl.SSLSocket) for x in guest.open_sockets))
        self.host.stop()
        self._assert_cut(s)
        self.assertEqual(set(), self.host.open_sockets)

    def test_guest_stop_cuts_its_side_too(self):
        guest = tunnel.Tunnel("guest", self.key, "127.0.0.1", 0, "127.0.0.1", self.host.port).start()
        s = socket.create_connection(("127.0.0.1", guest.port), timeout=5)
        self.addCleanup(s.close)
        s.sendall(b"ping")
        self.assertEqual(b"ping", s.recv(100))
        guest.stop()
        self._assert_cut(s)

    def test_relay_host_stop_cuts_paired_matches(self):
        a, b = socket.socketpair()                       # b plays the lobby relay's end of a paired connection
        self.addCleanup(b.close)
        handed = threading.Event()

        def dial(track):
            if handed.is_set():
                raise OSError("no more")
            handed.set()
            track(a)
            return a
        relay = tunnel.RelayHost(self.key, dial, "127.0.0.1", self.echo.getsockname()[1], slots=1).start()
        self.addCleanup(relay.stop)
        context = tunnel._context(False, self.key)
        client = context.wrap_socket(b, server_hostname=None)
        self.addCleanup(client.close)
        client.sendall(b"over relay")
        self.assertEqual(b"over relay", client.recv(100))
        self.assertTrue(any(isinstance(x, tunnel.ssl.SSLSocket) for x in relay.open_sockets))
        relay.stop()
        client.settimeout(5)
        try:
            data = client.recv(100)
        except (ConnectionError, tunnel.ssl.SSLError):
            data = b""
        self.assertEqual(b"", data)

    def test_listener_port_cannot_be_shared(self):
        other = socket.socket()
        self.addCleanup(other.close)
        if sys.platform != "win32":
            other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        with self.assertRaises(OSError):
            other.bind(("127.0.0.1", self.host.port))

    def test_wrong_key_is_refused(self):
        guest = tunnel.Tunnel("guest", tunnel.new_key(), "127.0.0.1", 0, "127.0.0.1", self.host.port).start()
        self.addCleanup(guest.stop)
        with socket.create_connection(("127.0.0.1", guest.port), timeout=5) as s:
            s.settimeout(5)
            try:
                s.sendall(b"secret")
                data = s.recv(100)
            except OSError:
                data = b""
            self.assertEqual(data, b"")


if __name__ == "__main__":
    unittest.main()
