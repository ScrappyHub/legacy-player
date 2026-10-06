import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.memory_probe.dolphin_attach.ram_candidate_validator import (
    RamCandidateValidationError,
    build_evidence,
    build_receipt,
    capture_windows,
    document_sha256,
    verify_receipt,
    write_verified_json,
)


REGION_SIZE = 0x02000000
OFFSETS = [0, 64]
WINDOW_SIZE = 4


def window(offset, data):
    return {
        "offset": offset,
        "size": WINDOW_SIZE,
        "data_hex": None if data is None else bytes(data).hex(),
    }


def snapshot(first, second):
    return [window(0, first), window(64, second)]


def candidate(base):
    return {
        "base_address": base,
        "region_size": REGION_SIZE,
        "protect": 0x04,
        "type": 0x40000,
        "is_exact_gamecube_ram_size": True,
        "is_mapped": True,
        "zero_filled_head": False,
    }


def make_evidence(*, first_posts, second_posts, first_baseline=None, noncanonical=None):
    candidates = [candidate(0x200000000), candidate(0x300000000)]
    baselines = {
        "candidate-000": first_baseline or snapshot(b"AAAA", b"BBBB"),
        "candidate-001": snapshot(b"CCCC", b"DDDD"),
    }
    posts = {
        "candidate-000": first_posts,
        "candidate-001": second_posts,
    }
    return build_evidence(
        subject={
            "emulator": "dolphin",
            "game_id": "GMPE01",
            "region": "USA",
            "action_label": "coin_change_once",
            "identity_assurance": "test-fixture",
        },
        candidates=candidates,
        offsets=OFFSETS,
        window_size=WINDOW_SIZE,
        baseline_windows=baselines,
        post_snapshots=posts,
        noncanonical=noncanonical,
    )


class RamCandidateValidatorTests(unittest.TestCase):
    def test_capture_normalizes_partial_read_to_explicit_failure(self):
        region = candidate(0x200000000)
        captured = capture_windows(
            object(), region, [0], WINDOW_SIZE, lambda proc, address, size: b"AAA"
        )
        self.assertIsNone(captured[0]["data_hex"])

    def test_unique_mutation_passes_and_receipt_recomputes(self):
        evidence = make_evidence(
            first_posts=[snapshot(b"AAAZ", b"BBBB")],
            second_posts=[snapshot(b"CCCC", b"DDDD")],
        )
        receipt = build_receipt(evidence)

        self.assertEqual("pass", receipt["result"])
        self.assertEqual("unique_behavioral_candidate", receipt["reason"])
        self.assertEqual("candidate-000", receipt["selected_candidate_id"])
        self.assertEqual(["DOLPHIN_RAM_CANDIDATE_VALIDATED"], receipt["claims"])
        self.assertEqual("pass", verify_receipt(evidence, receipt)["result"])

    def test_multiple_mutating_candidates_fail_as_ambiguous(self):
        evidence = make_evidence(
            first_posts=[snapshot(b"AAAZ", b"BBBB")],
            second_posts=[snapshot(b"CCCZ", b"DDDD")],
        )
        receipt = build_receipt(evidence)

        self.assertEqual("fail", receipt["result"])
        self.assertEqual("ambiguous_mutation", receipt["reason"])
        self.assertIsNone(receipt["selected_candidate_id"])
        self.assertEqual([], receipt["claims"])
        self.assertEqual("pass", verify_receipt(evidence, receipt)["result"])

    def test_no_mutation_fails_explicitly(self):
        evidence = make_evidence(
            first_posts=[snapshot(b"AAAA", b"BBBB")],
            second_posts=[snapshot(b"CCCC", b"DDDD")],
        )
        receipt = build_receipt(evidence)

        self.assertEqual("fail", receipt["result"])
        self.assertEqual("no_candidate_mutated", receipt["reason"])

    def test_failed_or_partial_read_fails_closed(self):
        evidence = make_evidence(
            first_baseline=[window(0, None), window(64, b"BBBB")],
            first_posts=[snapshot(b"AAAZ", b"BBBB")],
            second_posts=[snapshot(b"CCCC", b"DDDD")],
        )
        receipt = build_receipt(evidence)

        self.assertEqual("fail", receipt["result"])
        self.assertEqual("capture_incomplete", receipt["reason"])
        self.assertGreater(receipt["candidates"][0]["read_error_count"], 0)

    def test_noncanonical_metadata_does_not_change_evidence_digest(self):
        common = dict(
            first_posts=[snapshot(b"AAAZ", b"BBBB")],
            second_posts=[snapshot(b"CCCC", b"DDDD")],
        )
        first = make_evidence(
            **common,
            noncanonical={"pid": 111, "captured_at_utc": "2026-01-01T00:00:00Z"},
        )
        second = make_evidence(
            **common,
            noncanonical={"pid": 222, "captured_at_utc": "2027-01-01T00:00:00Z"},
        )

        self.assertEqual(first["evidence_sha256"], second["evidence_sha256"])

    def test_corrupted_evidence_and_forged_decision_are_rejected(self):
        evidence = make_evidence(
            first_posts=[snapshot(b"AAAZ", b"BBBB")],
            second_posts=[snapshot(b"CCCC", b"DDDD")],
        )
        receipt = build_receipt(evidence)

        corrupted = copy.deepcopy(evidence)
        corrupted["candidates"][0]["post_snapshots"][0]["windows"][0][
            "data_hex"
        ] = b"AAAA".hex()
        with self.assertRaisesRegex(RamCandidateValidationError, "evidence_sha256"):
            verify_receipt(corrupted, receipt)

        forged = copy.deepcopy(receipt)
        forged["selected_candidate_id"] = "candidate-001"
        forged["content_sha256"] = document_sha256(forged, "content_sha256")
        with self.assertRaisesRegex(RamCandidateValidationError, "recomputed evidence"):
            verify_receipt(evidence, forged)

    def test_malformed_partial_bytes_are_rejected_even_with_valid_digest(self):
        evidence = make_evidence(
            first_posts=[snapshot(b"AAAZ", b"BBBB")],
            second_posts=[snapshot(b"CCCC", b"DDDD")],
        )
        evidence["candidates"][0]["baseline"][0]["data_hex"] = b"AAA".hex()
        evidence["evidence_sha256"] = document_sha256(evidence, "evidence_sha256")

        with self.assertRaisesRegex(RamCandidateValidationError, "partial memory read"):
            build_receipt(evidence)

    def test_verified_json_write_round_trips_exact_object(self):
        evidence = make_evidence(
            first_posts=[snapshot(b"AAAZ", b"BBBB")],
            second_posts=[snapshot(b"CCCC", b"DDDD")],
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            write_verified_json(path, evidence)
            self.assertEqual(evidence, json.loads(path.read_text(encoding="utf-8")))
            self.assertFalse(path.read_bytes().startswith(b"\xef\xbb\xbf"))


if __name__ == "__main__":
    unittest.main()
