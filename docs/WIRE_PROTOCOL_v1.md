# Legacy Player Coordination Protocol v1

The first self-hosted protocol uses newline-delimited JSON over TCP. It is intended
for local development and private-network proofs, not direct public exposure.

## Lifecycle

1. The host sends `create` and receives a session ID, private join code, and credential.
2. A peer sends `join` with the join code and receives its own credential.
3. The host sends `validate`; every profile must match the session game ID and region.
4. Every participant sends `ready`; the final ready request activates lockstep.
5. Every participant submits one `input` per simulation frame.
6. A frame is released only after every participant's input exists.
7. Participants use `poll` with `after_frame` to retrieve ordered released bundles.
8. Participants submit SHA-256 state `checkpoint` values at agreed frames.
9. The host sends `complete`, which finalizes an atomic replay artifact.

Authenticated operations carry `session_id`, `participant_id`, and `credential`.
Credentials are scoped to a participant and compared using constant-time comparison.

## Input request

```json
{
  "operation": "input",
  "session_id": "...",
  "participant_id": "peer",
  "credential": "...",
  "frame": 0,
  "buttons": 1,
  "stick_x": 0,
  "stick_y": 0
}
```

## Current limitations

- In-memory sessions only
- No TLS or reconnect identity
- No distributed rate limiting or public-internet hardening
- Polling rather than pushed frame delivery
- Most recent 1,024 released bundles retained
- DSU controller delivery exists, but deterministic Dolphin frame control does not
- Bounded active sessions, participants, request sizes, frame lead, history, and idle time
