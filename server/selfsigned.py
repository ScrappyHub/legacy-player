"""Make a self-signed TLS certificate with nothing but the standard library.

Used by the in-app shared server so friends over the internet always get TLS, even on a
Windows machine with no OpenSSL. RSA-2048, SHA-256, valid 10 years, CN = legacy-player.
Friends pin the certificate's SHA-256 fingerprint (shown in the app) instead of trusting a CA.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import tempfile
import threading
import time
from pathlib import Path

# ---- tiny DER encoder ------------------------------------------------------------------

def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def _tlv(tag: int, body: bytes) -> bytes:
    return bytes([tag]) + _len(len(body)) + body


def _int(n: int) -> bytes:
    body = n.to_bytes((n.bit_length() + 8) // 8, "big") or b"\x00"
    return _tlv(0x02, body)


def _seq(*items: bytes) -> bytes:
    return _tlv(0x30, b"".join(items))


def _set(*items: bytes) -> bytes:
    return _tlv(0x31, b"".join(items))


def _oid(dotted: str) -> bytes:
    parts = [int(p) for p in dotted.split(".")]
    body = bytes([40 * parts[0] + parts[1]])
    for p in parts[2:]:
        chunk = [p & 0x7F]
        p >>= 7
        while p:
            chunk.append(0x80 | (p & 0x7F))
            p >>= 7
        body += bytes(reversed(chunk))
    return _tlv(0x06, body)


def _utf8(s: str) -> bytes:
    return _tlv(0x0C, s.encode())


def _bitstring(b: bytes) -> bytes:
    return _tlv(0x03, b"\x00" + b)


def _utctime(t: float) -> bytes:
    return _tlv(0x17, time.strftime("%y%m%d%H%M%SZ", time.gmtime(t)).encode())


NULL = b"\x05\x00"
OID_RSA = _oid("1.2.840.113549.1.1.1")
OID_SHA256_RSA = _oid("1.2.840.113549.1.1.11")
OID_CN = _oid("2.5.4.3")
OID_SAN = _oid("2.5.29.17")

# ---- RSA ----------------------------------------------------------------------------------

_SMALL_PRIMES = [p for p in range(3, 2000, 2) if all(p % q for q in range(3, int(p ** 0.5) + 1, 2))]


def _probably_prime(n: int, rounds: int = 40) -> bool:
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits: int) -> int:
    while True:
        n = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if _probably_prime(n):
            return n


def generate_rsa(bits: int = 2048) -> dict:
    e = 65537
    while True:
        p, q = _prime(bits // 2), _prime(bits // 2)
        if p == q:
            continue
        n = p * q
        phi = (p - 1) * (q - 1)
        if phi % e:
            break
    d = pow(e, -1, phi)
    return {"n": n, "e": e, "d": d, "p": p, "q": q, "dp": d % (p - 1), "dq": d % (q - 1), "qinv": pow(q, -1, p)}


def _sign_sha256(key: dict, data: bytes) -> bytes:
    k = (key["n"].bit_length() + 7) // 8
    digest_info = _seq(_seq(_oid("2.16.840.1.101.3.4.2.1"), NULL), _tlv(0x04, hashlib.sha256(data).digest()))
    padded = b"\x00\x01" + b"\xff" * (k - len(digest_info) - 3) + b"\x00" + digest_info
    return pow(int.from_bytes(padded, "big"), key["d"], key["n"]).to_bytes(k, "big")


def _pem(label: str, der: bytes) -> str:
    b64 = base64.encodebytes(der).decode().replace("\n", "")
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return f"-----BEGIN {label}-----\n" + "\n".join(lines) + f"\n-----END {label}-----\n"


def make_certificate(common_name: str = "legacy-player", days: int = 3650, bits: int = 2048) -> tuple[str, str, str]:
    """Return (cert_pem, key_pem, sha256_fingerprint_hex)."""
    key = generate_rsa(bits)
    public_key = _seq(_seq(OID_RSA, NULL), _bitstring(_seq(_int(key["n"]), _int(key["e"]))))
    name = _seq(_set(_seq(OID_CN, _utf8(common_name))))
    now = time.time() - 3600
    san = _seq(_tlv(0x82, common_name.encode()), _tlv(0x82, b"localhost"), _tlv(0x87, bytes([127, 0, 0, 1])))
    extensions = _tlv(0xA3, _seq(_seq(OID_SAN, _tlv(0x04, san))))
    tbs = _seq(
        _tlv(0xA0, _int(2)),                       # version 3
        _int(secrets.randbits(63) | 1),            # serial
        _seq(OID_SHA256_RSA, NULL),
        name,
        _seq(_utctime(now), _utctime(now + days * 86400)),
        name,
        public_key,
        extensions,
    )
    cert = _seq(tbs, _seq(OID_SHA256_RSA, NULL), _bitstring(_sign_sha256(key, tbs)))
    private = _seq(_int(0), _int(key["n"]), _int(key["e"]), _int(key["d"]), _int(key["p"]), _int(key["q"]),
                   _int(key["dp"]), _int(key["dq"]), _int(key["qinv"]))
    return _pem("CERTIFICATE", cert), _pem("RSA PRIVATE KEY", private), hashlib.sha256(cert).hexdigest()


_CERT_LOCK = threading.Lock()
LOCK_NAME = ".cert.lock"
STALE_LOCK_SECONDS = 300.0        # a lock older than this was left by a process that died while making the key
LOCK_WAIT_SECONDS = 600.0


def _write_new(folder: Path, prefix: str, text: str) -> str:
    """Write text to a fresh, uniquely named file in folder (owner-only), flushed to disk; returns its path."""
    fd, tmp = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return tmp


def _take_lock(lock: Path, done) -> bool:
    """Take the folder's lock file (shared by every process). Returns False when another process finished the work
    while we waited, so there is nothing left to do."""
    end = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            if done():
                return False
            try:
                if time.time() - lock.stat().st_mtime > STALE_LOCK_SECONDS:
                    lock.unlink()
                    continue
            except OSError:
                continue                               # gone in the meantime: try again at once
            if time.monotonic() > end:
                raise TimeoutError("another program has been making the certificate for too long")
            time.sleep(0.1)


def ensure_certificate(folder: Path, common_name: str = "legacy-player") -> tuple[Path, Path, str]:
    """Create cert.pem/key.pem in folder if missing; return their paths and the fingerprint.

    Two callers (threads, or two processes such as the app and its server starting together) never write one half
    each: a lock file in the folder lets only one make the pair, the others wait and then use it. The key goes in
    first and the certificate last, so "cert.pem exists" means the matching key is already in place."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    cert_path, key_path = folder / "cert.pem", folder / "key.pem"

    def done() -> bool:
        return cert_path.exists() and key_path.exists()

    with _CERT_LOCK:
        if not done():
            lock = folder / LOCK_NAME
            if _take_lock(lock, done):
                try:
                    if not done():                     # someone may have finished just before we got the lock
                        cert_pem, key_pem, _ = make_certificate(common_name)
                        tmp_key = _write_new(folder, ".key-", key_pem)
                        tmp_cert = _write_new(folder, ".cert-", cert_pem)
                        cert_path.unlink(missing_ok=True)     # a lone old certificate must not pair with the new key
                        os.replace(tmp_key, key_path)
                        os.replace(tmp_cert, cert_path)
                finally:
                    try:
                        lock.unlink()
                    except OSError:
                        pass
    return cert_path, key_path, fingerprint_of(cert_path)


def fingerprint_of(cert_path: Path) -> str:
    import ssl
    der = ssl.PEM_cert_to_DER_cert(Path(cert_path).read_text(encoding="utf-8"))
    return hashlib.sha256(der).hexdigest()


def pretty_fingerprint(hex_digest: str) -> str:
    return "-".join(hex_digest[i:i + 4].upper() for i in range(0, 32, 4))  # first 128 bits is plenty to read aloud
