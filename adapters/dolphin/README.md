# Dolphin Adapter

## Purpose

The Dolphin adapter is the first platform adapter for Legacy Player.

It connects the Legacy Player runtime to Dolphin-based GameCube and later Wii environments.

Its job is to expose structured platform capabilities to the runtime without leaking Dolphin-specific assumptions into the shared core.

---

## Responsibilities

The Dolphin adapter is responsible for:

- identifying the active platform environment
- identifying the active game and supported profile where possible
- exposing compatibility-relevant fingerprints
- exposing state and memory observation surfaces
- exposing controller and input-related capability surfaces
- reporting capability availability and failure conditions clearly

---

## Initial focus

The first adapter proof should focus on:

- GameCube
- Dolphin
- one first supported party-game target
- structured game identification
- structured capability reporting
- basic state observation surfaces

The first adapter proof does not need full broad emulator feature coverage.

---

## Adapter boundaries

The Dolphin adapter must not become the multiplayer brain of the system.

It is a platform bridge.

It should expose:

- identity
- fingerprinting
- observables
- controlled hooks
- diagnostics

It should not own:

- shared session policy
- shared replay policy
- game-pack decision logic
- long-term multiplayer architecture

---

## Expected capability areas

The Dolphin adapter should eventually expose:

- adapter identity
- Dolphin version/environment details where available
- active title fingerprint
- region/revision support information
- memory/state observation surfaces
- controller/input observation surfaces
- controlled runtime assistance surfaces
- adapter health and failure reporting

---

## First proof of value

The first proof of value for this adapter is simple:

Legacy Player can attach to a supported Dolphin-driven target and identify enough structured information for the runtime to select a matching game pack and enter a controlled session flow.
