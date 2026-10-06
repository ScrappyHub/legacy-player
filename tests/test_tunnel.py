import socket
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
