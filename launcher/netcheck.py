"""Is this computer's network ready to host or join? Measures only things on this machine and the
server the user already chose; it contacts nothing else and sends no personal information."""
from __future__ import annotations

import ipaddress
import socket
import statistics
import threading
import time


def classify_address(address: str) -> dict:
    """What kind of address is this? Decides whether friends outside the home network can reach it directly."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return {"kind": "unknown", "text": "Could not read this computer's address."}
    if ip.is_loopback:
        return {"kind": "loopback", "text": "This computer is not on a network right now (only its own loopback address)."}
    if ip in ipaddress.ip_network("100.64.0.0/10"):
        return {"kind": "cgnat", "text": "Your internet provider shares one public address between many customers (carrier-grade NAT), so friends cannot reach this computer directly."}
    if ip.is_private or ip.is_link_local:
        return {"kind": "private", "text": "This computer is on a home or office network. Friends on the same network or a VPN (Tailscale, ZeroTier) can reach it; friends elsewhere need your router to forward a port, or a server that relays for them."}
    return {"kind": "public", "text": "This computer has a public address, so friends can reach it directly if the port is open in your firewall."}


def loopback_test(rounds: int = 60, megabytes: int = 4) -> dict:
    """Mock hosting: a small echo server on this computer, to measure how fast it answers and carries data."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def serve() -> None:
        conn, _ = listener.accept()
        with conn:
            while data := conn.recv(65536):
                conn.sendall(data)
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    client = socket.create_connection(("127.0.0.1", port), timeout=5)
    client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    times = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        client.sendall(b"x" * 32)
        got = 0
        while got < 32:
            got += len(client.recv(32))
        times.append((time.perf_counter() - t0) * 1000)
    payload = b"y" * 65536
    total = megabytes * 1024 * 1024
    t0 = time.perf_counter()
    sent = recvd = 0
    client.setblocking(False)
    while recvd < total:
        try:
            if sent < total:
                sent += client.send(payload[: min(len(payload), total - sent)])
        except (BlockingIOError, InterruptedError):
            pass
        try:
            recvd += len(client.recv(65536))
        except (BlockingIOError, InterruptedError):
            time.sleep(0.0005)
        if time.perf_counter() - t0 > 10:
            break
    seconds = max(time.perf_counter() - t0, 1e-6)
    client.close()
    listener.close()
    return {"rtt_ms": round(statistics.mean(times), 3), "rtt_max_ms": round(max(times), 3),
            "mbps": round(recvd * 8 / 1e6 / seconds, 1)}


def room_load_test(players: int = 4, calls: int = 40) -> dict:
    """Mock a room: run the real lobby logic with several simulated players polling at once."""
    from server.lobby import LobbyService
    service = LobbyService()
    profile = {"game_id": "test:game", "region": "usa"}
    created = service.dispatch({"operation": "create", "participant_id": "host", "profile": profile,
                                "adapter_id": "retroarch", "game_pack_id": "generic", "require_approval": False,
                                "max_players": max(2, players)})
    sid = created["session"]["session_id"]
    creds = [("host", created["credential"])]
    for i in range(1, players):
        joined = service.dispatch({"operation": "join", "invite_code": created["invite_code"], "participant_id": f"p{i}", "profile": profile})
        creds.append((f"p{i}", joined["credential"]))
    times: list[float] = []
    lock = threading.Lock()

    def poll(pid: str, cred: str) -> None:
        for _ in range(calls):
            t0 = time.perf_counter()
            service.dispatch({"operation": "status", "session_id": sid, "participant_id": pid, "credential": cred})
            with lock:
                times.append((time.perf_counter() - t0) * 1000)
    t0 = time.perf_counter()
    threads = [threading.Thread(target=poll, args=c) for c in creds]
    [t.start() for t in threads]
    [t.join() for t in threads]
    elapsed = max(time.perf_counter() - t0, 1e-6)
    return {"players": players, "avg_ms": round(statistics.mean(times), 3), "requests_per_s": round(len(times) / elapsed)}


def ping_server(call, samples: int = 20) -> dict:
    """Round trips to the server the user chose. `call()` performs one tiny request."""
    times, lost = [], 0
    for _ in range(samples):
        t0 = time.perf_counter()
        try:
            call()
        except Exception:
            lost += 1
            continue
        finally:
            time.sleep(0.05)
        times.append((time.perf_counter() - t0) * 1000)
    if not times:
        return {"ok": False, "loss_pct": 100}
    return {"ok": True, "min_ms": round(min(times), 1), "avg_ms": round(statistics.mean(times), 1), "max_ms": round(max(times), 1),
            "jitter_ms": round(statistics.pstdev(times), 1), "loss_pct": round(lost * 100 / samples)}


def advise(address_kind: str, mock: dict, room: dict, server: dict | None, local_server: bool) -> dict:
    """Plain-language verdict: host here, or join someone else's server."""
    reasons: list[str] = []
    host_ok = True
    if mock["rtt_ms"] > 2 or mock["mbps"] < 100:
        host_ok = False
        reasons.append("This computer was slow to answer even to itself, so it may struggle to host while also running a game.")
    else:
        reasons.append("Hosting a room here is light: this computer handled %d simulated players at %d requests per second." % (room["players"], room["requests_per_s"]))
    if address_kind == "cgnat":
        host_ok = False
        reasons.append("Your provider shares one address between many customers, so a router port cannot reach this computer. Friends can still join through a shared server (a cheap rented one) or over IPv6 if you both have it.")
    elif address_kind == "private":
        reasons.append("Friends on your home network can join at once. For friends elsewhere, Legacy Player tries to open the port on your router by itself; Servers > How friends reach me shows what works here.")
    elif address_kind == "loopback":
        host_ok = False
        reasons.append("This computer is not on a network right now.")
    elif address_kind == "public":
        reasons.append("You have a public address, which makes this computer a good host once the port is open.")
    if server is not None and not local_server:
        if not server.get("ok"):
            reasons.append("The server you connect to did not answer.")
        else:
            avg = server["avg_ms"]
            quality = "excellent" if avg < 30 else "good" if avg < 60 else "fair" if avg < 100 else "poor"
            reasons.append(f"Your connection to that server is {quality}: {avg} ms average, {server['jitter_ms']} ms jitter, {server['loss_pct']}% lost.")
            if avg >= 100 or server["loss_pct"] >= 5:
                reasons.append("Matches will feel laggy. Ask someone closer to you, or with a wired connection, to host instead.")
    verdict = "host" if host_ok and address_kind in {"public"} else "either" if host_ok else "join"
    headline = {"host": "Good place to host.", "either": "You can host for people on your network or VPN, or join someone else.",
                "join": "Better to join someone else's server."}[verdict]
    return {"verdict": verdict, "headline": headline, "reasons": reasons}
