from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from adapters.controller import ControllerState
from adapters.dolphin.dsu_protocol import DsuServerProtocol, DsuVirtualPad, create_dsu_server
from runtime.client import CoordinationClient


class DolphinBridgeError(RuntimeError):
    pass


class DolphinDsuBridge:
    def __init__(self, participant_slots: dict[str, int]) -> None:
        if len(set(participant_slots.values())) != len(participant_slots):
            raise ValueError("controller slots must be unique")
        if any(slot not in range(4) for slot in participant_slots.values()):
            raise ValueError("Dolphin controller slots must be between 0 and 3")
        self.participant_slots = dict(participant_slots)
        self.pads = {slot: DsuVirtualPad(slot) for slot in participant_slots.values()}
        self.last_frame = -1

    @property
    def supports_frame_control(self) -> bool:
        return False

    def apply_bundle(self, bundle: dict, protocol: DsuServerProtocol) -> None:
        frame = int(bundle["frame"])
        if frame != self.last_frame + 1:
            raise DolphinBridgeError(
                f"non-contiguous frame bundle: expected {self.last_frame + 1}, got {frame}"
            )
        seen = set()
        for item in bundle.get("inputs", []):
            participant_id = item["participant_id"]
            if participant_id not in self.participant_slots:
                raise DolphinBridgeError(f"unmapped participant: {participant_id}")
            if participant_id in seen:
                raise DolphinBridgeError(f"duplicate participant in bundle: {participant_id}")
            seen.add(participant_id)
            slot = self.participant_slots[participant_id]
            self.pads[slot].update(
                ControllerState(
                    buttons=int(item["buttons"]),
                    stick_x=int(item.get("stick_x", 0)),
                    stick_y=int(item.get("stick_y", 0)),
                )
            )
            protocol.broadcast(slot)
        missing = set(self.participant_slots) - seen
        if missing:
            raise DolphinBridgeError(f"bundle is missing participants: {sorted(missing)}")
        self.last_frame = frame


async def run_bridge(args) -> None:
    slots = {}
    for mapping in args.map:
        participant_id, slot = mapping.rsplit(":", 1)
        slots[participant_id] = int(slot)
    bridge = DolphinDsuBridge(slots)
    transport, protocol = await create_dsu_server(args.dsu_host, args.dsu_port)
    protocol.pads = bridge.pads
    # one connection for the whole session (reopened if it drops), not a new one every poll
    client = CoordinationClient(args.server_host, args.server_port, persistent=True)
    credential = os.environ.get("LEGACY_PLAYER_CREDENTIAL")
    if args.credential_file is not None:
        credential = args.credential_file.read_text(encoding="utf-8").strip()
    if not credential:
        raise DolphinBridgeError(
            "set LEGACY_PLAYER_CREDENTIAL or provide --credential-file"
        )
    auth = {
        "session_id": args.session_id,
        "participant_id": args.participant_id,
        "credential": credential,
    }
    print(
        f"Dolphin DSU bridge listening on {args.dsu_host}:{args.dsu_port}; "
        "frame pause/resume is unavailable"
    )
    try:
        while True:
            result = await client.request(
                {"operation": "poll", **auth, "after_frame": bridge.last_frame}
            )
            for bundle in result["bundles"]:
                bridge.apply_bundle(bundle, protocol)
            await asyncio.sleep(args.poll_interval)
    finally:
        await client.close()
        transport.close()
        await protocol.wait_closed()


def main() -> None:
    parser = argparse.ArgumentParser(description="Relay lockstep bundles into Dolphin DSU pads")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--participant-id", required=True)
    parser.add_argument("--credential-file", type=Path)
    parser.add_argument("--map", action="append", required=True, metavar="PARTICIPANT:SLOT")
    parser.add_argument("--server-host", default="127.0.0.1")
    parser.add_argument("--server-port", type=int, default=8765)
    parser.add_argument("--dsu-host", default="127.0.0.1")
    parser.add_argument("--dsu-port", type=int, default=26760)
    parser.add_argument("--poll-interval", type=float, default=0.01)
    args = parser.parse_args()
    asyncio.run(run_bridge(args))


if __name__ == "__main__":
    main()
