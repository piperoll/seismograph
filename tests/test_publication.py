"""Publication regressions: assessment is separate from findings and evidence links.

Fixtures are aggregate statistics only, with no private probes or model output.
"""

import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import gen_pages


class TestPublication(unittest.TestCase):
    def test_model_with_findings_does_not_claim_nothing_was_flagged(self):
        model = {"dates": ["2026-09-15"], "provider": "test", "call_errors": [0]}
        finding = {"model": "test-model", "dimension": "sycophancy",
                   "metric": "thinking_tokens_mean", "level": "movement",
                   "baseline": 10, "current": 40}
        series = {"daily": {"models": {"test-model": model}},
                  "weekly": {"models": {"test-model": model}}}
        advisories = {
            "log": [{"cadence": "daily", "date": "2026-09-15", "finding": finding}],
            "cadence": {
                "daily": {"assessment": [{"model": "test-model", "status": "assessed",
                                           "eligible": 13, "attempted": 13}]},
                "weekly": {"assessment": [{"model": "test-model", "status": "baseline",
                                            "eligible": 0, "attempted": 13}]}}}
        with tempfile.TemporaryDirectory() as tmp:
            paths = gen_pages.build_static_pages(series, advisories, tmp)
            model_page = (Path(tmp) / "models/test-model/index.html").read_text()
            index = (Path(tmp) / "models/index.html").read_text()
            self.assertNotIn("No findings", model_page)
            self.assertNotIn("No findings", index)
            self.assertIn("Assessed (13/13 metrics eligible)", model_page)
            self.assertIn("Baseline accruing (0/13 metrics eligible)", model_page)
            self.assertIn("cadence=daily", model_page)
            self.assertIn("cadence=weekly", model_page)
            self.assertIn("/models/test-model/", paths)

    def test_unassessable_models_do_not_receive_a_quiet_verdict(self):
        model = {"dates": ["2026-09-15"], "provider": "test"}
        for status in ("coverage", "baseline", "partial", "absent"):
            with self.subTest(status=status):
                page = gen_pages._model_page("test", model, None,
                    {"daily": {"status": status, "eligible": 0, "attempted": 7}}, [])
                self.assertNotIn("No movement or watch", page)
                self.assertNotIn("No findings in completed", page)

    def test_reading_bundle_requires_matching_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "readings/2026").mkdir(parents=True)
            (root / "witness").mkdir()
            raw = b'{"reading_date":"2026-09-15"}\n'
            (root / "readings/2026/reading-2026-09-15-daily.json").write_bytes(raw)
            bundle = root / "witness/2026-09-15T120000Z-reading-2026-09-15-daily.json.bundle.json"
            def write_digest(digest):
                bundle.write_text(json.dumps({"messageSignature": {"messageDigest": {
                    "algorithm": "SHA2_256", "digest": base64.b64encode(digest).decode()}}}))
            write_digest(hashlib.sha256(b"different reading").digest())
            self.assertEqual({}, gen_pages.reading_witnesses(root))
            write_digest(hashlib.sha256(raw).digest())
            links = gen_pages.reading_witnesses(root)
            self.assertEqual(links["2026-09-15|daily"],
                             f"{gen_pages.REPO}/blob/main/witness/{bundle.name}")
            bundle.write_text("invalid JSON")
            self.assertEqual({}, gen_pages.reading_witnesses(root))

    def test_missing_bundle_is_labelled_as_directory(self):
        finding = {"model": "test", "metric": "latency_p50", "dimension": "-",
                   "baseline": 1000, "current": 3000, "level": "movement"}
        item = {"f": finding, "model": "test", "cad": "daily", "metric": "latency_p50",
                "level": "context", "onset": "2026-09-15", "latest": "2026-09-15", "n": 1}
        page = gen_pages._finding_page(item, {})
        self.assertIn("Rekor witness directory</a>", page)
        self.assertNotIn("Rekor witness bundle</a>", page)
        self.assertIn(">Context</span>", page)
        linked = gen_pages._finding_page(item, {}, {"2026-09-15|daily": "https://example.com/bundle.json"})
        self.assertIn('href="https://example.com/bundle.json">Rekor witness bundle</a>', linked)


if __name__ == "__main__":
    unittest.main()
