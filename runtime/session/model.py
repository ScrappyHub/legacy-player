from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4


class SessionError(RuntimeError):
    pass


class SessionState(StrEnum):
    CREATED = "created"
    JOINING = "joining"
    VALIDATING = "validating"
    READY_BARRIER = "ready-barrier"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Participant:
    participant_id: str
    role: str = "peer"
    ready: bool = False
    profile: dict[str, str] = field(default_factory=dict)


@dataclass
class Session:
    host_id: str
    game_id: str
    region: str
    adapter_id: str
    game_pack_id: str
    session_id: str = field(default_factory=lambda: str(uuid4()))
    state: SessionState = SessionState.CREATED
    participants: dict[str, Participant] = field(default_factory=dict)
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        self.participants[self.host_id] = Participant(self.host_id, role="host")

    def add_participant(self, participant: Participant) -> None:
        if self.state not in {SessionState.CREATED, SessionState.JOINING}:
            raise SessionError(f"cannot join session in state {self.state}")
        if participant.participant_id in self.participants:
            raise SessionError(f"duplicate participant: {participant.participant_id}")
        self.participants[participant.participant_id] = participant
        self.state = SessionState.JOINING

    def remove_participant(self, participant_id: str) -> None:
        """Remove a non-host participant before the session is active."""
        if participant_id == self.host_id:
            raise SessionError("the host cannot be removed")
        if participant_id not in self.participants:
            raise SessionError(f"unknown participant: {participant_id}")
        if self.state in {SessionState.COMPLETED, SessionState.FAILED, SessionState.ACTIVE}:
            raise SessionError(f"cannot remove participant in state {self.state}")
        del self.participants[participant_id]
        if self.state in {SessionState.VALIDATING, SessionState.READY_BARRIER}:
            # Roster changed after validation: compatibility must be re-checked.
            for participant in self.participants.values():
                participant.ready = False
            self.state = SessionState.JOINING
        if len(self.participants) == 1 and self.state == SessionState.JOINING:
            self.state = SessionState.CREATED

    def reopen_barrier(self) -> None:
        """Return an interrupted active session to the ready barrier (server resume)."""
        if self.state != SessionState.ACTIVE:
            raise SessionError(f"cannot reopen session in state {self.state}")
        for participant in self.participants.values():
            participant.ready = False
        self.state = SessionState.READY_BARRIER

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        session = cls(
            host_id=data["host_id"],
            game_id=data["game_id"],
            region=data["region"],
            adapter_id=data["adapter_id"],
            game_pack_id=data["game_pack_id"],
            session_id=data["session_id"],
        )
        session.state = SessionState(data["state"])
        session.failure_reason = data.get("failure_reason")
        session.participants = {
            key: Participant(
                key,
                role=value.get("role", "peer"),
                ready=bool(value.get("ready", False)),
                profile=dict(value.get("profile", {})),
            )
            for key, value in data["participants"].items()
        }
        return session

    def begin_validation(self) -> None:
        if self.state not in {SessionState.CREATED, SessionState.JOINING}:
            raise SessionError(f"cannot validate session in state {self.state}")
        if len(self.participants) < 2:
            raise SessionError("at least two participants are required")
        expected = {"game_id": self.game_id, "region": self.region}
        for participant in self.participants.values():
            for key, value in expected.items():
                if participant.profile.get(key) != value:
                    self.fail(f"incompatible {key} for {participant.participant_id}")
                    raise SessionError(self.failure_reason or "compatibility failed")
        self.state = SessionState.READY_BARRIER

    def set_ready(self, participant_id: str, ready: bool = True) -> None:
        if self.state != SessionState.READY_BARRIER:
            raise SessionError(f"readiness is closed in state {self.state}")
        try:
            self.participants[participant_id].ready = ready
        except KeyError as exc:
            raise SessionError(f"unknown participant: {participant_id}") from exc

    def activate(self) -> None:
        if self.state != SessionState.READY_BARRIER:
            raise SessionError(f"cannot activate session in state {self.state}")
        if not all(participant.ready for participant in self.participants.values()):
            raise SessionError("ready barrier is incomplete")
        self.state = SessionState.ACTIVE

    def complete(self) -> None:
        if self.state != SessionState.ACTIVE:
            raise SessionError(f"cannot complete session in state {self.state}")
        self.state = SessionState.COMPLETED

    def fail(self, reason: str) -> None:
        if self.state in {SessionState.COMPLETED, SessionState.FAILED}:
            raise SessionError(f"cannot fail session in state {self.state}")
        self.failure_reason = reason
        self.state = SessionState.FAILED

    def as_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "host_id": self.host_id,
            "game_id": self.game_id,
            "region": self.region,
            "adapter_id": self.adapter_id,
            "game_pack_id": self.game_pack_id,
            "failure_reason": self.failure_reason,
            "participants": {
                key: {
                    "role": value.role,
                    "ready": value.ready,
                    "profile": value.profile,
                }
                for key, value in self.participants.items()
            },
        }
