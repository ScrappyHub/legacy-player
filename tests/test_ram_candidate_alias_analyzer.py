import unittest

from tests.test_ram_candidate_validator import make_evidence, snapshot
from tools.memory_probe.dolphin_attach.ram_candidate_alias_analyzer import (
    analyze_aliases,
)
from tools.memory_probe.dolphin_attach.ram_candidate_validator import build_receipt


class RamCandidateAliasAnalyzerTests(unittest.TestCase):
    def test_near_identical_candidates_are_diagnostic_only(self):
        evidence = make_evidence(
            first_posts=[snapshot(b"AAAZ", b"BBBB")],
            second_posts=[snapshot(b"AAAZ", b"BBBB")],
        )
        # Make both baselines and mutation positions equivalent.
        evidence["candidates"][1]["baseline"] = evidence["candidates"][0]["baseline"]
        from tools.memory_probe.dolphin_attach.ram_candidate_validator import document_sha256

        evidence["evidence_sha256"] = document_sha256(evidence, "evidence_sha256")
        receipt = build_receipt(evidence)
        analysis = analyze_aliases(evidence, receipt)

        self.assertEqual("probable_mirror_detected", analysis["result"])
        self.assertEqual("probable_mirror", analysis["pairs"][0]["classification"])
        self.assertFalse(analysis["authority_claimed"])
        self.assertEqual("fail", receipt["result"])

    def test_distinct_candidates_remain_distinct(self):
        evidence = make_evidence(
            first_posts=[snapshot(b"AAAZ", b"BBBB")],
            second_posts=[snapshot(b"CCCZ", b"DDDD")],
        )
        receipt = build_receipt(evidence)
        analysis = analyze_aliases(evidence, receipt)

        self.assertEqual("no_probable_mirror", analysis["result"])
        self.assertEqual("distinct", analysis["pairs"][0]["classification"])


if __name__ == "__main__":
    unittest.main()

