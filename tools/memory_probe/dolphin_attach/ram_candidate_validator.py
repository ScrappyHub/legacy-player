from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable


EVIDENCE_SCHEMA = "legacy_player.dolphin_ram_candidate_evidence.v1"
RECEIPT_SCHEMA = "legacy_player.dolphin_ram_candidate_validation.v1"
SELECTION_POLICY = "exactly_one_candidate_with_changed_bytes.v1"
DEFAULT_WINDOW_SIZE = 256
DEFAULT_MAX_SCAN_BYTES = 1024 * 1024
DEFAULT_MAX_WINDOW_COUNT = 1024
DEFAULT_POST_SNAPSHOT_COUNT = 4
DEFAULT_POST_SNAPSHOT_DELAY_SECONDS = 0.15
DEFAULT_MAX_CANDIDATES = 8


class RamCandidateValidationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digestable_document(document: dict, digest_field: str) -> dict:
    return {
        key: value
        for key, value in document.items()
        if key not in {digest_field, "noncanonical"}
    }


def document_sha256(document: dict, digest_field: str) -> str:
    return hashlib.sha256(
        canonical_json_bytes(_digestable_document(document, digest_field))
    ).hexdigest()


def _require_digest(document: dict, digest_field: str) -> None:
    stored = document.get(digest_field)
    if not isinstance(stored, str) or len(stored) != 64:
        raise RamCandidateValidationError(f"missing or malformed {digest_field}")
    actual = document_sha256(document, digest_field)
    if actual != stored:
        raise RamCandidateValidationError(f"{digest_field} does not match canonical content")


def safe_action_label(raw: str) -> str:
    cleaned = "".join(
        character
        for character in str(raw).strip().replace(" ", "_")
        if character.isascii() and (character.isalnum() or character in "_.-")
    )
    if not cleaned:
        raise RamCandidateValidationError("action label must contain a safe ASCII character")
    return cleaned[:128]


def capture_windows(
    proc,
    region: dict,
    offsets: list[int],
    window_size: int,
    read_fn: Callable,
) -> list[dict]:
    base_address = _required_int(region, "base_address", minimum=0)
    region_size = _required_int(region, "region_size", minimum=1)
    windows = []
    for offset in offsets:
        if offset < 0 or offset >= region_size:
            raise RamCandidateValidationError(f"sample offset is outside region: {offset}")
        expected_size = min(window_size, region_size - offset)
        data = read_fn(proc, base_address + offset, expected_size)
        if data is not None and not isinstance(data, bytes):
            raise RamCandidateValidationError("memory reader returned a non-bytes value")
        if data is not None and len(data) != expected_size:
            data = None
        windows.append(
            {
                "offset": offset,
                "size": expected_size,
                "data_hex": None if data is None else data.hex(),
            }
        )
    return windows


def build_evidence(
    *,
    subject: dict,
    candidates: list[dict],
    offsets: list[int],
    window_size: int,
    baseline_windows: dict[str, list[dict]],
    post_snapshots: dict[str, list[list[dict]]],
    capture_parameters: dict | None = None,
    noncanonical: dict | None = None,
) -> dict:
    if window_size <= 0:
        raise RamCandidateValidationError("window_size must be positive")
    if not offsets or offsets != sorted(set(offsets)) or offsets[0] < 0:
        raise RamCandidateValidationError("sample offsets must be non-empty, sorted, and unique")
    if not candidates:
        raise RamCandidateValidationError("at least one candidate is required")

    ordered_candidates = sorted(candidates, key=lambda item: item["base_address"])
    serialized_candidates = []
    address_map = {}
    for index, region in enumerate(ordered_candidates):
        candidate_id = f"candidate-{index:03d}"
        address_map[candidate_id] = hex(_required_int(region, "base_address", minimum=0))
        try:
            baseline = baseline_windows[candidate_id]
            posts = post_snapshots[candidate_id]
        except KeyError as exc:
            raise RamCandidateValidationError(
                f"missing capture data for {candidate_id}"
            ) from exc
        if not posts:
            raise RamCandidateValidationError(f"no post-action snapshots for {candidate_id}")
        serialized_candidates.append(
            {
                "candidate_id": candidate_id,
                "region_size": _required_int(region, "region_size", minimum=1),
                "protect": _required_int(region, "protect", minimum=0),
                "type": _required_int(region, "type", minimum=0),
                "is_exact_gamecube_ram_size": bool(
                    region.get("is_exact_gamecube_ram_size", False)
                ),
                "is_mapped": bool(region.get("is_mapped", False)),
                "zero_filled_head": bool(region.get("zero_filled_head", True)),
                "baseline": baseline,
                "post_snapshots": [
                    {"snapshot_index": snapshot_index, "windows": windows}
                    for snapshot_index, windows in enumerate(posts)
                ],
            }
        )

    parameters = {
        **(capture_parameters or {}),
        "window_size": window_size,
        "sample_offsets": list(offsets),
        "post_snapshot_count": len(serialized_candidates[0]["post_snapshots"]),
    }
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "subject": dict(subject),
        "parameters": parameters,
        "candidates": serialized_candidates,
        "noncanonical": {
            **(noncanonical or {}),
            "candidate_base_addresses": address_map,
        },
    }
    evidence["evidence_sha256"] = document_sha256(evidence, "evidence_sha256")
    return evidence


def analyze_evidence(evidence: dict) -> dict:
    _validate_evidence_shape(evidence)
    offsets = evidence["parameters"]["sample_offsets"]
    reports = []
    any_incomplete = False

    for candidate in evidence["candidates"]:
        baseline_bytes, baseline_errors = _decode_windows(
            candidate["baseline"], offsets, candidate["region_size"]
        )
        baseline_sha256 = _snapshot_sha256(candidate["baseline"])
        best_report = None
        post_hashes = []
        total_errors = baseline_errors

        for post in candidate["post_snapshots"]:
            post_bytes, post_errors = _decode_windows(
                post["windows"], offsets, candidate["region_size"]
            )
            total_errors += post_errors
            post_hash = _snapshot_sha256(post["windows"])
            post_hashes.append(post_hash)
            changed_window_count, changed_byte_count = _count_changes(
                baseline_bytes, post_bytes
            )
            current = {
                "snapshot_index": post["snapshot_index"],
                "changed_window_count": changed_window_count,
                "changed_byte_count": changed_byte_count,
            }
            if best_report is None or (
                current["changed_byte_count"], current["changed_window_count"]
            ) > (
                best_report["changed_byte_count"],
                best_report["changed_window_count"],
            ):
                best_report = current

        if best_report is None:
            raise RamCandidateValidationError("candidate has no post-action snapshots")
        if total_errors:
            any_incomplete = True
        reports.append(
            {
                "candidate_id": candidate["candidate_id"],
                "region_size": candidate["region_size"],
                "protect": candidate["protect"],
                "type": candidate["type"],
                "is_exact_gamecube_ram_size": candidate[
                    "is_exact_gamecube_ram_size"
                ],
                "is_mapped": candidate["is_mapped"],
                "zero_filled_head": candidate["zero_filled_head"],
                "baseline_sha256": baseline_sha256,
                "post_snapshot_sha256": post_hashes,
                "read_error_count": total_errors,
                "selected_post_snapshot": best_report["snapshot_index"],
                "changed_window_count": best_report["changed_window_count"],
                "changed_byte_count": best_report["changed_byte_count"],
                "mutation_detected": best_report["changed_byte_count"] > 0,
            }
        )

    mutating = [report for report in reports if report["mutation_detected"]]
    if any_incomplete:
        result = "fail"
        reason = "capture_incomplete"
        selected_candidate_id = None
    elif not mutating:
        result = "fail"
        reason = "no_candidate_mutated"
        selected_candidate_id = None
    elif len(mutating) > 1:
        result = "fail"
        reason = "ambiguous_mutation"
        selected_candidate_id = None
    else:
        result = "pass"
        reason = "unique_behavioral_candidate"
        selected_candidate_id = mutating[0]["candidate_id"]

    return {
        "selection_policy": SELECTION_POLICY,
        "result": result,
        "reason": reason,
        "selected_candidate_id": selected_candidate_id,
        "candidates": reports,
    }


def build_receipt(evidence: dict, *, noncanonical: dict | None = None) -> dict:
    _require_digest(evidence, "evidence_sha256")
    analysis = analyze_evidence(evidence)
    claims = []
    if analysis["result"] == "pass":
        claims.append("DOLPHIN_RAM_CANDIDATE_VALIDATED")
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "receipt_type": "dolphin_ram_candidate_validation",
        "subject": dict(evidence["subject"]),
        "evidence_sha256": evidence["evidence_sha256"],
        **analysis,
        "claims": claims,
        "noncanonical": dict(noncanonical or {}),
    }
    receipt["content_sha256"] = document_sha256(receipt, "content_sha256")
    return receipt


def verify_receipt(evidence: dict, receipt: dict) -> dict:
    _require_digest(evidence, "evidence_sha256")
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise RamCandidateValidationError("unsupported receipt schema")
    _require_digest(receipt, "content_sha256")
    expected = build_receipt(evidence)
    actual_canonical = _digestable_document(receipt, "content_sha256")
    expected_canonical = _digestable_document(expected, "content_sha256")
    if actual_canonical != expected_canonical:
        raise RamCandidateValidationError(
            "receipt decision does not match independently recomputed evidence"
        )
    return {
        "schema": "legacy_player.dolphin_ram_candidate_verification.v1",
        "result": "pass",
        "evidence_sha256": evidence["evidence_sha256"],
        "receipt_sha256": receipt["content_sha256"],
        "decision": receipt["result"],
        "reason": receipt["reason"],
        "selected_candidate_id": receipt["selected_candidate_id"],
    }


def write_verified_json(path: Path, value: dict) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    encoded = data.encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        stored = path.read_bytes()
        if stored != encoded:
            raise RamCandidateValidationError(f"written JSON failed read-back: {path}")
        json.loads(stored.decode("utf-8"))
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _validate_evidence_shape(evidence: dict) -> None:
    if not isinstance(evidence, dict) or evidence.get("schema") != EVIDENCE_SCHEMA:
        raise RamCandidateValidationError("unsupported evidence schema")
    _require_digest(evidence, "evidence_sha256")
    subject = evidence.get("subject")
    if not isinstance(subject, dict):
        raise RamCandidateValidationError("evidence subject must be an object")
    for key in ("emulator", "game_id", "region", "action_label", "identity_assurance"):
        if not isinstance(subject.get(key), str) or not subject[key].strip():
            raise RamCandidateValidationError(f"evidence subject requires {key}")
    parameters = evidence.get("parameters")
    if not isinstance(parameters, dict):
        raise RamCandidateValidationError("evidence parameters must be an object")
    window_size = _required_int(parameters, "window_size", minimum=1)
    offsets = parameters.get("sample_offsets")
    if (
        not isinstance(offsets, list)
        or not offsets
        or any(isinstance(value, bool) or not isinstance(value, int) for value in offsets)
        or offsets != sorted(set(offsets))
        or offsets[0] < 0
    ):
        raise RamCandidateValidationError("invalid sample offsets")
    post_count = _required_int(parameters, "post_snapshot_count", minimum=1)
    candidates = evidence.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RamCandidateValidationError("evidence must contain candidates")
    candidate_ids = [candidate.get("candidate_id") for candidate in candidates]
    if any(not isinstance(value, str) or not value for value in candidate_ids):
        raise RamCandidateValidationError("candidate IDs must be non-empty strings")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise RamCandidateValidationError("candidate IDs must be unique")
    for candidate in candidates:
        region_size = _required_int(candidate, "region_size", minimum=1)
        _required_int(candidate, "protect", minimum=0)
        _required_int(candidate, "type", minimum=0)
        if (
            candidate.get("is_exact_gamecube_ram_size") is not True
            or candidate.get("is_mapped") is not True
        ):
            raise RamCandidateValidationError(
                "all candidates must be exact mapped GameCube RAM regions"
            )
        if candidate.get("zero_filled_head") is not False:
            raise RamCandidateValidationError("zero-filled candidates are not eligible")
        _decode_windows(candidate.get("baseline"), offsets, region_size, window_size)
        posts = candidate.get("post_snapshots")
        if not isinstance(posts, list) or len(posts) != post_count:
            raise RamCandidateValidationError("post snapshot count does not match parameters")
        for expected_index, post in enumerate(posts):
            if not isinstance(post, dict) or post.get("snapshot_index") != expected_index:
                raise RamCandidateValidationError("post snapshot indexes must be contiguous")
            _decode_windows(post.get("windows"), offsets, region_size, window_size)


def _decode_windows(
    windows: object,
    offsets: list[int],
    region_size: int,
    window_size: int | None = None,
) -> tuple[list[bytes | None], int]:
    if not isinstance(windows, list) or len(windows) != len(offsets):
        raise RamCandidateValidationError("snapshot window count does not match offsets")
    decoded = []
    errors = 0
    for expected_offset, window in zip(offsets, windows, strict=True):
        if not isinstance(window, dict) or window.get("offset") != expected_offset:
            raise RamCandidateValidationError("snapshot windows do not match sample offsets")
        size = _required_int(window, "size", minimum=1)
        maximum_size = region_size - expected_offset
        expected_size = min(window_size or size, maximum_size)
        if expected_offset >= region_size or size != expected_size:
            raise RamCandidateValidationError("snapshot window size is inconsistent")
        data_hex = window.get("data_hex")
        if data_hex is None:
            decoded.append(None)
            errors += 1
            continue
        if not isinstance(data_hex, str):
            raise RamCandidateValidationError("window data_hex must be a string or null")
        try:
            data = bytes.fromhex(data_hex)
        except ValueError as exc:
            raise RamCandidateValidationError("window data_hex is malformed") from exc
        if len(data) != size:
            raise RamCandidateValidationError("partial memory read is not a valid window")
        decoded.append(data)
    return decoded, errors


def _snapshot_sha256(windows: list[dict]) -> str:
    digest = hashlib.sha256()
    for window in windows:
        digest.update(window["offset"].to_bytes(8, "big"))
        digest.update(window["size"].to_bytes(4, "big"))
        data_hex = window.get("data_hex")
        if data_hex is None:
            digest.update(b"\x00")
        else:
            data = bytes.fromhex(data_hex)
            digest.update(b"\x01")
            digest.update(data)
    return digest.hexdigest()


def _count_changes(
    baseline: list[bytes | None], post: list[bytes | None]
) -> tuple[int, int]:
    changed_windows = 0
    changed_bytes = 0
    for before, after in zip(baseline, post, strict=True):
        if before is None or after is None:
            continue
        count = sum(left != right for left, right in zip(before, after, strict=True))
        if count:
            changed_windows += 1
            changed_bytes += count
    return changed_windows, changed_bytes


def _required_int(value: dict, key: str, *, minimum: int) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int) or item < minimum:
        raise RamCandidateValidationError(f"{key} must be an integer >= {minimum}")
    return item


def _capture_all(
    proc,
    candidates: list[dict],
    offsets: list[int],
    window_size: int,
    read_fn: Callable,
) -> dict[str, list[dict]]:
    snapshots = {}
    for index, candidate in enumerate(sorted(candidates, key=lambda item: item["base_address"])):
        snapshots[f"candidate-{index:03d}"] = capture_windows(
            proc, candidate, offsets, window_size, read_fn
        )
    return snapshots


def run_live(args: argparse.Namespace) -> tuple[Path, Path, dict]:
    from tools.memory_probe.dolphin_attach.attach import find_dolphin_process
    from tools.memory_probe.dolphin_attach.ram_map import (
        GAMECUBE_MAIN_RAM_SIZE,
        list_dolphin_ram_candidates,
    )
    from tools.memory_probe.dolphin_attach.ram_sampler import build_sample_offsets
    from tools.memory_probe.game_fingerprint.compatibility import require_game_profile
    from tools.memory_probe.game_fingerprint.fingerprint import detect_game
    from tools.memory_probe.memory_reader.reader import read_region

    proc = find_dolphin_process(args.pid)
    if proc is None:
        raise RamCandidateValidationError("Dolphin is not running")
    game = require_game_profile(detect_game(proc))
    candidates = [
        candidate
        for candidate in list_dolphin_ram_candidates(proc, limit=args.region_limit)
        if candidate["region_size"] == GAMECUBE_MAIN_RAM_SIZE
        and candidate["is_mapped"]
        and not candidate["zero_filled_head"]
    ]
    if not candidates:
        raise RamCandidateValidationError("no eligible exact mapped MEM1 candidates")
    if len(candidates) > args.max_candidates:
        raise RamCandidateValidationError(
            f"candidate count {len(candidates)} exceeds safety limit {args.max_candidates}"
        )
    offsets = build_sample_offsets(
        GAMECUBE_MAIN_RAM_SIZE,
        args.window_size,
        args.max_scan_bytes,
        max_window_count=args.max_window_count,
        alignment=args.alignment,
    )

    print(f"Dolphin PID: {proc.pid}")
    print(f"Profile: {game['game_id']}/{game['region']} (title-derived prototype identity)")
    print(f"Eligible candidates: {len(candidates)}")
    print(f"Sample windows per candidate: {len(offsets)}")
    input("Press Enter to capture the baseline for every candidate...")
    baseline = _capture_all(proc, candidates, offsets, args.window_size, read_region)
    print(f"Perform exactly one labeled action: {args.action_label}")
    input("Press Enter immediately after the action occurs...")

    posts = {f"candidate-{index:03d}": [] for index in range(len(candidates))}
    for snapshot_index in range(args.post_snapshot_count):
        if args.post_snapshot_delay > 0:
            time.sleep(args.post_snapshot_delay)
        captured = _capture_all(proc, candidates, offsets, args.window_size, read_region)
        for candidate_id, windows in captured.items():
            posts[candidate_id].append(windows)
        print(f"Captured post-action snapshot {snapshot_index + 1}/{args.post_snapshot_count}")

    run_id = str(uuid.uuid4())
    evidence = build_evidence(
        subject={
            "emulator": "dolphin",
            "game_id": game["game_id"],
            "region": game["region"],
            "action_label": args.action_label,
            "identity_assurance": "title-derived-prototype",
        },
        candidates=candidates,
        offsets=offsets,
        window_size=args.window_size,
        baseline_windows=baseline,
        post_snapshots=posts,
        capture_parameters={
            "max_scan_bytes": args.max_scan_bytes,
            "max_window_count": args.max_window_count,
            "alignment": args.alignment,
            "post_snapshot_delay_milliseconds": round(args.post_snapshot_delay * 1000),
        },
        noncanonical={
            "run_id": run_id,
            "captured_at_utc": utc_now(),
            "pid": proc.pid,
            "process_name": game.get("process_name"),
            "executable": game.get("exe"),
        },
    )
    receipt = build_receipt(
        evidence,
        noncanonical={"run_id": run_id, "created_at_utc": utc_now()},
    )
    verify_receipt(evidence, receipt)

    stem = f"ram-validation-{run_id}_{args.action_label}"
    evidence_path = args.output_dir / f"{stem}.evidence.json"
    receipt_path = args.output_dir / f"{stem}.receipt.json"
    write_verified_json(evidence_path, evidence)
    write_verified_json(receipt_path, receipt)
    return evidence_path.resolve(), receipt_path.resolve(), receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Behaviorally evaluate every exact mapped Dolphin MEM1 candidate"
    )
    parser.add_argument("--action-label", required=True, type=safe_action_label)
    parser.add_argument("--pid", type=int)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("tools/memory_probe/exports")
    )
    parser.add_argument("--window-size", type=int, default=DEFAULT_WINDOW_SIZE)
    parser.add_argument("--max-scan-bytes", type=int, default=DEFAULT_MAX_SCAN_BYTES)
    parser.add_argument("--max-window-count", type=int, default=DEFAULT_MAX_WINDOW_COUNT)
    parser.add_argument("--alignment", type=int, default=64)
    parser.add_argument(
        "--post-snapshot-count", type=int, default=DEFAULT_POST_SNAPSHOT_COUNT
    )
    parser.add_argument(
        "--post-snapshot-delay",
        type=float,
        default=DEFAULT_POST_SNAPSHOT_DELAY_SECONDS,
    )
    parser.add_argument("--max-candidates", type=int, default=DEFAULT_MAX_CANDIDATES)
    parser.add_argument("--region-limit", type=int, default=2048)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    integer_options = {
        "window_size": args.window_size,
        "max_scan_bytes": args.max_scan_bytes,
        "max_window_count": args.max_window_count,
        "alignment": args.alignment,
        "post_snapshot_count": args.post_snapshot_count,
        "max_candidates": args.max_candidates,
        "region_limit": args.region_limit,
    }
    for name, value in integer_options.items():
        if value <= 0:
            raise SystemExit(f"ERROR: --{name.replace('_', '-')} must be positive")
    if args.post_snapshot_delay < 0:
        raise SystemExit("ERROR: --post-snapshot-delay must be non-negative")
    try:
        evidence_path, receipt_path, receipt = run_live(args)
    except (RamCandidateValidationError, RuntimeError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1) from exc
    print(f"EVIDENCE: {evidence_path}")
    print(f"RECEIPT: {receipt_path}")
    print(f"RESULT: {receipt['result']}")
    print(f"REASON: {receipt['reason']}")
    if receipt["selected_candidate_id"]:
        print(f"SELECTED: {receipt['selected_candidate_id']}")
        print("DOLPHIN_RAM_CANDIDATE_VALIDATED")
    if receipt["result"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
