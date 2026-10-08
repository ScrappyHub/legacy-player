"""How a friend can reach this computer without any extra program: a public IPv6 address, a router port opened by UPnP,
or a shared server. Read-only: it asks the operating system which addresses it has; nothing is sent anywhere."""
from __future__ import annotations

import ipaddress
import socket


def _global(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    return a.version == 6 and a.is_global and not a.is_multicast and not a.is_link_local


def _outbound_ipv6() -> str:
    """The IPv6 address this computer uses to reach the internet (no packet is sent: connect on UDP only picks a route)."""
    probe = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    try:
        probe.connect(("2001:4860:4860::8888", 9))
        return probe.getsockname()[0]
    except OSError:
        return ""
    finally:
        probe.close()


def global_ipv6() -> dict:
    """{"address": str, "available": bool}. Windows rotates a 'temporary' address for outgoing traffic; the stable one a friend
    should use is a different global address on the same computer, so that is preferred when there is one."""
    try:
        outbound = _outbound_ipv6()
    except OSError:
        outbound = ""
    if not _global(outbound):
        return {"available": False, "address": "", "stable": False}
    candidates: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET6):
            ip = info[4][0].split("%")[0]
            if _global(ip) and ip not in candidates:
                candidates.append(ip)
    except OSError:
        pass
    others = [c for c in candidates if c != outbound]
    if others:
        return {"available": True, "address": others[0], "stable": True}
    return {"available": True, "address": outbound, "stable": False}


def plan(ipv6: dict, port_state: str, shared_server: bool) -> list[dict]:
    """The ways a friend could connect, best first, in plain words."""
    routes = []
    if shared_server:
        routes.append({"key": "shared", "ok": True, "label": "A shared server",
                       "text": "You and your friend both connect out to it. No router setup, and it works even when your provider shares your address."})
    else:
        routes.append({"key": "shared", "ok": False, "label": "A shared server",
                       "text": "Not set up. This is the most reliable way: everyone connects out to one small always-on server. See docs/HOSTING_PUBLIC_SERVER.md."})
    routes.append({"key": "ipv6", "ok": bool(ipv6.get("available")), "label": "Direct over IPv6",
                   "text": ("This computer has a public IPv6 address. A friend who also has IPv6 can connect straight to it, with no router setup."
                            + ("" if ipv6.get("stable", True) else " The address may change from day to day, so send a fresh code each time.")) if ipv6.get("available")
                   else "No public IPv6 address here, so this route is not available."})
    routes.append({"key": "router", "ok": port_state == "mapped", "label": "Direct over IPv4 (router port)",
                   "text": {"mapped": "Your router opened the port. Friends can connect to your public address.",
                            "not_reachable": "Your provider shares one public address between customers, so this cannot work.",
                            }.get(port_state, "Not open. Turn on UPnP in the router or forward the port by hand, then press Test my router.")})
    return routes
