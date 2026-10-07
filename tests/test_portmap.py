import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from launcher import portmap

DESC = """<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0"><device><serviceList><service>
<serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType><controlURL>/ctl</controlURL></service></serviceList></device></root>"""


def router(outside, refuse_forever=False):
    seen = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(DESC.encode())

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            action = self.headers["SOAPAction"].strip('"').split("#")[1]
            seen.append((action, body))
            if action == "AddPortMapping" and refuse_forever and "<NewLeaseDuration>0<" in body:
                self.send_response(500); self.end_headers()
                self.wfile.write(b"<errorCode>725</errorCode>"); return
            self.send_response(200); self.end_headers()
            if action == "GetExternalIPAddress":
                self.wfile.write(f"<NewExternalIPAddress>{outside}</NewExternalIPAddress>".encode())
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen, f"http://127.0.0.1:{srv.server_port}/desc.xml"


class PortMapTests(unittest.TestCase):
    def test_opens_and_reports_public_address(self):
        srv, seen, loc = router("93.184.216.34")
        self.addCleanup(srv.shutdown)
        r = portmap.open_port(8765, 2, [loc], "192.168.1.5")
        self.assertEqual("mapped", r["state"])
        self.assertEqual("93.184.216.34", r["external_ip"])
        add = [b for a, b in seen if a == "AddPortMapping"][0]
        self.assertIn("<NewInternalClient>192.168.1.5<", add)
        self.assertIn("<NewExternalPort>8765<", add)

    def test_shared_provider_address_is_not_reachable_and_mapping_removed(self):
        srv, seen, loc = router("100.72.1.9")
        self.addCleanup(srv.shutdown)
        r = portmap.open_port(8765, 2, [loc], "192.168.1.5")
        self.assertEqual("not_reachable", r["state"])
        self.assertEqual("cgnat", r["kind"])
        self.assertIn("DeletePortMapping", [a for a, _ in seen])

    def test_router_that_refuses_forever_gets_a_lease(self):
        srv, seen, loc = router("93.184.216.34", refuse_forever=True)
        self.addCleanup(srv.shutdown)
        self.assertEqual("mapped", portmap.open_port(8765, 2, [loc], "192.168.1.5")["state"])

    def test_no_router(self):
        r = portmap.open_port(8765, 1, [], "192.168.1.5")
        self.assertEqual("no_router", r["state"])

    def test_kinds(self):
        self.assertEqual("cgnat", portmap.address_kind("100.64.3.3"))
        self.assertEqual("private", portmap.address_kind("192.168.0.9"))
        self.assertEqual("public", portmap.address_kind("8.8.8.8"))


if __name__ == "__main__":
    unittest.main()
