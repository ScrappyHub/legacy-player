"""Check a hosted Legacy Player server (and report receiver) the way a player's app would reach it.

    python tools/check_deployment.py --code LP2-... [--reports https://reports.example.com]

Exit code 0 only when everything asked for worked. Nothing is created on the server; the report check only reads the
receiver's health page.
"""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from launcher import servercode                                    # noqa: E402
from launcher.lobby_client import LobbyClient, LobbyClientError    # noqa: E402


def check_server(code: str) -> list[tuple[bool, str]]:
    out: list[tuple[bool, str]] = []
    try:
        found = servercode.decode(code)
    except servercode.CodeError as exc:
        return [(False, f"The code is not valid: {exc}")]
    out.append((True, "The code reads correctly."))
    client = LobbyClient(found["host"], found["port"], tls=True, fingerprint=found["fingerprint"],
                         access_key=found.get("key", ""), timeout=8.0)
    try:
        client.call({"operation": "browse"})
        out.append((True, "Connected with an encrypted connection; the certificate matches the code and the key is accepted."))
    except LobbyClientError as exc:
        out.append((False, f"Could not use the server: {exc}"))
    if not found.get("key"):
        out.append((False, "This code carries no access key, so anyone could use the server. Make the code with `server.cli code`."))
    return out


def check_reports(url: str) -> list[tuple[bool, str]]:
    if not url.lower().startswith("https://"):
        return [(False, "The report address must start with https:// (the app refuses anything else).")]
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=10) as reply:
            body = reply.read(200).decode("utf-8", "replace")
        if "report receiver" in body.lower():
            return [(True, "The report receiver answers over HTTPS with a valid certificate.")]
        return [(False, "Something answered, but it is not the report receiver.")]
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return [(False, f"The report receiver did not answer: {exc}")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--code", help="the server code (LP-... or LP2-...)")
    parser.add_argument("--reports", help="the https address of the report receiver")
    args = parser.parse_args(argv)
    if not (args.code or args.reports):
        parser.error("give --code and/or --reports")
    results = (check_server(args.code) if args.code else []) + (check_reports(args.reports) if args.reports else [])
    for ok, text in results:
        print(("OK    " if ok else "FAIL  ") + text)
    return 0 if all(ok for ok, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
