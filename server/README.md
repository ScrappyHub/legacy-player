# Legacy Player Self-Hosted Server

The first server implementation is a private, in-memory coordination service. It
manages session creation, join codes, participant credentials, compatibility checks,
the ready barrier, and frame-numbered input lockstep.

Start it from the repository root:

```powershell
python -m server.api.json_server --host 127.0.0.1 --port 8765
```

The wire format is newline-delimited JSON. Every response is either
`{"ok":true,"result":...}` or `{"ok":false,"error":"..."}`.

Supported operations are `create`, `join`, `validate`, `ready`, `input`, `poll`, and
`status`. Create returns a private join code and host credential. Join returns a
participant credential. All later operations require the session ID, participant ID,
and that participant's credential.

This server intentionally binds to localhost by default. It currently stores state
in memory, writes finalized replays beneath `artifacts/replays`, has no TLS, and has
no persistent identity system. Non-loopback binding is rejected unless
`--allow-insecure-remote` is supplied. Do not expose it to the public internet
directly; place remote deployments behind an authenticated, encrypted transport.

Released frame bundles are retained for the most recent 1,024 frames so every peer
can poll and inject the identical ordered input set. Dolphin controller injection is
the next adapter-specific implementation step.


## Hosting, invites and notifications (Phase 1)

Run on Windows, Linux or a Raspberry Pi with Python 3.11+ and no extra packages:

```
python -m server.cli start --detach     # run ONE of these at a time, not all four; add --host 0.0.0.0 --tls-cert c.pem --tls-key k.pem to host for friends
python -m server.cli status
python -m server.cli restart
python -m server.cli stop               # graceful: notifies players, saves lobby state
```

Stopping saves lobby state under `artifacts/state` (override with `--state-dir`); the next
`start` resumes it. Seats, credentials, invite codes and notifications survive. An active
match returns to the ready barrier so players re-ready and reload emulator state. Frame
streams themselves are not snapshotted.

Internet hosting requires TLS (`--tls-cert/--tls-key`); a self-signed certificate is enough
for a private group: `openssl req -x509 -newkey rsa:2048 -nodes -keyout k.pem -out c.pem -days 365 -subj /CN=legacy-player`.
Without TLS the server only binds loopback unless `--allow-insecure-remote` is given.

Players join with a short invite code (`XXXXX-XXXXX`, expires in 15 minutes by default,
use-limited, revocable). Create a session with `"require_approval": true` and the host gets a
`join_requested` notification and answers with `decide_join`. Clients call `events` with
`after_seq` to receive: `participant_joined`, `participant_left`, `participant_kicked`,
`participant_disconnected`, `participant_reconnected`, `join_requested` (host only),
`session_resumed` and `server_stopping`. Any authenticated call counts as a heartbeat; silent
players are flagged disconnected after 45 seconds. A kicked player's next call returns
`kicked from session: <reason>`. Kicking someone mid-match fails the match (lockstep needs
every input) and finalizes the replay.
