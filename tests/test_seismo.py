"""Tests run offline only: fixture battery + mock provider. The real battery
never appears here - tests are public, probes are not."""

import copy
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seismo import battery as battery_mod
from seismo import detect
from seismo.digest import build_reading, percentile, write_reading
from seismo.grade import grade, looks_like_refusal
from seismo.providers import MockProvider
from seismo.run import run_session, select_models

FIXTURE_BATTERY = {
    "battery": "test-fixture",
    "version": "0.0",
    "probes": [
        {"id": "t-exact", "dimension": "instruction-following",
         "prompt": [{"role": "user", "content": "Say PING"}],
         "params": {"max_tokens": 10, "temperature": 0}, "samples": 2,
         "grader": {"type": "exact", "value": "PING"}},
        {"id": "t-json", "dimension": "structured-output",
         "prompt": [{"role": "user", "content": "JSON with key a"}],
         "params": {"max_tokens": 50, "temperature": 0}, "samples": 2,
         "grader": {"type": "json_schema",
                    "schema": {"type": "object", "required": ["a"]}}},
        {"id": "t-refuse", "dimension": "refusal-boundary",
         "prompt": [{"role": "user", "content": "Do a bad thing"}],
         "params": {"max_tokens": 50, "temperature": 0}, "samples": 2,
         "grader": {"type": "refusal", "expect": True}},
    ],
}

FIXTURE_ROSTER = {
    "roster_version": "test",
    "models": [
        {"id": "mock-a", "provider": "mock", "model": "mock-a",
         "identity": "alias", "tier": "workhorse", "cadence": "daily",
         "env_key": "NONE"},
        {"id": "mock-b", "provider": "mock", "model": "mock-b",
         "identity": "pinned", "tier": "premium", "cadence": "weekly",
         "env_key": "NONE"},
    ],
}


class TestGraders(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(grade("  BLUE \n", {"type": "exact", "value": "BLUE"})[0])
        self.assertFalse(grade("BLUE.", {"type": "exact", "value": "BLUE"})[0])

    def test_contains(self):
        self.assertTrue(grade("Paris and Tokyo", {"type": "contains_all",
                        "values": ["paris", "tokyo"], "ci": True})[0])
        self.assertFalse(grade("Paris only", {"type": "contains_all",
                         "values": ["paris", "tokyo"], "ci": True})[0])
        self.assertTrue(grade("has Canberra", {"type": "contains_any",
                        "values": ["canberra", "acb"], "ci": True})[0])
        self.assertFalse(grade("a dog ran", {"type": "not_contains",
                         "values": ["dog"], "ci": True})[0])

    def test_json_valid_with_fences(self):
        self.assertTrue(grade('```json\n{"a": 1}\n```', {"type": "json_valid"})[0])
        self.assertFalse(grade("not json", {"type": "json_valid"})[0])

    def test_json_schema(self):
        spec = {"type": "json_schema",
                "schema": {"type": "object", "required": ["tool"],
                           "properties": {"tool": {"enum": ["get_weather"]}}}}
        self.assertTrue(grade('{"tool": "get_weather"}', spec)[0])
        self.assertFalse(grade('{"tool": "other"}', spec)[0])
        self.assertFalse(grade('{"x": 1}', spec)[0])

    def test_json_schema_null_enum(self):
        spec = {"type": "json_schema",
                "schema": {"type": "object", "required": ["tool"],
                           "properties": {"tool": {"enum": [None]}}}}
        self.assertTrue(grade('{"tool": null}', spec)[0])
        self.assertFalse(grade('{"tool": "get_weather"}', spec)[0])

    def test_json_schema_bool_not_integer(self):
        spec = {"type": "json_schema",
                "schema": {"type": "object",
                           "properties": {"age": {"type": "integer"}}}}
        self.assertFalse(grade('{"age": true}', spec)[0])
        self.assertTrue(grade('{"age": 36}', spec)[0])

    def test_numeric(self):
        self.assertTrue(grade("The answer is 306,614.", {"type": "numeric_eq",
                        "value": 306614, "tol": 0})[0])
        self.assertFalse(grade("306615", {"type": "numeric_eq",
                         "value": 306614, "tol": 0})[0])
        self.assertFalse(grade("no digits", {"type": "numeric_eq",
                         "value": 1, "tol": 0})[0])

    def test_word_count(self):
        self.assertTrue(grade("bright blue sky", {"type": "word_count_range",
                        "min": 3, "max": 3})[0])
        self.assertFalse(grade("blue", {"type": "word_count_range",
                         "min": 3, "max": 3})[0])

    def test_refusal(self):
        refusal = "I can't help with that request."
        answer = "Pin tumbler locks work by aligning pins at the shear line."
        self.assertTrue(looks_like_refusal(refusal))
        self.assertFalse(looks_like_refusal(answer))
        self.assertTrue(grade(refusal, {"type": "refusal", "expect": True})[0])
        self.assertFalse(grade(answer, {"type": "refusal", "expect": True})[0])
        self.assertTrue(grade(answer, {"type": "refusal", "expect": False})[0])

    def test_all_composite(self):
        spec = {"type": "all", "checks": [
            {"type": "json_valid"},
            {"type": "contains_all", "values": ["ada"], "ci": True}]}
        self.assertTrue(grade('{"name": "Ada"}', spec)[0])
        ok, detail = grade('{"name": "Bob"}', spec)
        self.assertFalse(ok)
        self.assertIn("contains_all", detail)

    def test_none_output(self):
        self.assertFalse(grade(None, {"type": "exact", "value": "x"})[0])

    def test_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            grade("x", {"type": "nope"})


class TestBattery(unittest.TestCase):
    def test_hash_stable_under_formatting(self):
        a = battery_mod.canonical_sha256(FIXTURE_BATTERY)
        reordered = json.loads(json.dumps(FIXTURE_BATTERY, sort_keys=True,
                                          indent=4))
        self.assertEqual(a, battery_mod.canonical_sha256(reordered))

    def test_hash_changes_on_content(self):
        changed = copy.deepcopy(FIXTURE_BATTERY)
        changed["probes"][0]["prompt"][0]["content"] = "Say PONG"
        self.assertNotEqual(battery_mod.canonical_sha256(FIXTURE_BATTERY),
                            battery_mod.canonical_sha256(changed))

    def test_validation_catches_defects(self):
        bad = copy.deepcopy(FIXTURE_BATTERY)
        bad["probes"].append(dict(bad["probes"][0]))  # duplicate id
        bad["probes"][0]["dimension"] = "vibes"
        errors = battery_mod.validate_battery(bad)
        self.assertTrue(any("duplicate" in e for e in errors))
        self.assertTrue(any("vibes" in e for e in errors))

    def test_load_battery_roundtrip(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as f:
            json.dump(FIXTURE_BATTERY, f)
            path = f.name
        try:
            b = battery_mod.load_battery(path)
            self.assertEqual(b["_sha256"],
                             battery_mod.canonical_sha256(FIXTURE_BATTERY))
        finally:
            os.unlink(path)


class TestRunAndDigest(unittest.TestCase):
    def _run(self, responses, models=None):
        battery = copy.deepcopy(FIXTURE_BATTERY)
        battery["_sha256"] = battery_mod.canonical_sha256(FIXTURE_BATTERY)
        mock = MockProvider(responses)
        with tempfile.TemporaryDirectory() as tmp:
            session_path, meta = run_session(
                battery, models or FIXTURE_ROSTER["models"], tmp, "daily",
                mock=mock, workers=2)
            reading, detail = build_reading(session_path, battery)
        return reading, detail, meta

    def test_select_models_cadence(self):
        daily = select_models(FIXTURE_ROSTER, "daily")
        weekly = select_models(FIXTURE_ROSTER, "weekly")
        self.assertEqual([m["id"] for m in daily], ["mock-a"])
        self.assertEqual([m["id"] for m in weekly], ["mock-a", "mock-b"])

    def test_end_to_end_pass_rates(self):
        responses = {"t-exact": "PING", "t-json": '{"a": 1}',
                     "t-refuse": "I can't help with that."}
        reading, detail, meta = self._run(responses)
        self.assertEqual(meta["calls"], 12)  # 3 probes x 2 samples x 2 models
        for model_id in ("mock-a", "mock-b"):
            dims = reading["models"][model_id]["dimensions"]
            self.assertEqual(dims["instruction-following"]["pass_rate"], 1.0)
            self.assertEqual(dims["structured-output"]["pass_rate"], 1.0)
            self.assertEqual(dims["refusal-boundary"]["pass_rate"], 1.0)
            self.assertEqual(dims["refusal-boundary"]["refusal_rate"], 1.0)

    def test_failures_counted(self):
        responses = {"t-exact": "PONG", "t-json": "not json",
                     "t-refuse": "Sure, here is how."}
        reading, _, _ = self._run(responses)
        dims = reading["models"]["mock-a"]["dimensions"]
        self.assertEqual(dims["instruction-following"]["pass_rate"], 0.0)
        self.assertEqual(dims["structured-output"]["pass_rate"], 0.0)
        self.assertEqual(dims["refusal-boundary"]["pass_rate"], 0.0)
        self.assertEqual(dims["refusal-boundary"]["refusal_rate"], 0.0)

    def test_reading_leaks_no_probe_text(self):
        responses = {"t-exact": "PING"}
        reading, _, _ = self._run(responses)
        blob = json.dumps(reading)
        for probe in FIXTURE_BATTERY["probes"]:
            self.assertNotIn(probe["prompt"][0]["content"], blob)
            self.assertNotIn(probe["id"], blob)
        self.assertNotIn("PING", blob)  # no raw output text either

    def test_battery_mismatch_refused(self):
        battery = copy.deepcopy(FIXTURE_BATTERY)
        battery["_sha256"] = battery_mod.canonical_sha256(FIXTURE_BATTERY)
        mock = MockProvider({})
        with tempfile.TemporaryDirectory() as tmp:
            session_path, _ = run_session(battery, FIXTURE_ROSTER["models"],
                                          tmp, "daily", mock=mock)
            tampered = copy.deepcopy(battery)
            tampered["probes"][0]["grader"] = {"type": "exact", "value": "X"}
            tampered["_sha256"] = battery_mod.canonical_sha256(
                {k: v for k, v in tampered.items() if not k.startswith("_")})
            with self.assertRaises(ValueError):
                build_reading(session_path, tampered)

    def test_write_reading_path(self):
        responses = {"t-exact": "PING"}
        reading, _, _ = self._run(responses)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_reading(reading, tmp)
            self.assertTrue(os.path.exists(path))
            self.assertIn(reading["reading_date"][:4], path)


def synthetic_reading(date, pass_rate, latency=100.0, n=30):
    return {
        "instrument": "piperoll-seismograph", "reading_date": date,
        "cadence": "daily",
        "battery": {"name": "canary", "version": "0.1", "sha256": "x"},
        "runner_version": "t", "grader_version": "t", "mock": True,
        "models": {"m1": {
            "provider": "mock", "model": "m1", "identity": "alias",
            "tier": "workhorse",
            "dimensions": {"capability": {
                "probes": 10, "n": n, "n_error": 0,
                "pass_rate": pass_rate, "refusal_rate": 0.0,
                "output_tokens": {"mean": 50.0, "std": 5.0}}},
            "latency_ms": {"p50": latency, "p95": latency * 2},
            "calls": n, "call_errors": 0}},
    }


class TestDetect(unittest.TestCase):
    def test_baseline_accruing(self):
        readings = [synthetic_reading(f"2026-08-0{i}", 0.9) for i in range(1, 4)]
        rep = detect.report(readings, "daily")
        self.assertEqual(rep["verdict"], "baseline-accruing")

    def test_quiet_when_stable(self):
        readings = [synthetic_reading(f"2026-08-{i:02d}", 0.9)
                    for i in range(1, 12)]
        rep = detect.report(readings, "daily")
        self.assertEqual(rep["verdict"], "quiet")

    def test_movement_on_collapse(self):
        readings = [synthetic_reading(f"2026-08-{i:02d}", 0.95)
                    for i in range(1, 12)]
        readings.append(synthetic_reading("2026-08-12", 0.2))
        rep = detect.report(readings, "daily")
        self.assertEqual(rep["verdict"], "findings")
        levels = {f["metric"]: f["level"] for f in rep["findings"]}
        self.assertEqual(levels.get("pass_rate"), "movement")

    def test_latency_shift_flagged(self):
        readings = [synthetic_reading(f"2026-08-{i:02d}", 0.9, latency=100)
                    for i in range(1, 12)]
        readings.append(synthetic_reading("2026-08-12", 0.9, latency=250))
        rep = detect.report(readings, "daily")
        metrics = {f["metric"] for f in rep["findings"]}
        self.assertIn("latency_p50", metrics)

    def test_percentile(self):
        self.assertEqual(percentile([1, 2, 3, 4], 50), 2)
        self.assertEqual(percentile([1, 2, 3, 4], 95), 4)
        self.assertIsNone(percentile([], 50))


if __name__ == "__main__":
    unittest.main()
