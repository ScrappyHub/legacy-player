# Patch Coordination v1

## Purpose

This document defines the first conceptual shape of controlled runtime assistance in Legacy Player.

The goal is to support multiplayer orchestration without collapsing the architecture into a patchwork of game-specific hacks.

---

## Core principle

Runtime assistance must be:

- explicit
- bounded
- explainable
- tied to known game-pack-defined needs
- dependent on adapter-supported capabilities

The runtime should never assume that arbitrary assistance is always safe or available.

---

## Coordination model

A simple conceptual model is:

1. game pack declares a boundary or assistance need
2. runtime requests controlled assistance
3. adapter reports whether the capability is supported
4. runtime records the result
5. session continues or fails explicitly

This keeps the system structured.

---

## First expected assistance classes

The first expected assistance classes may include:

- ready barrier coordination
- transition barrier coordination
- ownership assumption coordination
- controlled scene-entry hold behavior

These are enough for early planning.

---

## Failure rule

If assistance is required and unavailable, the system should fail clearly.

It should not proceed silently into undefined multiplayer behavior.
