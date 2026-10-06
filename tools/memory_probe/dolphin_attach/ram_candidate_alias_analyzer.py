from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

from tools.memory_probe.dolphin_attach.ram_candidate_validator import (
    RamCandidateValidationError,
    document_sha256,
    verify_receipt,
    write_verified_json,
)


ALIAS_SCHEMA = "legacy_player.dolphin_ram_candidate_alias_analysis.v1"
PROBABLE_MIRROR_BASIS_POINTS = 9900
RELATED_BASIS_POINTS = 9000


def analyze_aliases(evidence: dict, receipt: dict) -> dict:
    verify_receipt(evidence, receipt)
    receipt_reports = {
        candidate["candidate_id"]: candidate for candidate in receipt["candidates"]
    }
    decoded = {}
    for candidate in evidence["candidates"]:
        candidate_id = candidate["candidate_id"]
        report = receipt_reports[candidate_id]
        post_index = report["selected_post_snapshot"]
        baseline = _decode(candidate["baseline"])
        post = _decode(candidate["post_snapshots"][post_index]["windows"])
        decoded[candidate_id] = {
            "baseline": baseline,
            "post": post,
            "mutations": _mutation_positions(baseline, post),
        }

    pairs = []
    for left_id, right_id in combinations(sorted(decoded), 2):
        left = decoded[left_id]
        right = decoded[right_id]
        baseline_equal, baseline_total = _equal_bytes(
            left["baseline"], right["baseline"]
        )
        post_equal, post_total = _equal_bytes(left["post"], right["post"])
        mutation_union = left["mutations"] | right["mutations"]
        mutation_intersection = left["mutations"] & right["mutations"]
        baseline_basis_points = _basis_points(baseline_equal, baseline_total)
        post_basis_points = _basis_points(post_equal, post_total)
        mutation_basis_points = _basis_points(
            len(mutation_intersection), len(mutation_union)
        )
        if (
            baseline_basis_points >= PROBABLE_MIRROR_BASIS_POINTS
            and mutation_basis_points >= PROBABLE_MIRROR_BASIS_POINTS
        ):
            classification = "probable_mirror"
        elif (
            baseline_basis_points >= RELATED_BASIS_POINTS
            or mutation_basis_points >= RELATED_BASIS_POINTS
        ):
            classification = "related"
        else:
            classification = "distinct"
        pairs.append(
            {
                "left_candidate_id": left_id,
                "right_candidate_id": right_id,
                "classification": classification,
                "baseline_equal_bytes": baseline_equal,
                "baseline_compared_bytes": baseline_total,
                "baseline_equal_basis_points": baseline_basis_points,
                "post_equal_bytes": post_equal,
                "post_compared_bytes": post_total,
                "post_equal_basis_points": post_basis_points,
                "left_mutation_positions": len(left["mutations"]),
                "right_mutation_positions": len(right["mutations"]),
                "mutation_intersection": len(mutation_intersection),
                "mutation_union": len(mutation_union),
                "mutation_jaccard_basis_points": mutation_basis_points,
            }
        )

    probable_pairs = [pair for pair in pairs if pair["classification"] == "probable_mirror"]
    analysis = {
        "schema": ALIAS_SCHEMA,
        "evidence_sha256": evidence["evidence_sha256"],
        "receipt_sha256": receipt["content_sha256"],
        "thresholds": {
            "probable_mirror_basis_points": PROBABLE_MIRROR_BASIS_POINTS,
            "related_basis_points": RELATED_BASIS_POINTS,
        },
        "result": "probable_mirror_detected" if probable_pairs else "no_probable_mirror",
        "authority_claimed": False,
        "pairs": pairs,
        "noncanonical": {
            "candidate_base_addresses": evidence.get("noncanonical", {}).get(
                "candidate_base_addresses", {}
            )
        },
    }
    analysis["content_sha256"] = document_sha256(analysis, "content_sha256")
    return analysis


def _decode(windows: list[dict]) -> list[bytes]:
    decoded = []
    for window in windows:
        data_hex = window.get("data_hex")
        if not isinstance(data_hex, str):
            raise RamCandidateValidationError(
                "alias analysis requires complete validated snapshots"
            )
        decoded.append(bytes.fromhex(data_hex))
    return decoded


def _mutation_positions(
    baseline: list[bytes], post: list[bytes]
) -> set[tuple[int, int]]:
    return {
        (window_index, byte_index)
        for window_index, (before, after) in enumerate(zip(baseline, post, strict=True))
        for byte_index, (left, right) in enumerate(zip(before, after, strict=True))
        if left != right
    }


def _equal_bytes(left: list[bytes], right: list[bytes]) -> tuple[int, int]:
    equal = 0
    total = 0
    for left_window, right_window in zip(left, right, strict=True):
        if len(left_window) != len(right_window):
            raise RamCandidateValidationError("candidate snapshots have different shapes")
        equal += sum(a == b for a, b in zip(left_window, right_window, strict=True))
        total += len(left_window)
    return equal, total


def _basis_points(numerator: int, denominator: int) -> int:
    if denominator == 0:
        return 10000 if numerator == 0 else 0
    return numerator * 10000 // denominator


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
        description="Compare ambiguous Dolphin RAM candidates for mirror-like behavior"
    )
    parser.add_argument("evidence", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        analysis = analyze_aliases(
            _load_object(args.evidence), _load_object(args.receipt)
        )
        output = args.output or args.receipt.with_name(
            args.receipt.name.replace(".receipt.json", ".alias-analysis.json")
        )
        write_verified_json(output, analysis)
    except RamCandidateValidationError as exc:
        print(json.dumps({"result": "fail", "error": str(exc)}, sort_keys=True))
        raise SystemExit(1) from exc
    print(json.dumps(analysis, indent=2, sort_keys=True))
    print(f"WROTE: {output.resolve()}")
    if analysis["result"] == "probable_mirror_detected":
        print("DOLPHIN_RAM_CANDIDATE_MIRROR_SUSPECTED")


if __name__ == "__main__":
    main()

