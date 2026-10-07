# Proposal 0005: Playing across countries, and volunteer relay nodes

Status: proposed, nothing here is built beyond "what works today".
Depends on: 0004 (relay mode, TLS-PSK match tunnel, open rooms and waiting lines).

## Goal

Anyone can play with anyone, in any country, without anyone learning another player's address,
operating system or location, and without a company running every server.

## What already works today

- A server with a public address (a cheap VPS, or a home connection with a forwarded port) can be
  started with `python -m server.cli start --host 0.0.0.0` plus the app's self-signed certificate.
  Players anywhere connect with its short server code (Servers tab) and play through the relay.
  The relay only copies bytes of the TLS-PSK match tunnel, so the server cannot read the game and
  guests and hosts never see each other's addresses.
- Network check (Server Info tab) tells a player whether to host, or to join someone closer.

## The honest limits

1. **Latency is physics.** Rollback/lockstep netplay feels fine to roughly 80-100 ms round trip
   through the relay and degrades fast past 120 ms. Europe to the US west coast is about 140 ms
   before any processing. "Anyone with anyone" therefore means "anyone, with best results among nearby
   players"; the app should say so and steer people to the nearest node.
2. **Someone has to pay for bandwidth.** A 4-player match through a relay is a few hundred kbit/s per
   player. That is small, which is what makes volunteer nodes plausible.
3. **A relay sees metadata.** It sees which IP connects, when, and for how long. Hiding that from the
   relay needs onion-style routing, which adds latency games cannot afford. The design instead
   limits what each party learns: players never learn each other; a node learns only its own
   connections; no node learns who the other players are or what game is played (room titles are
   never sent to a relay node; only the owning lobby server knows them).
4. **Volunteer machines are untrusted.** A node must never be trusted with game data, account
   data or room contents. It may only move opaque encrypted bytes.

## Design in phases

### Phase 1: named public servers (no new code beyond docs and a directory file)
A static, signed `servers.json` (served from the project's repository) lists community servers:
name, region label, short server code, owner contact, last-verified date. The Servers tab shows it
as a read-only list ("Community servers") the player may choose to fetch (needs
*Allow internet downloads*), then connect with one click. Nothing is contacted automatically.

### Phase 2: relay-only nodes, lobby elsewhere
Split the two jobs the server does today:
- **Lobby** (rooms, invite codes, waiting lines): stays with whoever hosts the room's server.
- **Relay node**: `python -m server.cli relay-node --lobby-key ...` accepts paired connections
  and copies bytes. The lobby tells the host and guests which node to use (nearest by measured
  round trip), by handing out a short-lived signed ticket. A node verifies the ticket offline
  with the lobby's public key; it never talks to the lobby and never learns the room.

### Phase 3: volunteer nodes
- A "Share my connection" switch (off by default, explained in plain words) runs a relay node on
  the user's machine with caps: bandwidth per node (default 2 Mbit/s), connections, hours per day.
- **Consent and safety for the volunteer:** a node only forwards TLS-PSK streams it cannot read,
  to other peers of the same ticket; it never opens connections to arbitrary addresses (no open
  proxy), only to the ticket's paired peer. Their address is visible to players who are routed
  through it, so the UI states this before enabling, and it is not enabled in the first-run wizard.
- **Discovery:** nodes announce to a directory (Phase 1's file, then a small signed registry).
  The client measures round trips to a few nearby nodes and picks the best.
- **Abuse:** tickets are rate-limited per lobby; nodes may block lobbies; the directory can revoke a
  node's listing. A node that drops traffic or lies about latency is ranked down by clients' own
  measurements.

### Phase 4: NAT traversal to reduce relay load
For players who allowed direct connections, try hole-punching with a STUN-style helper, and fall
back to the relay. Players who did not opt in never use it.

## What this needs from the owner (decisions, not code)

- Who runs the project's first public servers and directory file, and under what name/contact.
- Whether a volunteer node should be allowed to carry matches for any lobby, or only lobbies on a
  community list.
- Legal review of volunteers carrying encrypted traffic they cannot inspect (terms of use, takedown
  contact), before Phase 3 ships.

## Canonical impact

None to the existing wire protocol for Phases 1-2 except two new operations (`ticket` on the lobby,
`relay-node` role on the relay). Phase 3 adds a directory format. All additions would be proposed to
`docs/WIRE_PROTOCOL_v1.md` before implementation.
