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

    def test_identity_is_stated_on_model_and_finding_pages(self):
        for kind, label in (("alias", "alias"), ("pinned", "pinned snapshot"), (None, "not recorded")):
            with self.subTest(identity=kind):
                model = {"dates": ["2026-09-15"], "provider": "test", "identity": kind}
                page = gen_pages._model_page("test", model, None,
                    {"daily": {"status": "assessed", "eligible": 7, "attempted": 7}}, [])
                self.assertIn(f"<th>identity</th><td>{label}", page)
        series = {"daily": {"models": {"m": {"dates": ["2026-09-15"], "call_errors": [0],
                                             "identity": "pinned"}}}}
        it = {"f": {"model": "m", "dimension": "capability", "metric": "pass_rate",
                    "baseline": 1.0, "current": 0.5, "level": "movement"},
              "cad": "daily", "model": "m", "metric": "pass_rate", "level": "movement",
              "onset": "2026-09-15", "latest": "2026-09-15", "n": 1}
        page = gen_pages._finding_page(it, series)
        self.assertIn("<th>identity</th><td>pinned snapshot", page)
        self.assertIn("snapshot itself changed", page)

    def test_thinking_movement_states_the_pass_rate_pattern(self):
        def item(onset="2026-09-10"):
            return {"f": {"model": "m", "dimension": "sycophancy", "metric": "thinking_tokens_mean",
                          "baseline": 90.0, "current": 1100.0, "level": "movement", "shift": 11.0},
                    "cad": "daily", "model": "m", "metric": "thinking_tokens_mean",
                    "level": "movement", "onset": onset, "latest": onset, "n": 1}
        dates = [f"2026-09-{d:02d}" for d in range(3, 11)]
        flat = {"daily": {"models": {"m": {"dates": dates, "call_errors": [0] * 8,
                                           "dims": {"sycophancy": [1.0] * 8}}}}}
        page = gen_pages._finding_page(item(), flat)
        self.assertIn("stayed flat", page)
        self.assertIn("serving-side change", page)
        moved = {"daily": {"models": {"m": {"dates": dates, "call_errors": [0] * 8,
                                            "dims": {"sycophancy": [1.0] * 7 + [0.6]}}}}}
        page = gen_pages._finding_page(item(), moved)
        self.assertIn("moved together", page)
        # not a thinking movement: no pattern paragraph
        it = item(); it["f"]["metric"] = "pass_rate"; it["metric"] = "pass_rate"
        self.assertNotIn("Pattern:", gen_pages._finding_page(it, flat))

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


class TestAnnotations(unittest.TestCase):
    def _item(self, onset="2026-10-17", dim="instruction-following", metric="pass_rate"):
        return {"f": {"model": "m", "dimension": dim, "metric": metric,
                      "baseline": 1.0, "current": 0.6, "level": "movement"},
                "cad": "daily", "model": "m", "metric": metric, "level": "movement",
                "onset": onset, "latest": onset, "n": 1}

    def test_matching_annotation_renders_with_sources_and_framing(self):
        ann = [{"scope": "finding", "model": "m", "cadence": "daily", "onset": "2026-10-17",
                "dimension": "instruction-following", "metric": "pass_rate",
                "title": "Provider record", "text": "Changelog entry dated 2026-10-17.",
                "sources": [{"label": "Changelog", "url": "https://example.com/updates"}],
                "added": "2026-10-21"}]
        series = {"daily": {"models": {"m": {"dates": ["2026-10-17"], "call_errors": [0]}}}}
        page = gen_pages._finding_page(self._item(), series, None, ann)
        self.assertIn("Provider record", page)
        self.assertIn("Changelog entry dated 2026-10-17.", page)
        self.assertIn('href="https://example.com/updates"', page)
        self.assertIn("establishes no cause", page)
        self.assertIn("Annotation added 2026-10-21", page)

    def test_non_matching_annotation_stays_off_the_page(self):
        ann = [{"scope": "finding", "model": "m", "cadence": "daily", "onset": "2026-10-17",
                "dimension": "sycophancy", "title": "Wrong dimension", "text": "x"},
               {"scope": "finding", "model": "m", "cadence": "daily", "onset": "2026-10-18",
                "title": "Wrong onset", "text": "x"},
               {"scope": "finding", "model": "other", "cadence": "daily", "onset": "2026-10-17",
                "title": "Wrong model", "text": "x"}]
        series = {"daily": {"models": {"m": {"dates": ["2026-10-17"], "call_errors": [0]}}}}
        page = gen_pages._finding_page(self._item(), series, None, ann)
        for title in ("Wrong dimension", "Wrong onset", "Wrong model"):
            self.assertNotIn(title, page)
        self.assertNotIn("Dated records alongside", page)

    def test_entry_without_dimension_matches_every_finding_at_that_onset(self):
        ann = [{"scope": "finding", "model": "m", "cadence": "daily", "onset": "2026-10-17",
                "title": "Broad", "text": "x"}]
        self.assertEqual(1, len(gen_pages.finding_annotations(self._item(dim="verbosity", metric="thinking_tokens_mean"), ann)))

    def test_model_scope_renders_on_model_page_only(self):
        ann = [{"scope": "model", "model": "m", "date": "2026-10-08",
                "title": "Alias retired", "text": "Routed to the successor.",
                "sources": [{"label": "Changelog", "url": "https://example.com/c"}], "added": "2026-10-21"}]
        model = {"dates": ["2026-10-17"], "provider": "test", "identity": "alias"}
        page = gen_pages._model_page("m", model, None,
            {"daily": {"status": "assessed", "eligible": 7, "attempted": 7}}, [], ann)
        self.assertIn("Editorial notes", page)
        self.assertIn("Alias retired", page)
        self.assertIn("Routed to the successor.", page)
        series = {"daily": {"models": {"m": {"dates": ["2026-10-17"], "call_errors": [0]}}}}
        self.assertNotIn("Alias retired", gen_pages._finding_page(self._item(), series, None, ann))

    def test_shipped_annotations_match_published_findings(self):
        root = Path(__file__).resolve().parents[1]
        ann = gen_pages.load_annotations(root)
        self.assertTrue(ann)
        for a in ann:
            self.assertIn(a.get("scope"), ("finding", "model"))
            self.assertTrue(a.get("model") and a.get("title") and a.get("text") and a.get("added"))
            self.assertNotRegex(a["text"].lower(), r"\b(caused by|because of|due to)\b",
                                "annotations state records, not causes")
