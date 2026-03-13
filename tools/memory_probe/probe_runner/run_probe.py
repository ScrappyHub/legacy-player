import uuid
from datetime import UTC, datetime

from tools.memory_probe.dolphin_attach.attach import find_dolphin_process
from tools.memory_probe.game_fingerprint.fingerprint import detect_game
from tools.memory_probe.state_sampler.sampler import run_sampler
from tools.memory_probe.log_writer.writer import LogWriter


def utc_now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def main():
    run_id = "probe-" + str(uuid.uuid4())[:8]
    writer = LogWriter(run_id)

    writer.emit({
        "ts": utc_now(),
        "kind": "session",
        "event": "probe_start",
    })

    proc = find_dolphin_process()

    if not proc:
        writer.emit({
            "ts": utc_now(),
            "kind": "error",
            "event": "dolphin_not_found",
        })
        return

    writer.emit({
        "ts": utc_now(),
        "kind": "session",
        "event": "attach_ok",
        "pid": proc.pid,
    })

    game = detect_game(proc)

    if game:
        writer.emit({
            "ts": utc_now(),
            "kind": "game",
            "event": "fingerprint_detected",
            "payload": game,
        })

        writer.emit({
            "ts": utc_now(),
            "kind": "phase",
            "event": "phase_hint_detected",
            "payload": {
                "phase_hint": game.get("phase_hint", "unknown"),
                "game_id": game.get("game_id", "unknown"),
                "region": game.get("region", "unknown"),
            },
        })
    else:
        writer.emit({
            "ts": utc_now(),
            "kind": "game",
            "event": "fingerprint_unknown",
        })

    run_sampler(proc, writer)

    writer.emit({
        "ts": utc_now(),
        "kind": "session",
        "event": "probe_complete",
    })


if __name__ == "__main__":
    main()