from __future__ import annotations

import hashlib
import ipaddress
import re
import secrets
import time
from dataclasses import asdict
from pathlib import Path

from runtime.desync import DesyncTracker
from runtime.replay import ReplayRecorder, ReplayStore
from runtime.session import Participant, Session, SessionError, SessionState
from runtime.sync import InputFrame, LockstepCoordinator, LockstepError

from .events import EventLog
from .invites import InviteBook, InviteError
from .throttle import FailureThrottle, wait_text


class LobbyError(RuntimeError):
    pass


class LobbyService:
    """In-memory coordination core used by the self-hosted wire server."""

    def __init__(
        self,
        *,
        max_sessions: int = 128,
        max_participants: int = 4,
        max_retained_sessions: int = 256,
        session_idle_seconds: float = 3600,
        replay_dir: Path | None = None,
        heartbeat_timeout: float = 45.0,
        max_pending_requests: int = 8,
        max_waiting: int = 16,
        waiting_timeout: float = 60.0,
        invite_book: InviteBook | None = None,
        clock=time.monotonic,
    ) -> None:
        self.clock = clock
        self.heartbeat_timeout = heartbeat_timeout
        self.max_pending_requests = max_pending_requests
        self.max_waiting = max_waiting
        self.lockstep_used: set[str] = set()
        self.relay = None   # set by the server; drop_session(sid) clears parked relay slots
        self.vacate_after_timeouts = 3  # a seat is freed after 3x the heartbeat timeout without a word
        self.waiting_timeout = waiting_timeout
        self.invites = invite_book if invite_book is not None else InviteBook()
        self.key_throttle = FailureThrottle(max_failures=8, window=60.0, lockout=300.0)
        self.events: dict[str, EventLog] = {}
        self.options: dict[str, dict] = {}
        self._psk: dict[str, str] = {}  # tunnel keys: memory only, never in snapshots
        self.pending: dict[str, dict[str, dict]] = {}
        self.removed: dict[tuple[str, str], str] = {}
        self.stats: dict[tuple[str, str], dict] = {}
        self.joined_at: dict[tuple[str, str], float] = {}
        self.established: set[tuple[str, str]] = set()   # players whose app reported a running match
        self.establish_grace = 180.0   # a seat someone is waiting for is freed if its holder never connects in this time
        self.aliases: dict[str, dict] = {}   # "alias#1234" (lowercase) -> {"install": id, "seen": clock time}
        self.alias_active_seconds = 900.0    # a name+tag is taken while its owner's app was heard from this recently
        self.last_seen: dict[tuple[str, str], float] = {}
        self.disconnected: set[tuple[str, str]] = set()
        self.max_sessions = max_sessions
        self.max_participants = max_participants
        self.max_retained_sessions = max_retained_sessions
        self.session_idle_seconds = session_idle_seconds
        self.sessions: dict[str, Session] = {}
        self.join_codes: dict[str, str] = {}
        self.credentials: dict[tuple[str, str], str] = {}
        self.coordinators: dict[str, LockstepCoordinator] = {}
        self.released_bundles: dict[str, list[dict]] = {}
        self.desync_trackers: dict[str, DesyncTracker] = {}
        self.recorders: dict[str, ReplayRecorder] = {}
        self.last_activity: dict[str, float] = {}
        self.replay_store = ReplayStore(replay_dir) if replay_dir is not None else None
        self.finalized_replays: dict[str, dict] = {}
        self.finalized_order: list[str] = []

    def create_session(self, request: dict) -> dict:
        self.expire_idle_sessions()
        active_count = sum(
            session.state not in {SessionState.COMPLETED, SessionState.FAILED}
            for session in self.sessions.values()
        )
        if active_count >= self.max_sessions:
            raise LobbyError("session capacity reached")
        host_id = self._required_text(request, "participant_id")
        profile = self._profile(request)
        session = Session(
            host_id=host_id,
            game_id=profile["game_id"],
            region=profile["region"],
            adapter_id=self._required_text(request, "adapter_id"),
            game_pack_id=self._required_text(request, "game_pack_id"),
        )
        session.participants[host_id].profile = profile
        join_code = secrets.token_urlsafe(24)
        credential = secrets.token_urlsafe(24)
        self.sessions[session.session_id] = session
        self.join_codes[session.session_id] = self._digest(join_code)
        self.credentials[(session.session_id, host_id)] = self._digest(credential)
        max_players = request.get("max_players", self.max_participants)
        if isinstance(max_players, bool) or not isinstance(max_players, int) or not 2 <= max_players <= self.max_participants:
            raise LobbyError(f"max_players must be a whole number from 2 to {self.max_participants}")
        label = str(request.get("label") or "")[:48].strip()
        if label and not re.fullmatch(r"[A-Za-z0-9 _.,'!?-]{1,48}", label):
            raise LobbyError("room label may only use letters, digits, spaces and . , ' ! ? - _")
        self.options[session.session_id] = {
            "require_approval": bool(request.get("require_approval", False)),
            "max_players": max_players,
            "open": bool(request.get("open", False)),   # listed publicly; anyone on the server may join or queue
            "label": label,
        }
        self.pending[session.session_id] = {}
        self.events[session.session_id] = EventLog()
        self.last_seen[(session.session_id, host_id)] = self.clock()
        invite_code, invite_info = self.invites.create(session.session_id)
        self.events[session.session_id].emit("session_created", host_id=host_id)
        self.last_activity[session.session_id] = self.clock()
        self.recorders[session.session_id] = ReplayRecorder(
            session.session_id,
            {
                "game_id": session.game_id,
                "region": session.region,
                "adapter_id": session.adapter_id,
                "game_pack_id": session.game_pack_id,
            },
        )
        self.recorders[session.session_id].record("session_created", session.as_dict())
        return {
            "session": session.as_dict(),
            "join_code": join_code,
            "invite_code": invite_code,
            "invite_expires_at": invite_info["expires_at"],
            "require_approval": self.options[session.session_id]["require_approval"],
            "max_players": max_players,
            "open": self.options[session.session_id]["open"],
            "credential": credential,
        }

    def join_session(self, request: dict) -> dict:
        """Join with a long join code (+ session_id) or a short invite code."""
        invite = request.get("invite_code")
        priority = False
        if invite is not None:
            try:
                session_id, priority = self.invites.redeem_ex(invite, request.get("_peer"))
            except InviteError as exc:
                raise LobbyError(str(exc)) from exc
            session = self.sessions.get(session_id)
            if session is None or session_id not in self.join_codes:
                raise LobbyError("invalid or expired invite code")
        elif request.get("open"):
            session = self._session(request)
            if not self.options.get(session.session_id, {}).get("open"):
                raise LobbyError("that room is private; you need an invite code")
        else:
            session = self._session(request)
            supplied = request.get("join_code")
            if session.session_id not in self.join_codes or not isinstance(
                supplied, str
            ) or not secrets.compare_digest(
                self._digest(supplied), self.join_codes[session.session_id]
            ):
                raise LobbyError("invalid join code")
        participant_id = self._required_text(request, "participant_id")
        profile = self._profile(request)
        if participant_id in session.participants:
            raise LobbyError(f"duplicate participant: {participant_id}")
        sid = session.session_id
        if session.state in {SessionState.COMPLETED, SessionState.FAILED}:
            raise LobbyError(f"cannot join session in state {session.state}")
        # Full room, or people already waiting: stand in line (nobody skips the queue).
        if self._free_slots(session) <= 0 or self._live_waiting(sid):
            return self._enqueue(session, participant_id, profile, priority)
        if session.state not in {SessionState.CREATED, SessionState.JOINING}:
            raise LobbyError(f"cannot join session in state {session.state}")
        if self.options[sid]["require_approval"]:
            queue = self.pending[sid]
            if participant_id in queue or len(queue) >= self.max_pending_requests:
                raise LobbyError("join request already pending or queue is full")
            request_token = secrets.token_urlsafe(24)
            queue[participant_id] = {
                "profile": profile,
                "token": self._digest(request_token),
                "status": "pending",
                "credential": None,
            }
            self.events[sid].emit(
                "join_requested", audience="host", participant_id=participant_id
            )
            self._touch(sid)
            return {"status": "pending", "session_id": sid, "request_token": request_token}
        credential = self._admit(session, participant_id, profile)
        return {"status": "joined", "session": session.as_dict(), "credential": credential}


    # -- waiting list -----------------------------------------------------------------
    def _capacity(self, sid: str) -> int:
        return self.options[sid].get("max_players", self.max_participants)

    def _live_waiting(self, sid: str) -> list[tuple[str, dict]]:
        """Waiting entries in turn order (priority first, then first come). Entries whose owner
        stopped checking in are dropped so a closed laptop cannot hold a place."""
        now = self.clock()
        queue = self.pending.get(sid, {})
        for pid, entry in list(queue.items()):
            if entry["status"] == "waiting" and now - entry.get("polled", now) > self.waiting_timeout:
                del queue[pid]
                self.events[sid].emit("waitlist_dropped", audience="host", participant_id=pid)
        waiting = [(pid, e) for pid, e in queue.items() if e["status"] == "waiting"]
        waiting.sort(key=lambda item: (-item[1].get("priority", 0), item[1].get("order", 0)))
        return waiting

    def _position(self, sid: str, participant_id: str) -> int:
        for index, (pid, _) in enumerate(self._live_waiting(sid), start=1):
            if pid == participant_id:
                return index
        return 0

    def _enqueue(self, session: Session, participant_id: str, profile: dict, priority: bool) -> dict:
        sid = session.session_id
        queue = self.pending[sid]
        if participant_id in queue:
            raise LobbyError("already waiting for a spot in this room")
        if self.max_waiting <= 0:
            raise LobbyError("this room is full and the server does not keep waiting lines")
        if len(self._live_waiting(sid)) >= self.max_waiting:
            raise LobbyError("the waiting list is full")
        token = secrets.token_urlsafe(24)
        order = max((e.get("order", 0) for e in queue.values()), default=0) + 1
        queue[participant_id] = {
            "profile": profile, "token": self._digest(token), "status": "waiting", "credential": None,
            "priority": 1 if priority else 0, "order": order, "polled": self.clock(),
        }
        position = self._position(sid, participant_id)
        self.events[sid].emit("waitlist_joined", audience="host", participant_id=participant_id,
                              position=position, priority=bool(priority))
        self._touch(sid)
        return {"status": "waiting", "session_id": sid, "request_token": token, "position": position,
                "priority": bool(priority), "capacity": self._capacity(sid)}

    def _free_slots(self, session: Session) -> int:
        sid = session.session_id
        reserved = sum(1 for e in self.pending.get(sid, {}).values() if e["status"] == "pending")
        return self._capacity(sid) - len(session.participants) - reserved

    def _advance_waiting(self, session: Session, participant_id: str, entry: dict) -> dict | None:
        """If this waiter's turn has come, let them in (or send them to the host for approval)."""
        sid = session.session_id
        if session.state not in {SessionState.CREATED, SessionState.JOINING}:
            return None
        waiting = self._live_waiting(sid)
        eligible = [pid for pid, _ in waiting[: max(self._free_slots(session), 0)]]
        if participant_id not in eligible:
            return None
        if self.options[sid]["require_approval"]:
            entry["status"] = "pending"
            self.events[sid].emit("join_requested", audience="host", participant_id=participant_id)
            return {"status": "pending"}
        entry["credential"] = self._admit(session, participant_id, entry["profile"])
        entry["status"] = "approved"
        return None  # the normal approved branch hands over the credential

    def set_priority(self, request: dict) -> dict:
        """Host moves a waiting person to the front group (or back to the normal line)."""
        session, host = self._authorized(request)
        self._require_host(session, host)
        target = self._required_text(request, "target_id")
        entry = self.pending[session.session_id].get(target)
        if entry is None or entry["status"] != "waiting":
            raise LobbyError("that person is not on the waiting list")
        entry["priority"] = 1 if request.get("priority", True) else 0
        self.events[session.session_id].emit("waitlist_priority", audience="host", participant_id=target,
                                             priority=bool(entry["priority"]))
        self._touch(session.session_id)
        return {"waiting": self._waiting_view(session.session_id)}

    def cancel_wait(self, request: dict) -> dict:
        """A waiting person steps out of line (needs the token they were given)."""
        session = self._session(request)
        participant_id = self._required_text(request, "participant_id")
        token = self._required_text(request, "request_token")
        entry = self.pending.get(session.session_id, {}).get(participant_id)
        if entry is None or not secrets.compare_digest(self._digest(token), entry["token"]):
            raise LobbyError("unknown join request")
        if entry["status"] in {"waiting", "pending"}:
            del self.pending[session.session_id][participant_id]
        return {"cancelled": True}

    def relay_authorize(self, request: dict):
        """A room member may use the room's relay while the room is live."""
        session, participant_id = self._authorized(request)
        if session.state in {SessionState.COMPLETED, SessionState.FAILED}:
            raise LobbyError("that room has ended")
        return session, participant_id

    def browse(self, request: dict) -> dict:
        """Public rooms on this server. Deliberately says nothing about who is inside:
        no names, no addresses, only the game and how full it is."""
        self.expire_idle_sessions()
        rooms = []
        for sid, session in self.sessions.items():
            opts = self.options.get(sid, {})
            if not opts.get("open") or session.state in {SessionState.COMPLETED, SessionState.FAILED}:
                continue
            rooms.append({
                "session_id": sid, "label": opts.get("label") or "", "game_id": session.game_id,
                "region": session.region, "adapter_id": session.adapter_id, "state": session.state.value,
                "players": len(session.participants), "max_players": self._capacity(sid),
                "waiting": len(self._live_waiting(sid)), "require_approval": bool(opts.get("require_approval")),
            })
        rooms.sort(key=lambda r: (r["players"] >= r["max_players"], r["waiting"], r["label"]))
        return {"rooms": rooms, "limits": self.limits()}

    def limits(self) -> dict:
        return {"max_players_per_room": self.max_participants, "max_rooms": self.max_sessions,
                "max_waiting_per_room": self.max_waiting}

    def set_open(self, request: dict) -> dict:
        session, host = self._authorized(request)
        self._require_host(session, host)
        self.options[session.session_id]["open"] = bool(request.get("open", True))
        self._touch(session.session_id)
        return {"open": self.options[session.session_id]["open"]}

    def list_waiting(self, request: dict) -> dict:
        session, host = self._authorized(request)
        self._require_host(session, host)
        return {"waiting": self._waiting_view(session.session_id), "capacity": self._capacity(session.session_id),
                "players": len(session.participants)}

    def _waiting_view(self, sid: str) -> list[dict]:
        return [{"participant_id": pid, "position": i, "priority": bool(e.get("priority"))}
                for i, (pid, e) in enumerate(self._live_waiting(sid), start=1)]

    def set_capacity(self, request: dict) -> dict:
        session, host = self._authorized(request)
        self._require_host(session, host)
        value = request.get("max_players")
        if isinstance(value, bool) or not isinstance(value, int) or not 2 <= value <= self.max_participants:
            raise LobbyError(f"max_players must be a whole number from 2 to {self.max_participants}")
        if value < len(session.participants):
            raise LobbyError("remove a player first: the room already has more people than that")
        self.options[session.session_id]["max_players"] = value
        self.events[session.session_id].emit("capacity_changed", max_players=value)
        self._touch(session.session_id)
        return {"max_players": value}

    def _admit(self, session: Session, participant_id: str, profile: dict) -> str:
        participant = Participant(participant_id, profile=profile)
        try:
            session.add_participant(participant)
        except SessionError as exc:
            raise LobbyError(str(exc)) from exc
        sid = session.session_id
        credential = secrets.token_urlsafe(24)
        self.credentials[(sid, participant_id)] = self._digest(credential)
        self.removed.pop((sid, participant_id), None)
        self.last_seen[(sid, participant_id)] = self.clock()
        self.joined_at[(sid, participant_id)] = self.clock()
        self._touch(sid)
        self.recorders[sid].record(
            "participant_joined", {"participant_id": participant_id, "profile": profile}
        )
        self.events[sid].emit("participant_joined", participant_id=participant_id)
        return credential

    def join_status(self, request: dict) -> dict:
        """Let a waiting requester collect the host's decision (credential shown once)."""
        session = self._session(request)
        participant_id = self._required_text(request, "participant_id")
        token = self._required_text(request, "request_token")
        entry = self.pending.get(session.session_id, {}).get(participant_id)
        if entry is None or not secrets.compare_digest(self._digest(token), entry["token"]):
            raise LobbyError("unknown join request")
        if entry["status"] == "waiting":
            entry["polled"] = self.clock()
            outcome = self._advance_waiting(session, participant_id, entry)
            if outcome is not None:
                return outcome
            if entry["status"] == "waiting":
                if session.state in {SessionState.COMPLETED, SessionState.FAILED}:
                    del self.pending[session.session_id][participant_id]
                    return {"status": "denied"}
                return {"status": "waiting", "position": self._position(session.session_id, participant_id),
                        "priority": bool(entry.get("priority")), "capacity": self._capacity(session.session_id),
                        "players": len(session.participants)}
        if entry["status"] == "approved":
            credential = entry["credential"]
            del self.pending[session.session_id][participant_id]
            return {"status": "approved", "session": session.as_dict(), "credential": credential}
        if entry["status"] == "denied":
            del self.pending[session.session_id][participant_id]
            return {"status": "denied"}
        return {"status": "pending"}

    def decide_join(self, request: dict) -> dict:
        session, host = self._authorized(request)
        self._require_host(session, host)
        target = self._required_text(request, "target_id")
        entry = self.pending[session.session_id].get(target)
        if entry is None or entry["status"] not in {"pending", "waiting"}:
            raise LobbyError("no pending request from that participant")
        approve = bool(request.get("approve", True))
        if not approve:
            entry["status"] = "denied"
            self.events[session.session_id].emit("join_denied", audience="host", participant_id=target)
            return {"decided": "denied"}
        was_waiting = entry["status"] == "waiting"
        held = sum(1 for pid, e in self.pending[session.session_id].items() if pid != target and e["status"] == "pending")
        if len(session.participants) + held >= self._capacity(session.session_id):
            raise LobbyError("the room is full: remove a player or raise the player limit first")
        if was_waiting and session.state not in {SessionState.CREATED, SessionState.JOINING}:
            raise LobbyError("the room is locked; unlock it by removing someone, then try again")
        entry["credential"] = self._admit(session, target, entry["profile"])
        entry["status"] = "approved"
        return {"decided": "approved", "session": session.as_dict()}

    def create_invite(self, request: dict) -> dict:
        session, host = self._authorized(request)
        self._require_host(session, host)
        try:
            code, info = self.invites.create(
                session.session_id,
                ttl_seconds=request.get("ttl_seconds", 900),
                max_uses=request.get("max_uses", 8),
                priority=bool(request.get("priority", False)),
            )
        except InviteError as exc:
            raise LobbyError(str(exc)) from exc
        self.events[session.session_id].emit("invite_created", audience="host")
        return {"invite_code": code, "expires_at": info["expires_at"], "max_uses": info["max_uses"],
                "priority": info["priority"]}

    def revoke_invites(self, request: dict) -> dict:
        session, host = self._authorized(request)
        self._require_host(session, host)
        count = self.invites.revoke_session(session.session_id)
        self.events[session.session_id].emit("invites_revoked", audience="host", count=count)
        return {"revoked": count}

    def kick(self, request: dict) -> dict:
        session, host = self._authorized(request)
        self._require_host(session, host)
        target = self._required_text(request, "target_id")
        if target == host:
            raise LobbyError("the host cannot be kicked")
        if target not in session.participants:
            raise LobbyError("unknown participant")
        reason = str(request.get("reason", "removed by host"))[:120]
        self._remove(session, target, reason=reason, kind="participant_kicked", by=host)
        return {"session": session.as_dict()}

    def leave(self, request: dict) -> dict:
        session, participant_id = self._authorized(request)
        if participant_id == session.host_id:
            raise LobbyError("the host ends the session with 'complete', not 'leave'")
        self._remove(session, participant_id, reason="left", kind="participant_left", by=participant_id)
        return {"left": True}

    def _remove(self, session: Session, participant_id: str, *, reason: str, kind: str, by: str) -> None:
        sid = session.session_id
        lockstep = sid in self.lockstep_used   # only rooms that actually stream frames through the server
        was_active = session.state == SessionState.ACTIVE and lockstep
        if was_active:
            # Lockstep needs every player's input; without resync the match cannot continue.
            session.participants.pop(participant_id, None)
            session.fail(f"{participant_id} {reason if kind == 'participant_left' else 'was removed'} during an active session")
            self.recorders[sid].record("session_failed", {"reason": session.failure_reason})
        elif session.state == SessionState.ACTIVE:
            # Emulator-native netplay (RetroArch, Dolphin) copes with a player dropping; the room
            # stays open so the seat can go to the next person in line.
            if participant_id == session.host_id:
                raise LobbyError("the host cannot be removed")
            session.participants.pop(participant_id, None)
        else:
            try:
                session.remove_participant(participant_id)
            except SessionError as exc:
                raise LobbyError(str(exc)) from exc
        self.credentials.pop((sid, participant_id), None)
        self.last_seen.pop((sid, participant_id), None)
        self.stats.pop((sid, participant_id), None)
        self.joined_at.pop((sid, participant_id), None)
        self.established.discard((sid, participant_id))
        self.disconnected.discard((sid, participant_id))
        self.removed[(sid, participant_id)] = (
            f"kicked from session: {reason}" if kind == "participant_kicked" else "you left the session"
        )
        self.recorders[sid].record(kind, {"participant_id": participant_id, "by": by, "reason": reason})
        self.events[sid].emit(kind, participant_id=participant_id, by=by, reason=reason)
        if self._live_waiting(sid):
            self.events[sid].emit("slot_opened", audience="host", waiting=len(self._live_waiting(sid)))
        self._touch(sid)
        if was_active:
            self._finalize_replay(sid)
            self._drop_secrets(sid)

    _HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.\-:]{0,251}[A-Za-z0-9])?$")

    def set_endpoint(self, request: dict) -> dict:
        """Host publishes where players should connect for emulator-native netplay."""
        session, host = self._authorized(request)
        self._require_host(session, host)
        if session.state not in {SessionState.READY_BARRIER, SessionState.ACTIVE}:
            raise LobbyError("check that everyone has a matching game before launching")
        kind = request.get("kind", "direct")
        address = "relay" if kind == "relay" else self._required_text(request, "address")
        if kind == "code":
            if not re.fullmatch(r"[A-Za-z0-9]{4,16}", address):
                raise LobbyError("host code must be 4-16 letters or digits")
            endpoint = {"kind": "code", "address": address}
        elif kind == "relay":
            endpoint = {"kind": "relay", "address": "relay"}
        elif kind == "direct":
            if not self._HOST_RE.match(address):
                raise LobbyError("address must be a hostname or IP address")
            port = self._required_int(request, "port", minimum=1)
            if port > 65535:
                raise LobbyError("port must be 1-65535")
            endpoint = {"kind": "direct", "address": address, "port": port}
        else:
            raise LobbyError("kind must be 'direct', 'code' or 'relay'")
        self.options[session.session_id]["endpoint"] = endpoint
        self.options[session.session_id]["endpoint_at"] = self.clock()
        if self.relay is not None:
            self.relay.drop_session(session.session_id)   # a fresh launch: old parked slots are stale
        psk = request.get("psk")
        if psk is None:
            self._psk.pop(session.session_id, None)
        else:
            if not isinstance(psk, str) or not re.fullmatch(r"[0-9a-f]{32,64}", psk):
                raise LobbyError("psk must be 32-64 lowercase hex characters")
            self._psk[session.session_id] = psk
        self.events[session.session_id].emit("endpoint_published", host_id=host, how=kind)
        self.recorders[session.session_id].record("endpoint_published", {"kind": kind})
        self._touch(session.session_id)
        return {"published": True}

    def get_endpoint(self, request: dict) -> dict:
        session, _ = self._authorized(request)
        endpoint = self.options[session.session_id].get("endpoint")
        if endpoint and session.session_id in self._psk:
            endpoint = {**endpoint, "psk": self._psk[session.session_id]}
        return {"endpoint": endpoint}

    def heartbeat(self, request: dict) -> dict:
        session, _ = self._authorized(request)
        return {"state": session.state.value, "server_time": time.time()}

    def poll_events(self, request: dict) -> dict:
        session, participant_id = self._authorized(request)
        after = request.get("after_seq", 0)
        if isinstance(after, bool) or not isinstance(after, int) or after < 0:
            raise LobbyError("after_seq must be a non-negative integer")
        return {
            "events": self.events[session.session_id].since(
                after, is_host=participant_id == session.host_id
            )
        }

    def sweep_disconnected(self) -> list[dict]:
        """Flag participants who stopped talking; call periodically from the server loop."""
        now = self.clock()
        flagged = []
        for key, seen in list(self.last_seen.items()):
            sid, participant_id = key
            session = self.sessions.get(sid)
            if session is None or session.state in {SessionState.COMPLETED, SessionState.FAILED}:
                continue
            if key not in self.disconnected and now - seen > self.heartbeat_timeout:
                self.disconnected.add(key)
                event = self.events[sid].emit(
                    "participant_disconnected", participant_id=participant_id
                )
                flagged.append(event)
            elif (key in self.disconnected and participant_id != session.host_id
                  and now - seen > self.heartbeat_timeout * self.vacate_after_timeouts):
                # Gone for good: free the seat so the waiting line can move.
                self._remove(session, participant_id, reason="connection lost", kind="participant_left", by="server")
        flagged += self._release_idle_seats(now)
        return flagged

    def _release_idle_seats(self, now: float) -> list[dict]:
        """A seat nobody is using must not block people in line. Once the host has launched, players who
        still have not connected to the match after the grace period lose their seat, but only when
        someone is actually waiting for one."""
        released = []
        for sid, session in list(self.sessions.items()):
            if session.state in {SessionState.COMPLETED, SessionState.FAILED}:
                continue
            launched = self.options.get(sid, {}).get("endpoint_at")
            if launched is None or not self._live_waiting(sid):
                continue
            for pid in list(session.participants):
                if pid == session.host_id or (sid, pid) in self.established:
                    continue
                since = max(launched, self.joined_at.get((sid, pid), launched))
                if now - since > self.establish_grace:
                    self._remove(session, pid, reason="seat released: not connected to the match in time",
                                 kind="participant_left", by="server")
                    released.append({"session_id": sid, "participant_id": pid})
        return released

    def announce_stopping(self) -> None:
        """Tell every live session the server is going down so clients can show it."""
        for sid, session in self.sessions.items():
            if session.state not in {SessionState.COMPLETED, SessionState.FAILED}:
                self.events[sid].emit("server_stopping")

    def export_state(self) -> dict:
        """Snapshot everything needed to resume lobbies after a stop or restart.

        Secrets (join codes, credentials, invites) are stored only as digests.
        Live frame streams are not snapshotted; see import_state.
        """
        return {
            "schema": "legacy_player.lobby_state.v1",
            "sessions": {sid: s.as_dict() for sid, s in self.sessions.items()},
            "join_codes": dict(self.join_codes),
            "credentials": {f"{sid}|{pid}": h for (sid, pid), h in self.credentials.items()},
            "removed": {f"{sid}|{pid}": r for (sid, pid), r in self.removed.items()},
            "options": self.options,
            "pending": self.pending,
            "events": {sid: log.export() for sid, log in self.events.items()},
            "invites": self.invites.export(),
            "recorders": {
                sid: {
                    "metadata": r.metadata,
                    "events": r.events,
                    "started_at_utc": r.started_at_utc,
                }
                for sid, r in self.recorders.items()
            },
            "finalized_replays": self.finalized_replays,
            "finalized_order": self.finalized_order,
        }

    def import_state(self, data: dict) -> None:
        """Restore a snapshot. Active matches return to the ready barrier.

        Lockstep frames live only in memory, so an interrupted active session
        cannot silently continue mid-frame: players keep their seats and
        credentials, then re-ready (and reload their emulator state) to resume.
        """
        if data.get("schema") != "legacy_player.lobby_state.v1":
            raise LobbyError("unsupported lobby snapshot")
        now = self.clock()
        self.sessions = {sid: Session.from_dict(d) for sid, d in data["sessions"].items()}
        self.join_codes = dict(data["join_codes"])
        self.credentials = {tuple(k.split("|", 1)): v for k, v in data["credentials"].items()}
        self.removed = {tuple(k.split("|", 1)): v for k, v in data["removed"].items()}
        self.options = data["options"]
        self.pending = data["pending"]
        for queue in self.pending.values():
            for entry in queue.values():
                entry["polled"] = now  # monotonic stamps do not survive a restart
        self.events = {sid: EventLog.restore(d) for sid, d in data["events"].items()}
        self.invites.load(data["invites"])
        self.finalized_replays = data["finalized_replays"]
        self.finalized_order = list(data["finalized_order"])
        self.recorders = {}
        for sid, rec in data["recorders"].items():
            recorder = ReplayRecorder(sid, rec["metadata"])
            recorder.events = list(rec["events"])
            recorder.started_at_utc = rec["started_at_utc"]
            self.recorders[sid] = recorder
        self.coordinators, self.released_bundles, self.desync_trackers = {}, {}, {}
        self.disconnected = set()
        self.last_seen, self.last_activity = {}, {}
        for sid, session in self.sessions.items():
            self.last_activity[sid] = now
            for pid in session.participants:
                self.last_seen[(sid, pid)] = now  # grace period after a restart
            if session.state == SessionState.ACTIVE:
                session.reopen_barrier()
                self.recorders[sid].record("session_resumed", {"reason": "server restart"})
                self.events[sid].emit("session_resumed", reason="server restart")

    def _require_host(self, session: Session, participant_id: str) -> None:
        if participant_id != session.host_id:
            raise LobbyError("only the host can do that")

    def _digest(self, value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def validate_session(self, request: dict) -> dict:
        session, participant_id = self._authorized(request)
        if participant_id != session.host_id:
            raise LobbyError("only the host can validate the session")
        if session.state in {SessionState.READY_BARRIER, SessionState.ACTIVE}:
            return {"session": session.as_dict()}                  # already checked: pressing it again, or Start after Check, is fine
        # A different copy of the game must not kill the room (a failed session cannot be repaired): say who differs and leave
        # the room open so they can pick the right file and rejoin.
        if len(session.participants) >= 2:
            def pretty(game_id: str, region: str) -> str:
                parts = str(game_id).split(":")
                title = (parts[1] if len(parts) > 1 else parts[0]).replace("-", " ")
                return f"{title} ({region})"
            mine = pretty(session.game_id, session.region)
            odd = [f"{p.participant_id} has {pretty(p.profile.get('game_id', '?'), p.profile.get('region', '?'))}"
                   for p in session.participants.values()
                   if p.profile.get("game_id") != session.game_id or p.profile.get("region") != session.region]
            if odd:
                raise LobbyError(f"Not the same game: the host has {mine}; " + "; ".join(odd) +
                                 ". Everyone needs the same game and region (the same disc dump is best). "
                                 "Rename or pick the matching file, then try again.")
        try:
            session.begin_validation()
        except SessionError as exc:
            raise LobbyError(str(exc)) from exc
        self._touch(session.session_id)
        self.recorders[session.session_id].record("session_validated")
        return {"session": session.as_dict()}

    def set_ready(self, request: dict) -> dict:
        session, participant_id = self._authorized(request)
        try:
            session.set_ready(participant_id, bool(request.get("ready", True)))
            if all(item.ready for item in session.participants.values()):
                session.activate()
                self.coordinators[session.session_id] = LockstepCoordinator(
                    set(session.participants)
                )
                self.released_bundles[session.session_id] = []
                self.desync_trackers[session.session_id] = DesyncTracker(
                    set(session.participants)
                )
        except SessionError as exc:
            raise LobbyError(str(exc)) from exc
        self._touch(session.session_id)
        self.recorders[session.session_id].record(
            "participant_ready",
            {"participant_id": participant_id, "ready": bool(request.get("ready", True))},
        )
        if session.state == SessionState.ACTIVE:
            self.recorders[session.session_id].record("session_active")
        return {"session": session.as_dict()}

    def submit_input(self, request: dict) -> dict:
        session, participant_id = self._authorized(request)
        if session.state != SessionState.ACTIVE:
            raise LobbyError("session is not active")
        try:
            buttons = self._required_int(request, "buttons", minimum=0)
            if buttons > 0xFFFFFFFF:
                raise LobbyError("buttons must fit in an unsigned 32-bit field")
            item = InputFrame(
                frame=self._required_int(request, "frame", minimum=0),
                participant_id=participant_id,
                buttons=buttons,
                stick_x=int(request.get("stick_x", 0)),
                stick_y=int(request.get("stick_y", 0)),
            )
            self.lockstep_used.add(session.session_id)
            bundle = self.coordinators[session.session_id].submit(item)
        except (ValueError, LockstepError) as exc:
            raise LobbyError(str(exc)) from exc
        self._touch(session.session_id)
        serialized = (
            None
            if bundle is None
            else {
                "frame": bundle.frame,
                "inputs": [asdict(value) for value in bundle.inputs],
            }
        )
        if serialized is not None:
            history = self.released_bundles[session.session_id]
            history.append(serialized)
            del history[:-1024]
            self.recorders[session.session_id].record("frame_released", serialized)
        return {
            "released": bundle is not None,
            "bundle": serialized,
        }

    def poll_frames(self, request: dict) -> dict:
        session, _ = self._authorized(request)
        if session.state != SessionState.ACTIVE:
            raise LobbyError("session is not active")
        after_frame = request.get("after_frame", -1)
        if isinstance(after_frame, bool) or not isinstance(after_frame, int):
            raise LobbyError("after_frame must be an integer")
        bundles = [
            bundle
            for bundle in self.released_bundles[session.session_id]
            if bundle["frame"] > after_frame
        ]
        self._touch(session.session_id)
        return {"bundles": bundles}

    def submit_checkpoint(self, request: dict) -> dict:
        session, participant_id = self._authorized(request)
        if session.state != SessionState.ACTIVE:
            raise LobbyError("session is not active")
        try:
            result = self.desync_trackers[session.session_id].submit(
                self._required_int(request, "frame", minimum=0),
                participant_id,
                self._required_text(request, "state_hash"),
            )
        except (ValueError, RuntimeError) as exc:
            raise LobbyError(str(exc)) from exc
        payload = asdict(result)
        self._touch(session.session_id)
        self.recorders[session.session_id].record("state_checkpoint", payload)
        if result.complete and not result.matched:
            session.fail(f"desync detected at frame {result.frame}")
            self.recorders[session.session_id].record("desync_detected", payload)
            self._finalize_replay(session.session_id)
            self._drop_secrets(session.session_id)
        return {"checkpoint": payload, "session": session.as_dict()}

    def complete_session(self, request: dict) -> dict:
        session, participant_id = self._authorized(request)
        if participant_id != session.host_id:
            raise LobbyError("only the host can complete the session")
        try:
            session.complete()
        except SessionError as exc:
            raise LobbyError(str(exc)) from exc
        recorder = self.recorders[session.session_id]
        recorder.record("session_completed")
        replay = self._finalize_replay(session.session_id)
        self._drop_secrets(session.session_id)
        return {
            "session": session.as_dict(),
            "replay_summary": replay["summary"],
            "replay_path": replay["path"],
        }

    def status(self, request: dict) -> dict:
        session, _ = self._authorized(request)
        endpoint = self.options.get(session.session_id, {}).get("endpoint")
        return {"session": {**session.as_dict(), "endpoint_kind": endpoint["kind"] if endpoint else None},
                "stats": self._stats_view(session), "start": self._start_view(session)}

    # live numbers and "start together" -------------------------------------
    _STAT_LIMITS = {"ping_ms": 60000.0, "rx_kbps": 10_000_000.0, "tx_kbps": 10_000_000.0, "updates_per_s": 1000.0}

    def report_stats(self, request: dict) -> dict:
        """A member reports its own measurements. Only numbers are accepted; nothing about the machine."""
        session, participant_id = self._authorized(request)
        clean: dict[str, float] = {}
        for key, limit in self._STAT_LIMITS.items():
            value = request.get(key)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or not 0 <= value <= limit:
                raise LobbyError(f"{key} must be a number from 0 to {int(limit)}")
            clean[key] = round(float(value), 1)
        private = request.get("private_address")
        if private is not None:
            try:
                ok = ipaddress.ip_address(str(private)) in ipaddress.ip_network("100.64.0.0/10")
            except ValueError:
                ok = False
            if not ok:
                raise LobbyError("private_address must be a 100.x Tailscale address")
            clean["private_address"] = str(private)
        in_match = request.get("in_match")
        if in_match is not None:
            if not isinstance(in_match, bool):
                raise LobbyError("in_match must be true or false")
            if in_match:
                self.established.add((session.session_id, participant_id))
            else:
                self.established.discard((session.session_id, participant_id))
        clean["at"] = self.clock()
        self.stats[(session.session_id, participant_id)] = clean
        return {"ok": True}

    _ALIAS_RE = re.compile(r"^[A-Za-z0-9 _.\-]{1,24}$")

    def claim_alias(self, request: dict) -> dict:
        """Give a player a name#tag nobody else who is active right now has. Asking again with the same install
        id keeps the same tag. Nothing about the machine is sent: the install id is a random number the app made."""
        alias = str(request.get("alias") or "").strip()
        install = str(request.get("install_id") or "")
        if not self._ALIAS_RE.match(alias):
            raise LobbyError("a name is 1 to 24 letters, numbers, spaces, dots, dashes or underscores")
        if not re.fullmatch(r"[0-9a-f]{4,32}", install):
            raise LobbyError("install_id must be a short hex number")
        now = self.clock()
        for key in [k for k, v in self.aliases.items() if now - v["seen"] > self.alias_active_seconds]:
            del self.aliases[key]
        low = alias.lower()
        # an install keeps one name at a time: drop whatever it held before under another name
        for key in [k for k, v in self.aliases.items() if v["install"] == install and not k.startswith(low + "#")]:
            del self.aliases[key]
        wanted = str(request.get("tag") or "")
        mine = next((k for k, v in self.aliases.items() if v["install"] == install and k.startswith(low + "#")), None)
        if mine:
            tag = mine.split("#", 1)[1]
        else:
            taken = {k.split("#", 1)[1] for k in self.aliases if k.startswith(low + "#")}
            if re.fullmatch(r"\d{4}", wanted) and wanted not in taken:
                tag = wanted
            else:
                free = [f"{n:04d}" for n in range(10000) if f"{n:04d}" not in taken]
                if not free:
                    raise LobbyError("that name is used by too many active players; pick another")
                tag = secrets.choice(free)
        if f"{low}#{tag}" not in self.aliases and len(self.aliases) >= 50000:
            raise LobbyError("too many active names on this server")      # checked before adding, so a flood can not grow memory
        self.aliases[f"{low}#{tag}"] = {"install": install, "seen": now}
        return {"alias": alias, "tag": tag, "player": f"{alias}#{tag}"}

    def _stats_view(self, session: Session) -> dict:
        now = self.clock()
        people: dict[str, dict] = {}
        for pid in session.participants:
            row = self.stats.get((session.session_id, pid))
            if row and now - row["at"] < 30:
                people[pid] = {**{k: v for k, v in row.items() if k != "at"}, "connected": (session.session_id, pid) in self.established}
        average = {}
        for key in self._STAT_LIMITS:
            values = [r[key] for r in people.values() if key in r]
            if values:
                average[key] = round(sum(values) / len(values), 1)
        return {"people": people, "average": average}

    def set_game(self, request: dict) -> dict:
        """Host picks (or changes) the game the room will play. Guests are told and must re-confirm."""
        session, host = self._authorized(request)
        self._require_host(session, host)
        profile = self._profile(request)
        title = str(request.get("title", ""))[:120]
        session.participants[host].profile = profile
        self.options[session.session_id]["title"] = title
        self.options[session.session_id].pop("start", None)
        self.events[session.session_id].emit("game_changed", title=title or profile.get("game_id", ""))
        return {"session": session.as_dict()}

    def announce_start(self, request: dict) -> dict:
        """Host says "start now". Nothing launches for anyone else until they agree."""
        session, host = self._authorized(request)
        self._require_host(session, host)
        options = self.options[session.session_id]
        number = options.get("start", {}).get("id", 0) + 1
        options["start"] = {"id": number, "title": str(request.get("title", options.get("title", "")))[:120],
                            "at": self.clock(), "consented": [host]}
        self.events[session.session_id].emit("start_requested", title=options["start"]["title"], start_id=number)
        return {"start": self._start_view(session)}

    def consent_start(self, request: dict) -> dict:
        session, participant_id = self._authorized(request)
        start = self.options[session.session_id].get("start")
        if not start:
            raise LobbyError("the host has not asked to start yet")
        if request.get("start_id") != start["id"]:
            raise LobbyError("that start request is out of date")
        if participant_id not in start["consented"]:
            start["consented"].append(participant_id)
            self.events[session.session_id].emit("start_consented", participant_id=participant_id)
        return {"start": self._start_view(session)}

    def _start_view(self, session: Session) -> dict | None:
        start = self.options.get(session.session_id, {}).get("start")
        if not start:
            return None
        present = [p for p in start["consented"] if p in session.participants]
        return {"id": start["id"], "title": start["title"], "consented": present,
                "waiting_on": [p for p in session.participants if p not in present]}

    # What a brand-new person needs the server code's key for. Everything else needs a room credential they already hold.
    KEYED_OPERATIONS = frozenset({"create", "join", "browse", "claim_alias"})
    access_key: str | None = None      # set by the running server; None (tests, embedded use) means no key is required

    def dispatch(self, request: dict) -> dict:
        operation = request.get("operation")
        if self.access_key and operation in self.KEYED_OPERATIONS:
            peer = request.get("_peer")
            wait = self.key_throttle.blocked(peer)
            if wait:
                raise PermissionError(wait_text(wait))
            given = request.get("access_key")
            if not isinstance(given, str) or not secrets.compare_digest(given, self.access_key):
                self.key_throttle.fail(peer)
                raise PermissionError("This server code is out of date or not right. Ask the host for a fresh one.")
        handlers = {
            "create": self.create_session,
            "join": self.join_session,
            "validate": self.validate_session,
            "ready": self.set_ready,
            "input": self.submit_input,
            "poll": self.poll_frames,
            "checkpoint": self.submit_checkpoint,
            "complete": self.complete_session,
            "status": self.status,
            "join_status": self.join_status,
            "decide_join": self.decide_join,
            "invite": self.create_invite,
            "revoke_invites": self.revoke_invites,
            "kick": self.kick,
            "leave": self.leave,
            "heartbeat": self.heartbeat,
            "set_priority": self.set_priority,
            "list_waiting": self.list_waiting,
            "browse": self.browse,
            "set_open": self.set_open,
            "cancel_wait": self.cancel_wait,
            "set_capacity": self.set_capacity,
            "set_endpoint": self.set_endpoint,
            "get_endpoint": self.get_endpoint,
            "events": self.poll_events,
            "report_stats": self.report_stats,
            "announce_start": self.announce_start,
            "consent_start": self.consent_start,
            "set_game": self.set_game,
            "claim_alias": self.claim_alias,
        }
        try:
            handler = handlers[operation]
        except (KeyError, TypeError) as exc:
            raise LobbyError(f"unsupported operation: {operation!r}") from exc
        return handler(request)

    def _session(self, request: dict) -> Session:
        session_id = self._required_text(request, "session_id")
        try:
            return self.sessions[session_id]
        except KeyError as exc:
            raise LobbyError("unknown session") from exc

    def _authorized(self, request: dict) -> tuple[Session, str]:
        session = self._session(request)
        if self.clock() - self.last_activity.get(session.session_id, 0) > self.session_idle_seconds:
            self._expire(session)
            raise LobbyError("session expired due to inactivity")
        participant_id = self._required_text(request, "participant_id")
        credential = self._required_text(request, "credential")
        removed = self.removed.get((session.session_id, participant_id))
        if removed is not None:
            raise LobbyError(removed)
        if not secrets.compare_digest(
            self.credentials.get((session.session_id, participant_id), ""),
            self._digest(credential),
        ):
            raise LobbyError("invalid participant credential")
        key = (session.session_id, participant_id)
        self.last_seen[key] = self.clock()
        if key in self.disconnected:
            self.disconnected.discard(key)
            self.events[session.session_id].emit(
                "participant_reconnected", participant_id=participant_id
            )
        return session, participant_id

    def _touch(self, session_id: str) -> None:
        self.last_activity[session_id] = self.clock()

    def _drop_secrets(self, session_id: str) -> None:
        if self.relay is not None:
            self.relay.drop_session(session_id)
        self.join_codes.pop(session_id, None)
        self._psk.pop(session_id, None)
        self.invites.revoke_session(session_id)
        self.pending.pop(session_id, None)
        for key in [key for key in self.credentials if key[0] == session_id]:
            del self.credentials[key]

    def _finalize_replay(self, session_id: str) -> dict:
        existing = self.finalized_replays.get(session_id)
        if existing is not None:
            return existing
        package = self.recorders[session_id].package()
        replay_path = None
        if self.replay_store is not None:
            replay_path = str(self.replay_store.write(package))
        result = {
            "summary": {
                "schema": package["schema"],
                "session_id": package["session_id"],
                "event_count": package["event_count"],
                "finalized_at_utc": package["finalized_at_utc"],
            },
            "path": replay_path,
        }
        self.finalized_replays[session_id] = result
        self.finalized_order.append(session_id)
        self.coordinators.pop(session_id, None)
        self.released_bundles.pop(session_id, None)
        self.desync_trackers.pop(session_id, None)
        self.recorders.pop(session_id, None)
        while len(self.finalized_order) > self.max_retained_sessions:
            expired_id = self.finalized_order.pop(0)
            self.finalized_replays.pop(expired_id, None)
            self.sessions.pop(expired_id, None)
            self.last_activity.pop(expired_id, None)
        return result

    def _expire(self, session: Session) -> None:
        if session.state not in {SessionState.COMPLETED, SessionState.FAILED}:
            session.fail("session expired due to inactivity")
            self.recorders[session.session_id].record("session_expired")
            self._finalize_replay(session.session_id)
        self._drop_secrets(session.session_id)

    def expire_idle_sessions(self) -> None:
        now = self.clock()
        for session_id, session in list(self.sessions.items()):
            if now - self.last_activity.get(session_id, now) > self.session_idle_seconds:
                self._expire(session)

    @staticmethod
    def _required_text(request: dict, key: str) -> str:
        value = request.get(key)
        if not isinstance(value, str) or not value.strip():
            raise LobbyError(f"{key} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _required_int(request: dict, key: str, *, minimum: int) -> int:
        value = request.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise LobbyError(f"{key} must be an integer >= {minimum}")
        return value

    def _profile(self, request: dict) -> dict[str, str]:
        profile = request.get("profile")
        if not isinstance(profile, dict):
            raise LobbyError("profile must be an object")
        return {
            "game_id": self._required_text(profile, "game_id"),
            "region": self._required_text(profile, "region"),
        }
