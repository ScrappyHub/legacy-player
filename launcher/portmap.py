"""Open the server's port on the home router by itself (UPnP), so a friend only needs the server code.

Most home routers answer a UPnP request from a program on the network: "please send TCP port N to this computer".
This module asks, reads back the router's public address, and removes the mapping again when the server stops.
It talks only to the router on the local network (SSDP multicast, then the router's own address); nothing leaves
the house. Routers that have UPnP turned off, and providers that share one public address between customers
(carrier-grade NAT, which includes most phone hotspots), cannot be opened this way; the result says which it was.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

SSDP_ADDR = ("239.255.255.250", 1900)
SEARCH_TARGETS = ("urn:schemas-upnp-org:device:InternetGatewayDevice:2", "urn:schemas-upnp-org:device:InternetGatewayDevice:1")
WAN_SERVICES = ("urn:schemas-upnp-org:service:WANIPConnection:2", "urn:schemas-upnp-org:service:WANIPConnection:1",
                "urn:schemas-upnp-org:service:WANPPPConnection:1")
DESCRIPTION = "Legacy Player server"


class PortMapError(Exception):
    pass


def address_kind(ip: str) -> str:
    """public | cgnat | private | unknown. A router whose own outside address is not public cannot be reached from outside."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return "unknown"
    if a in ipaddress.ip_network("100.64.0.0/10"):
        return "cgnat"
    if a.is_private or a.is_loopback or a.is_link_local or a.is_unspecified:
        return "private"
    return "public"


def _find_locations(timeout: float) -> list[str]:
    found: list[str] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.settimeout(0.5)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        for target in SEARCH_TARGETS:
            msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 1\r\nST: %s\r\n\r\n" % target).encode()
            try:
                sock.sendto(msg, SSDP_ADDR)
            except OSError:
                continue
        import time
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            match = re.search(r"^location:\s*(\S+)", data.decode("latin-1"), re.I | re.M)
            if match and match.group(1) not in found:
                found.append(match.group(1))
    finally:
        sock.close()
    return found


def _local_address_towards(host: str) -> str:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((host, 9))
        return probe.getsockname()[0]
    finally:
        probe.close()


class Gateway:
    """One UPnP router."""

    def __init__(self, location: str, timeout: float = 3.0) -> None:
        self.location, self.timeout = location, timeout
        self.control = ""
        self.service = ""
        self._describe()

    def _describe(self) -> None:
        try:
            with urllib.request.urlopen(self.location, timeout=self.timeout) as r:
                text = r.read(200_000).decode("utf-8", "replace")
        except (OSError, urllib.error.URLError) as exc:
            raise PortMapError("The router did not describe itself.") from exc
        text = re.sub(r'\sxmlns="[^"]+"', "", text, count=1)
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise PortMapError("The router's description could not be read.") from exc
        for svc in root.iter("service"):
            kind = (svc.findtext("serviceType") or "").strip()
            if kind in WAN_SERVICES:
                url = (svc.findtext("controlURL") or "").strip()
                if url:
                    self.service, self.control = kind, urllib.parse.urljoin(self.location, url)
                    return
        raise PortMapError("This router does not offer port mapping.")

    def _soap(self, action: str, args: dict) -> str:
        body = "".join(f"<{k}>{v}</{k}>" for k, v in args.items())
        envelope = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
                    f'<u:{action} xmlns:u="{self.service}">{body}</u:{action}></s:Body></s:Envelope>').encode()
        req = urllib.request.Request(self.control, envelope, {"Content-Type": 'text/xml; charset="utf-8"',
                                                              "SOAPAction": f'"{self.service}#{action}"'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.read(100_000).decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read(4000).decode("utf-8", "replace")
            code = re.search(r"<errorCode>(\d+)</errorCode>", detail)
            raise PortMapError("code " + (code.group(1) if code else str(exc.code))) from exc
        except (OSError, urllib.error.URLError) as exc:
            raise PortMapError("The router did not answer.") from exc

    def external_ip(self) -> str:
        text = self._soap("GetExternalIPAddress", {})
        match = re.search(r"<NewExternalIPAddress>([^<]*)</NewExternalIPAddress>", text)
        return match.group(1).strip() if match else ""

    def add(self, port: int, internal_ip: str, lease: int = 0) -> None:
        self._soap("AddPortMapping", {"NewRemoteHost": "", "NewExternalPort": port, "NewProtocol": "TCP", "NewInternalPort": port,
                                      "NewInternalClient": internal_ip, "NewEnabled": 1, "NewPortMappingDescription": DESCRIPTION,
                                      "NewLeaseDuration": lease})

    def delete(self, port: int) -> None:
        self._soap("DeletePortMapping", {"NewRemoteHost": "", "NewExternalPort": port, "NewProtocol": "TCP"})


def open_port(port: int, timeout: float = 4.0, locations: list[str] | None = None, local_ip: str | None = None) -> dict:
    """Ask the router to forward `port`. Never raises. state: mapped | not_reachable | no_router | refused."""
    last = "No router answered. UPnP may be switched off in the router's settings."
    for location in (locations if locations is not None else _find_locations(timeout)):
        try:
            gw = Gateway(location, timeout)
            host = urllib.parse.urlparse(location).hostname or ""
            mine = local_ip or _local_address_towards(host)
            try:
                gw.add(port, mine, 0)
            except PortMapError as exc:
                if "725" in str(exc):          # some routers refuse "forever"; take two hours
                    gw.add(port, mine, 7200)
                else:
                    raise
            outside = gw.external_ip()
        except (PortMapError, OSError) as exc:
            last = str(exc)
            continue
        kind = address_kind(outside)
        if kind != "public":
            try:
                gw.delete(port)
            except PortMapError:
                pass
            return {"state": "not_reachable", "external_ip": outside, "kind": kind, "location": location,
                    "message": "Your router's outside address is shared with other customers (or is not public), so people outside "
                               "your home cannot connect straight in. Friends can still join over a VPN, or through a relay server."}
        return {"state": "mapped", "external_ip": outside, "kind": "public", "location": location, "local_ip": mine, "port": port,
                "message": "Port opened on your router automatically. Friends can use your server code."}
    return {"state": "refused" if last.startswith("code") else "no_router", "external_ip": "", "kind": "unknown",
            "message": "Could not open the port on your router automatically (" + last + "). Turn on UPnP in the router, "
                       "or friends can use a VPN."}


def close_port(port: int, location: str, timeout: float = 4.0) -> bool:
    try:
        Gateway(location, timeout).delete(port)
        return True
    except (PortMapError, OSError):
        return False
