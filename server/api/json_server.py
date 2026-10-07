from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import signal
import ssl
import time
from pathlib import Path

from server.api.control import ServerControl
from server.lobby import LobbyError, LobbyService
from server.lobby.invites import InviteBook
from server.relay import Relay
from server.state_store import StateStore


MAX_REQUEST_BYTES = 64 * 1024
MAX_REQUESTS_PER_CONNECTION = 256
CLIENT_IDLE_SECONDS = 30
MAX_CONNECTIONS_PER_IP = 16
_PER_IP: dict[str, int] = {}


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    service: LobbyService,
    connection_limit: asyncio.Semaphore | None = None,
    control: ServerControl | None = None,
    relay: Relay | None = None,
) -> None:
    peer = writer.get_extra_info("peername")
    ip = peer[0] if peer else ""
    counted = False
    if connection_limit is not None:
        if connection_limit.locked():                        # full: say so at once instead of queueing every stranger forever
            writer.write(b'{"ok":false,"error":"the server is busy, try again in a moment"}\n')
            try:
                await writer.drain()
            except (OSError, ConnectionError):
                pass
            writer.close()
            return
        await connection_limit.acquire()
    if ip and not _is_loopback(ip):
        if _PER_IP.get(ip, 0) >= MAX_CONNECTIONS_PER_IP:     # one address cannot hold every slot
            if connection_limit is not None:
                connection_limit.release()
            writer.close()
            return
        _PER_IP[ip] = _PER_IP.get(ip, 0) + 1
        counted = True
    try:
        request_count = 0
        while True:
            try:
                line = await asyncio.wait_for(reader.readline(), CLIENT_IDLE_SECONDS)
            except TimeoutError:
                break
            except ValueError:
                writer.write(b'{"ok":false,"error":"request is too large"}\n')
                await writer.drain()
                break
            if not line:
                break
            request_count += 1
            if request_count > MAX_REQUESTS_PER_CONNECTION:
                response = {"ok": False, "error": "connection request limit reached"}
                writer.write(json.dumps(response, separators=(",", ":")).encode() + b"\n")
                await writer.drain()
                break
            if len(line) > MAX_REQUEST_BYTES:
                response = {"ok": False, "error": "request is too large"}
            else:
                try:
                    request = json.loads(line)
                    if not isinstance(request, dict):
                        raise LobbyError("request must be a JSON object")
                    request["_peer"] = ip              # set here, never trusted from the client (it overwrites anything sent)
                    if relay is not None and request.get("operation") == "relay" and request_count == 1:
                        # This connection becomes a raw byte pipe; it is counted by the relay, not here.
                        if connection_limit is not None:
                            connection_limit.release()
                            connection_limit = None
                        await relay.handle(request, reader, writer)
                        return
                    if control is not None and control.is_admin_operation(request.get("operation")):
                        peer = writer.get_extra_info("peername")
                        host = peer[0] if peer else ""
                        try:
                            loopback = ipaddress.ip_address(host).is_loopback
                        except ValueError:
                            loopback = False
                        response = {
                            "ok": True,
                            "result": control.handle(request, peer_is_loopback=loopback),
                        }
                    else:
                        response = {"ok": True, "result": service.dispatch(request)}
                except PermissionError as exc:
                    response = {"ok": False, "error": str(exc)}
                except (json.JSONDecodeError, LobbyError) as exc:
                    response = {"ok": False, "error": str(exc)}
            writer.write(json.dumps(response, separators=(",", ":")).encode() + b"\n")
            await writer.drain()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, ConnectionError):
            pass
        if connection_limit is not None:
            connection_limit.release()
        if counted:
            _PER_IP[ip] = max(0, _PER_IP.get(ip, 1) - 1)
            if not _PER_IP[ip]:
                _PER_IP.pop(ip, None)


async def _periodic(seconds: float, action) -> None:
    while True:
        await asyncio.sleep(seconds)
        action()


async def serve(
    host: str,
    port: int,
    replay_dir: Path,
    *,
    state_dir: Path | None = None,
    tls_cert: Path | None = None,
    tls_key: Path | None = None,
    autosave_seconds: float = 15.0,
    heartbeat_timeout: float = 45.0,
    max_players: int = 4,
    max_rooms: int = 128,
    max_waiting: int = 16,
) -> None:
    store = StateStore(state_dir or Path("artifacts/state"))
    service = LobbyService(
        replay_dir=replay_dir,
        heartbeat_timeout=heartbeat_timeout,
        max_participants=max_players,
        max_sessions=max_rooms,
        max_waiting=max_waiting,
        invite_book=InviteBook(pepper=store.pepper(), clock=time.time),
    )
    snapshot = store.load_snapshot()
    if snapshot is not None:
        service.import_state(snapshot)
        print(f"Resumed {len(service.sessions)} session(s) from the saved lobby state")
    shutdown = asyncio.Event()
    service.access_key = store.access_key()
    control = ServerControl(store.admin_token(), shutdown, service, store)
    relay = Relay(service)
    service.relay = relay
    ssl_context = None
    if tls_cert is not None:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        ssl_context.load_cert_chain(tls_cert, tls_key)
    connection_limit = asyncio.Semaphore(128)
    server = await asyncio.start_server(
        lambda reader, writer: handle_client(reader, writer, service, connection_limit, control, relay),
        host,
        port,
        limit=MAX_REQUEST_BYTES * 2,
        ssl=ssl_context,
        ssl_handshake_timeout=8 if ssl_context is not None else None,      # a stranger that never finishes the handshake cannot hold a slot
    )
    bound = server.sockets[0].getsockname()
    store.write_info(
        {"host": host, "port": bound[1], "tls": ssl_context is not None, "started_at": time.time()}
    )
    addresses = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    mode = "TLS" if ssl_context else "plaintext"
    print(f"Legacy Player coordination server listening on {addresses} ({mode})", flush=True)

    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM"):
        try:
            loop.add_signal_handler(getattr(signal, name), shutdown.set)
        except (NotImplementedError, AttributeError, ValueError):
            pass  # Windows: use `python -m server.cli stop` or Ctrl+C

    background = [
        asyncio.create_task(_periodic(5.0, service.sweep_disconnected)),
        asyncio.create_task(_periodic(autosave_seconds, lambda: store.save_snapshot(service.export_state()))),
    ]
    try:
        await shutdown.wait()
    except asyncio.CancelledError:
        pass
    finally:
        service.announce_stopping()
        for task in background:
            task.cancel()
        store.save_snapshot(service.export_state())
        server.close()
        await server.wait_closed()
        print("Legacy Player server stopped; lobby state saved", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Legacy Player coordination server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--replay-dir", type=Path, default=Path("artifacts/replays"))
    parser.add_argument("--allow-insecure-remote", action="store_true")
    parser.add_argument("--state-dir", type=Path, default=Path("artifacts/state"))
    parser.add_argument("--tls-cert", type=Path)
    parser.add_argument("--tls-key", type=Path)
    parser.add_argument("--autosave-seconds", type=float, default=15.0)
    parser.add_argument("--heartbeat-timeout", type=float, default=45.0)
    parser.add_argument("--max-players", type=int, default=4, help="players per room (2-8)")
    parser.add_argument("--max-rooms", type=int, default=128, help="rooms this server will hold at once")
    parser.add_argument("--max-waiting", type=int, default=16, help="waiting-line length per room (0 = no line)")
    args = parser.parse_args()
    if not 2 <= args.max_players <= 8 or not 1 <= args.max_rooms <= 10000 or not 0 <= args.max_waiting <= 500:
        parser.error("--max-players 2-8, --max-rooms 1-10000, --max-waiting 0-500")
    if bool(args.tls_cert) != bool(args.tls_key):
        parser.error("--tls-cert and --tls-key must be given together")
    try:
        is_loopback = ipaddress.ip_address(args.host).is_loopback
    except ValueError:
        is_loopback = args.host.lower() == "localhost"
    if not is_loopback and not args.tls_cert and not args.allow_insecure_remote:
        parser.error("non-loopback binding requires --tls-cert/--tls-key (or --allow-insecure-remote)")
    try:
        asyncio.run(
            serve(
                args.host,
                args.port,
                args.replay_dir,
                state_dir=args.state_dir,
                tls_cert=args.tls_cert,
                tls_key=args.tls_key,
                autosave_seconds=args.autosave_seconds,
                heartbeat_timeout=args.heartbeat_timeout,
                max_players=args.max_players,
                max_rooms=args.max_rooms,
                max_waiting=args.max_waiting,
            )
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
