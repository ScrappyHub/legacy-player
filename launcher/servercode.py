"""Short server codes: one easy-to-type string that carries a server's address, port and a
fingerprint prefix, so a friend types one thing instead of three.

Format: LP-XXXX-XXXX-XXXX-XXXX-XX (Crockford base32 of: 4 address bytes, 2 port bytes,
5 fingerprint bytes). Only IPv4 addresses fit; for a name or IPv6 address share the long form.
The 40-bit fingerprint prefix is checked against the server certificate on every connect, which
protects against casual impostors; the full fingerprint is still shown for people who want it.
"""
from __future__ import annotations

import ipaddress

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_FIX = {"O": "0", "I": "1", "L": "1", "U": "V"}


class CodeError(ValueError):
    pass


def encode(host: str, port: int, fingerprint_hex: str, key_hex: str = "") -> str:
    try:
        ip = ipaddress.IPv4Address(host)
    except ValueError as exc:
        raise CodeError("Short codes only work with a numeric IPv4 address.") from exc
    if not 1 <= port <= 65535:
        raise CodeError("Port out of range.")
    try:
        fp = bytes.fromhex("".join(c for c in fingerprint_hex.lower() if c in "0123456789abcdef"))[:5]
    except ValueError as exc:
        raise CodeError("Bad fingerprint.") from exc
    fp = fp.ljust(5, b"\0")
    key = bytes.fromhex(key_hex) if key_hex else b""
    if key and len(key) != 5:
        raise CodeError("Bad server key.")
    raw = ip.packed + port.to_bytes(2, "big") + fp + key
    value = int.from_bytes(raw, "big")
    length = 26 if key else 18          # 11 bytes -> 18 base32 chars; 16 bytes (with the key) -> 26
    chars = []
    for _ in range(length):
        chars.append(ALPHABET[value & 31])
        value >>= 5
    text = "".join(reversed(chars))
    return "LP-" + "-".join(text[i:i + 4] for i in range(0, length - 2, 4)) + "-" + text[length - 2:]


def decode(code: str) -> dict:
    text = "".join(c for c in code.upper() if c not in "- _")
    if text.startswith("LP") and len(text) in (20, 28):
        text = text[2:]
    text = "".join(_FIX.get(c, c) for c in text)
    if len(text) not in (18, 26) or any(c not in ALPHABET for c in text):
        raise CodeError("That server code does not look right. It should be LP- followed by letters and numbers.")
    size = 11 if len(text) == 18 else 16
    value = 0
    for c in text:
        value = value << 5 | ALPHABET.index(c)
    if value >> (size * 8):
        raise CodeError("That server code does not look right.")
    raw = value.to_bytes(size, "big")
    host = str(ipaddress.IPv4Address(raw[:4]))
    port = int.from_bytes(raw[4:6], "big")
    if not port:
        raise CodeError("That server code does not look right.")
    out = {"host": host, "port": port, "fingerprint": raw[6:11].hex()}
    if size == 16:
        out["key"] = raw[11:16].hex()
    return out
