# State Markers v1

## Purpose

This document defines the initial idea of state markers inside Legacy Player.

A state marker is a structured runtime-visible fact that helps the system reason about where a session is, whether peers are aligned, and what should be logged for replay and diagnostics.

---

## Why state markers matter

Legacy Player needs a shared way to describe multiplayer-relevant state without hardcoding every game directly into the runtime.

State markers provide that layer.

They help with:

- replay labeling
- mismatch detection
- session boundary observation
- active-state visibility
- explicit failure analysis

---

## Example marker categories

Suggested initial categories:

- session marker
- readiness marker
- compatibility marker
- phase marker
- boundary marker
- mismatch marker
- completion marker

---

## Examples

Examples of state markers may include:

- session created
- participant joined
- compatibility validated
- ready barrier reached
- minigame entry observed
- mismatch detected
- session completed

These are examples of shape, not locked implementation fields.

---

## Design rule

Markers should be:

- explicit
- structured
- explainable
- replay-visible when relevant

Markers should not rely on hidden assumptions.
