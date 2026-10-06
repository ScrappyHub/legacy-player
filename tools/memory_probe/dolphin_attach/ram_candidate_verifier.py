from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.memory_probe.dolphin_attach.ram_candidate_validator import (
    RamCandidateValidationError,
    verify_receipt,
)


def _load_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RamCandidateValidationError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RamCandidateValidationError(f"JSON root must be an object: {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Independently recompute a Dolphin RAM candidate decision"
    )
    parser.add_argument("evidence", type=Path)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        verification = verify_receipt(
            _load_object(args.evidence), _load_object(args.receipt)
        )
    except RamCandidateValidationError as exc:
        print(json.dumps({"result": "fail", "error": str(exc)}, sort_keys=True))
        raise SystemExit(1) from exc
    print(json.dumps(verification, indent=2, sort_keys=True))
    print("DOLPHIN_RAM_CANDIDATE_RECEIPT_VERIFIED")


if __name__ == "__main__":
    main()

