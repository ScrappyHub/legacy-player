from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import signal
import ssl
import sys
import time
from pathlib import Path

from server.api.control import ServerControl
from server.lobby import LobbyError, LobbyService
from server.lobby.invites import InviteBook
from server.lobby.throttle import key_for
from server.relay import Relay
from server.state_store import StateStore


MAX_REQUEST_BYTES = 64 * 1024
MAX_REQUESTS_PER_CONNECTION = 256
CLIENT_IDLE_SECONDS = 30
CONNECTION_LIFETIME_SECONDS = 120     # a request/answer connection (not a relay pipe) lives at most this long in total
MAX_FAILED_IN_A_ROW = 8               # this many refused or unreadable requests in a row and the connection is closed
MAX_CONNECTIONS_PER_IP = 16
SHUTDOWN_WAIT_SECONDS = 5.0
_PER_IP: dict[str, int] = {}          # keyed like the lobby's throttle: an IPv4 address, or an IPv6 /64 (one household)


def _log(line: str) -> None:
    """The server's own log line. Never a client address or anything a client sent."""
    try:
        print(f"Legacy Player server: {line}", file=sys.stderr, flush=True)
    except Exception:
        pass


def _is_loopback(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    return (mapped or ip).is_loopback


def _from_this_machine(writer: asyncio.StreamWriter) -> bool:
    """Loopback, or a connection whose source is the very address it arrived on (this computer talking to its own
    non-loopback address: nobody else can have that source address and finish a TCP handshake)."""
    peer = writer.get_extra_info("peername")
    host = peer[0] if peer else ""
    if _is_loopback(host):
        return True
    local = writer.get_extra_info("sockname")
    try:
        return bool(host) and bool(local) and ipaddress.ip_address(host) == ipaddress.ip_address(local[0])
    except ValueError:
        return False


def _send(writer: asyncio.StreamWriter, response: dict) -> None:
    writer.write(json.dumps(response, separators=(",", ":")).encode() + b"\n")


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    service: LobbyService,
    connection_limit: asyncio.Semaphore | None = None,
    control: ServerControl | None = None,
    relay: Relay | None = None,
    tracked: set | None = None,
) -> None:
    peer = writer.get_extra_info("peername")
    ip = peer[0] if peer else ""
    ip_key = key_for(ip)
    counted = False
    if tracked is not None:
        tracked.add(writer)
    if connection_limit is not None:
        if connection_limit.locked():                        # full: say so at once instead of queueing every stranger forever
            writer.write(b'{"ok":false,"error":"the server is busy, try again in a moment"}\n')
            try:
                await writer.drain()
            except (OSError, ConnectionError):
                pass
            writer.close()
            if tracked is not None:
                tracked.discard(writer)
            return
        await connection_limit.acquire()
    if ip_key is not None:
        if _PER_IP.get(ip_key, 0) >= MAX_CONNECTIONS_PER_IP:     # one address (or one IPv6 household) cannot hold every slot
            if connection_limit is not None:
                connection_limit.release()
            writer.close()
            if tracked is not None:
                tracked.discard(writer)
            return
        _PER_IP[ip_key] = _PER_IP.get(ip_key, 0) + 1
        counted = True
    loop = asyncio.get_running_loop()
    deadline = loop.time() + CONNECTION_LIFETIME_SECONDS
    try:
        request_count = 0
        failed_in_a_row = 0
        while True:
            left = deadline - loop.time()
            if left <= 0:
                break
            try:
                line = await asyncio.wait_for(reader.readline(), min(CLIENT_IDLE_SECONDS, left))
            except (TimeoutError, asyncio.TimeoutError):
                break
            except ValueError:
                _send(writer, {"ok": False, "error": "request is too large"})
                await writer.drain()
                break
            except (OSError, ConnectionError, ssl.SSLError):
                break
            if not line:
                break
            request_count += 1
            if request_count > MAX_REQUESTS_PER_CONNECTION:
                _send(writer, {"ok": False, "error": "connection request limit reached"})
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
                    if relay is not None and request.get("operation") == "punch" and request_count == 1:
                        if connection_limit is not None:
                            connection_limit.release()
                            connection_limit = None
                        await relay.handle_punch(request, reader, writer)
                        return
                    if control is not None and control.is_admin_operation(request.get("operation")):
                        response = {
                            "ok": True,
                            "result": control.handle(request, peer_is_loopback=_from_this_machine(writer)),
                        }
                    else:
                        response = {"ok": True, "result": service.dispatch(request)}
                except PermissionError as exc:
                    response = {"ok": False, "error": str(exc)}
                except (json.JSONDecodeError, LobbyError) as exc:
                    response = {"ok": False, "error": str(exc)}
                except Exception:                      # anything else (huge numbers, odd types, deep nesting): a plain no
                    response = {"ok": False, "error": "bad request"}
            failed_in_a_row = 0 if response.get("ok") else failed_in_a_row + 1
            _send(writer, response)
            await writer.drain()
            if failed_in_a_row >= MAX_FAILED_IN_A_ROW:
                break
    except (OSError, ConnectionError, ssl.SSLError):
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, ConnectionError, ssl.SSLError):
            pass
        except Exception:
            pass
        if connection_limit is not None:
            connection_limit.release()
        if counted:
            _PER_IP[ip_key] = max(0, _PER_IP.get(ip_key, 1) - 1)
            if not _PER_IP[ip_key]:
                _PER_IP.pop(ip_key, None)
        if tracked is not None:
            tracked.discard(writer)


async def _periodic(seconds: float, action, name: str = "background task") -> None:
    while True:
        await asyncio.sleep(seconds)
        try:
            action()
        except Exception as exc:          # one failure (an antivirus holding the snapshot file) must not stop it for good
            _log(f"{name} failed ({type(exc).__name__}); will try again")


def _new_service(store: StateStore, replay_dir: Path, heartbeat_timeout: float, max_players: int, max_rooms: int,
                 max_waiting: int) -> LobbyService:
    return LobbyService(
        replay_dir=replay_dir,
        heartbeat_timeout=heartbeat_timeout,
        max_participants=max_players,
        max_sessions=max_rooms,
        max_waiting=max_waiting,
        invite_book=InviteBook(pepper=store.pepper(), clock=time.time),
    )


def _loopback_for(host: str) -> str | None:
    """The loopback address to listen on as well when bound to one specific address, so local admin calls work."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return None if host.lower() == "localhost" else "127.0.0.1"
    if ip.is_loopback or ip.is_unspecified:
        return None
    return "::1" if ip.version == 6 else "127.0.0.1"


async def drop_connections(server, relay: Relay | None, tracked: set) -> None:
    """Close the listener and every open connection (parked relay slots included), and wait a bounded time.
    Since Python 3.12 wait_closed() waits for every connection, so one parked relay could keep the process alive."""
    server.close()
    if relay is not None:
        for sid in list(relay.parked) + list(relay.punch_parked):
            try:
                relay.drop_session(sid)
            except Exception:
                pass
    for writer in list(tracked):
        try:
            writer.close()
        except Exception:
            pass
    close_clients = getattr(server, "close_clients", None)        # 3.13+
    if close_clients is not None:
        try:
            close_clients()
        except Exception:
            pass
    try:
        await asyncio.wait_for(server.wait_closed(), SHUTDOWN_WAIT_SECONDS)
    except (asyncio.TimeoutError, TimeoutError):
        abort = getattr(server, "abort_clients", None)
        if abort is not None:
            abort()


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
    service = _new_service(store, replay_dir, heartbeat_timeout, max_players, max_rooms, max_waiting)
    snapshot = store.load_snapshot()
    if snapshot is not None:
        try:
            service.import_state(snapshot)
            print(f"Resumed {len(service.sessions)} session(s) from the saved lobby state")
        except Exception as exc:          # parses but can't be used (another version, a missing part): start empty
            _log(f"the saved lobby state could not be used ({type(exc).__name__}); kept it as "
                 "lobby_state.json.corrupt and started with no rooms")
            store.quarantine_snapshot()
            service = _new_service(store, replay_dir, heartbeat_timeout, max_players, max_rooms, max_waiting)
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
    tracked: set = set()

    async def listen(where):
        return await asyncio.start_server(
            lambda reader, writer: handle_client(reader, writer, service, connection_limit, control, relay, tracked),
            where,
            port,
            limit=MAX_REQUEST_BYTES * 2,
            ssl=ssl_context,
            ssl_handshake_timeout=8 if ssl_context is not None else None,      # a stranger that never finishes the handshake cannot hold a slot
        )
    server = None
    if host == "0.0.0.0":          # shared server: listen on IPv6 too, so players on IPv6 need no router setup at all
        try:
            server = await listen(["0.0.0.0", "::"])
        except OSError:            # no IPv6 on this machine: IPv4 only, as before
            server = None
    elif _loopback_for(host) is not None and port:
        # Bound to one specific address: listen on loopback too, so `stop`/`status` (which only talk to loopback) reach it.
        try:
            server = await listen([host, _loopback_for(host)])
        except OSError:            # loopback port taken: the specific address alone (admin calls fall back to it)
            server = None
    if server is None:
        server = await listen(host)
    bound = server.sockets[0].getsockname()
    store.write_info(
        {"host": host, "port": bound[1], "tls": ssl_context is not None, "started_at": time.time()}
    )
    addresses = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    mode = "TLS" if ssl_context else "plaintext"
    print(f"Legacy Player coordination server listening on {addresses} ({mode})", flush=True)

    loop = asyncio.get_running_loop()
    # asyncio's own error reports can name the connection; write only what kind of error it was
    loop.set_exception_handler(lambda _loop, context: _log(
        f"background error ({type(context.get('exception')).__name__ if context.get('exception') else 'no exception'})"))
    for name in ("SIGINT", "SIGTERM"):
        try:
            loop.add_signal_handler(getattr(signal, name), shutdown.set)
        except (NotImplementedError, AttributeError, ValueError):
            pass  # Windows: use `python -m server.cli stop` or Ctrl+C

    background = [
        asyncio.create_task(_periodic(5.0, service.sweep_disconnected, "sweep")),
        asyncio.create_task(_periodic(autosave_seconds, lambda: store.save_snapshot(service.export_state()), "autosave")),
    ]
    try:
        await shutdown.wait()
    except asyncio.CancelledError:
        pass
    finally:
        for task in background:
            task.cancel()
        try:
            service.announce_stopping()
        except Exception as exc:
            _log(f"could not tell the rooms the server is stopping ({type(exc).__name__})")
        saved = True
        try:
            store.save_snapshot(service.export_state())
        except Exception as exc:
            saved = False
            _log(f"could not save the lobby state ({type(exc).__name__})")
        await drop_connections(server, relay, tracked)
        print("Legacy Player server stopped" + ("; lobby state saved" if saved else ""), flush=True)


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
