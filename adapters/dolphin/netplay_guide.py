"""Guided launch for Dolphin's built-in NetPlay (GameCube and Wii).

Dolphin has no command-line option to start or join NetPlay, so this adapter does
not pretend to drive it. It opens Dolphin with the game ready (a visible window,
not batch mode), then gives the player exact, ordered steps with the room's
address or host code already filled in. Everyone must use the same Dolphin
version, the same game file (region and revision) and the same settings.
"""
from __future__ import annotations

DEFAULT_PORT = 2626
SUPPORTED_CONSOLES = {"gamecube", "wii"}


class DolphinNetplayError(RuntimeError):
    pass


def build_open_command(exe: str, rom: str) -> list[str]:
    """Open Dolphin with the game loaded in the normal window (`-e` = execute)."""
    return [exe, "-e", rom]


def steps(role: str, *, mode: str, address: str | None = None, port: int | None = None, code: str | None = None) -> list[str]:
    if role == "host":
        common = [
            "In Dolphin, choose Tools > Start NetPlay… and open the Host tab.",
            "Pick this game in the list.",
        ]
        if mode == "traversal":
            return common + [
                "Set Connection to 'Traversal Server' (no router setup needed).",
                "Click Host. Dolphin shows an 8-character host code.",
                "Paste that code into the 'Share Dolphin host code' box here. Your friends are notified.",
                "When everyone appears in Dolphin's NetPlay window, start the game from there.",
            ]
        return common + [
            f"Set Connection to 'Direct Connection' and the port to {port or DEFAULT_PORT}.",
            "Make sure that port is reachable (same network, a VPN, or a forwarded port).",
            "Click Host. Your friends were notified with your address.",
            "When everyone appears in Dolphin's NetPlay window, start the game from there.",
        ]
    if role == "guest":
        if mode == "traversal":
            if not code:
                raise DolphinNetplayError("the host has not shared a Dolphin host code yet")
            return [
                "In Dolphin, choose Tools > Start NetPlay… and open the Connect tab.",
                "Set Connection to 'Traversal Server'.",
                f"Enter the host code: {code}",
                "Click Connect, then wait for the host to start the game.",
            ]
        if not address:
            raise DolphinNetplayError("the host has not published an address yet")
        return [
            "In Dolphin, choose Tools > Start NetPlay… and open the Connect tab.",
            "Set Connection to 'Direct Connection'.",
            f"Enter the host address {address} and port {port or DEFAULT_PORT}.",
            "Click Connect, then wait for the host to start the game.",
        ]
    raise DolphinNetplayError("role must be host or guest")
