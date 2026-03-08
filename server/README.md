# Legacy Player Server

## Purpose

The server layer provides the self-hosted multiplayer infrastructure surface of Legacy Player.

It exists to support session creation, player coordination, relay behavior, and later replay or community-hosted services.

The server layer is important to the long-term project identity because Legacy Player is intended to be self-hostable.

---

## Initial role

The first implementation does not need a large public multiplayer service.

The initial server role should remain narrow and practical:

- private session creation
- direct or relay-assisted join flow
- simple session coordination
- explicit compatibility-aware session metadata

This is enough for the first real proof.

---

## Intended areas

### `lobby/`

Session creation, join flow, readiness metadata, and participant coordination.

### `relay/`

Optional traffic relay surfaces for sessions that cannot rely on direct peer connectivity alone.

### `api/`

Server-facing control surfaces for session creation, join, status, and future administrative tooling.

---

## Design rule

The server layer must stay separate from game-specific logic.

The server can coordinate sessions.

It should not contain Mario Party logic, emulator assumptions, or per-game synchronization rules.

Those belong elsewhere.

---

## Long-term role

As Legacy Player grows, the server layer may support:

- persistent self-hosted communities
- replay storage
- tournament/event tooling
- community session discovery
- administrative controls

The first proof does not require those features.

It requires one clean self-hosted session path.
