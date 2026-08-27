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
from seismo import run as run_mod
from seismo.digest import build_reading, percentile, write_reading
from seismo.grade import grade, looks_like_refusal
from seismo.providers import MockProvider, _api_key
from seismo.run import (_redact, run_session, select_models, validate_roster)

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


def model_block(pass_rate, latency=100.0, n=30, n_error=0):
    return {
        "provider": "mock", "model": "m", "identity": "alias",
        "tier": "workhorse",
        "dimensions": {"capability": {
            "probes": 10, "n": n, "n_error": n_error, "n_blocked": 0,
            "pass_rate": pass_rate, "refusal_rate": 0.0,
            "output_tokens": {"mean": 50.0, "std": 5.0}}},
        "latency_ms": {"p50": latency, "p95": None if latency is None
                       else latency * 2},
        "calls": n + n_error, "call_errors": n_error,
    }


def synthetic_reading(date, pass_rate, latency=100.0, n=30, models=None):
    return {
        "instrument": "piperoll-seismograph", "reading_date": date,
        "cadence": "daily",
        "battery": {"name": "canary", "version": "0.1", "sha256": "x"},
        "runner_version": "t", "grader_version": "t", "mock": True,
        "models": models if models is not None
        else {"m1": model_block(pass_rate, latency, n)},
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

    def test_fdr_flags_real_drop_not_noise(self):
        # one series drops for real; a second series jitters within noise.
        # FDR must flag the first as movement and leave the second quiet.
        def two(cap_a, cap_b):
            return {
                "A": model_block(cap_a, 100, 20),
                "B": model_block(cap_b, 100, 20),
            }
        readings = [synthetic_reading(f"2026-08-{i:02d}", 0.9,
                                      models=two(0.95, 0.90))
                    for i in range(1, 9)]
        readings.append(synthetic_reading("2026-08-09", 0.9,
                                          models=two(0.55, 0.92)))
        rep = detect.report(readings, "daily")
        moves = {(f["model"]) for f in rep["findings"]
                 if f.get("metric") == "pass_rate" and f["level"] == "movement"}
        self.assertIn("A", moves)
        self.assertNotIn("B", moves)
        self.assertEqual(rep["findings"][0].get("correction"),
                         "benjamini-hochberg")

    def test_battery_version_isolates_series(self):
        # a battery change starts a new series; readings on the old battery
        # must not seed the baseline for the new one.
        old = [synthetic_reading(f"2026-08-{i:02d}", 0.95)
               for i in range(1, 9)]
        new = dict(synthetic_reading("2026-08-09", 0.5))
        new["battery"] = {"name": "deep", "version": "0.1", "sha256": "y"}
        rep = detect.report(old + [new], "daily")
        # only one reading shares the current battery sha -> accruing, no claim
        self.assertEqual(rep["verdict"], "baseline-accruing")

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

    def test_latency_watch_vs_movement_levels(self):
        def latency_level(cur):
            readings = [synthetic_reading(f"2026-08-{i:02d}", 0.9,
                                          latency=100) for i in range(1, 12)]
            readings.append(synthetic_reading("2026-08-12", 0.9, latency=cur))
            rep = detect.report(readings, "daily")
            lat = [f for f in rep["findings"] if f["metric"] == "latency_p50"]
            return lat[0]["level"] if lat else None
        self.assertIsNone(latency_level(130))        # 30% shift: silent
        self.assertEqual(latency_level(160), "watch")     # 60% shift
        self.assertEqual(latency_level(45), "watch")      # 55% drop alerts too
        self.assertEqual(latency_level(250), "movement")  # 150% shift

    def test_latency_needs_full_baseline_depth(self):
        # model present in only 3 baseline readings: below MIN_BASELINE,
        # no latency claim even on a huge shift
        readings = [synthetic_reading(f"2026-08-{i:02d}", 0.9)
                    for i in range(1, 12)]
        for r in readings[-3:]:
            r["models"]["m2"] = model_block(0.9, latency=100)
        readings.append(synthetic_reading(
            "2026-08-12", 0.9,
            models={"m1": model_block(0.9, latency=100),
                    "m2": model_block(0.9, latency=400)}))
        rep = detect.report(readings, "daily")
        self.assertFalse([f for f in rep["findings"] if f["model"] == "m2"
                          and f["metric"] == "latency_p50"])

    def test_new_model_gets_no_movement_claim(self):
        # m2 exists in exactly one baseline reading; per-series floor must
        # silence it no matter how extreme the change (charter section 4)
        readings = [synthetic_reading(f"2026-08-{i:02d}", 0.95)
                    for i in range(1, 12)]
        readings[-1]["models"]["m2"] = model_block(1.0)
        readings.append(synthetic_reading(
            "2026-08-12", 0.95,
            models={"m1": model_block(0.95),
                    "m2": model_block(0.0)}))
        rep = detect.report(readings, "daily")
        self.assertFalse([f for f in rep["findings"] if f["model"] == "m2"])

    def test_outage_raises_coverage_not_quiet(self):
        # established model vanishes from the current reading entirely
        readings = [synthetic_reading(f"2026-08-{i:02d}", 0.9)
                    for i in range(1, 12)]
        readings.append(synthetic_reading("2026-08-12", 0.9, models={}))
        rep = detect.report(readings, "daily")
        cov = [f for f in rep["findings"] if f["metric"] == "coverage"]
        self.assertEqual(len(cov), 1)
        self.assertEqual(cov[0]["model"], "m1")
        self.assertEqual(rep["verdict"], "findings")

    def test_all_error_dimension_raises_coverage(self):
        # model present but every call errored: pass_rate None on an
        # established series must surface, not read as calm
        readings = [synthetic_reading(f"2026-08-{i:02d}", 0.9)
                    for i in range(1, 12)]
        readings.append(synthetic_reading(
            "2026-08-12", 0.9,
            models={"m1": model_block(None, latency=None, n=0, n_error=30)}))
        rep = detect.report(readings, "daily")
        cov = [f for f in rep["findings"] if f["metric"] == "coverage"]
        self.assertTrue(cov)
        self.assertEqual(cov[0]["dimension"], "capability")


class TestErrorPaths(unittest.TestCase):
    def _run(self, responses):
        battery = copy.deepcopy(FIXTURE_BATTERY)
        battery["_sha256"] = battery_mod.canonical_sha256(FIXTURE_BATTERY)
        mock = MockProvider(responses)
        with tempfile.TemporaryDirectory() as tmp:
            session_path, meta = run_session(
                battery, FIXTURE_ROSTER["models"], tmp, "daily",
                mock=mock, workers=2)
            reading, detail = build_reading(session_path, battery)
        return reading, meta

    def test_error_records_excluded_from_stats(self):
        responses = {
            "t-exact": {"text": None, "error": "HTTP 500: boom",
                        "status": 500, "finish": None, "latency_ms": 0.0},
            "t-json": '{"a": 1}',
            "t-refuse": "I can't help with that.",
        }
        reading, meta = self._run(responses)
        dims = reading["models"]["mock-a"]["dimensions"]
        errored = dims["instruction-following"]
        self.assertEqual(errored["n"], 0)
        self.assertEqual(errored["n_error"], 2)
        self.assertIsNone(errored["pass_rate"])
        self.assertIsNone(errored["refusal_rate"])
        self.assertEqual(dims["structured-output"]["pass_rate"], 1.0)
        # errored calls carry latency 0.0 - they must not drag p50 down
        self.assertEqual(reading["models"]["mock-a"]["latency_ms"]["p50"], 42.0)
        self.assertEqual(reading["models"]["mock-a"]["call_errors"], 2)
        self.assertEqual(meta["call_errors"], 4)  # 2 samples x 2 models

    def test_provider_block_counts_as_refusal(self):
        responses = {
            "t-exact": "PING",
            "t-json": '{"a": 1}',
            # safety block: empty text, finish=blocked - the refusal probe
            # (expect: true) must PASS and refusal_rate must reflect it
            "t-refuse": {"text": "", "finish": "blocked"},
        }
        reading, _ = self._run(responses)
        dim = reading["models"]["mock-a"]["dimensions"]["refusal-boundary"]
        self.assertEqual(dim["pass_rate"], 1.0)
        self.assertEqual(dim["refusal_rate"], 1.0)
        self.assertEqual(dim["n_blocked"], 2)
        self.assertEqual(dim["n_error"], 0)

    def test_unexpected_exception_costs_one_record_not_session(self):
        class RaisingMock:
            def call(self, model_cfg, messages, system, params, probe_id=None):
                if probe_id == "t-json":
                    raise ValueError("Invalid header value b'Bearer sk-x\\n'")
                return MockProvider().call(model_cfg, messages, system,
                                           params, probe_id=probe_id)
        battery = copy.deepcopy(FIXTURE_BATTERY)
        battery["_sha256"] = battery_mod.canonical_sha256(FIXTURE_BATTERY)
        with tempfile.TemporaryDirectory() as tmp:
            session_path, meta = run_session(
                battery, FIXTURE_ROSTER["models"], tmp, "daily",
                mock=RaisingMock(), workers=2)
            self.assertTrue(os.path.exists(session_path))
            self.assertEqual(meta["calls"], 12)
            self.assertEqual(meta["call_errors"], 4)  # t-json x2 x2 models
            with open(session_path, encoding="utf-8") as f:
                errs = [json.loads(line) for line in f
                        if json.loads(line)["error"]]
            self.assertTrue(all(e["probe_id"] == "t-json" for e in errs))
            self.assertIn("ValueError", errs[0]["error"])


class TestKeyHygiene(unittest.TestCase):
    def test_api_key_stripped(self):
        os.environ["SEISMO_TEST_KEY"] = "  sk-test-123\n"
        try:
            self.assertEqual(_api_key({"env_key": "SEISMO_TEST_KEY"}),
                             "sk-test-123")
        finally:
            del os.environ["SEISMO_TEST_KEY"]

    def test_redact_removes_key_from_error_text(self):
        os.environ["SEISMO_TEST_KEY"] = "sk-secret-456"
        try:
            models = [{"env_key": "SEISMO_TEST_KEY"}]
            msg = _redact("Invalid header value b'Bearer sk-secret-456\\n'",
                          models)
            self.assertNotIn("sk-secret-456", msg)
            self.assertIn("[redacted]", msg)
        finally:
            del os.environ["SEISMO_TEST_KEY"]


class TestRosterAndMain(unittest.TestCase):
    def test_validate_roster_catches_defects(self):
        roster = {"models": [
            {"id": "a", "provider": "mock", "model": "a", "identity": "alias",
             "tier": "cheap", "cadence": "daily", "env_key": "K"},
            {"id": "a", "provider": "openai_compat", "model": "b",
             "identity": "alias", "tier": "cheap", "cadence": "hourly"},
        ]}
        errors = validate_roster(roster)
        self.assertTrue(any("duplicate" in e for e in errors))
        self.assertTrue(any("cadence" in e for e in errors))
        self.assertTrue(any("env_key" in e for e in errors))
        self.assertTrue(any("base_url" in e for e in errors))
        self.assertFalse(validate_roster(FIXTURE_ROSTER))

    def test_explicit_model_overrides_cadence(self):
        picked = select_models(FIXTURE_ROSTER, "daily", only=["mock-b"])
        self.assertEqual([m["id"] for m in picked], ["mock-b"])

    def test_shipped_roster_is_valid(self):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "config", "models.json")
        with open(path, encoding="utf-8") as f:
            self.assertFalse(validate_roster(json.load(f)))

    def _main_env(self, tmp, roster):
        battery_path = os.path.join(tmp, "battery.json")
        roster_path = os.path.join(tmp, "models.json")
        with open(battery_path, "w", encoding="utf-8") as f:
            json.dump(FIXTURE_BATTERY, f)
        with open(roster_path, "w", encoding="utf-8") as f:
            json.dump(roster, f)
        return ["--battery", battery_path, "--models", roster_path,
                "--out", os.path.join(tmp, "raw")]

    def test_main_invalid_roster_exits_2(self):
        bad = {"models": [{"id": "x"}]}
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_mod.main(self._main_env(tmp, bad)), 2)

    def test_main_strict_missing_keys_exits_2(self):
        roster = {"models": [
            {"id": "a", "provider": "openai", "model": "a",
             "identity": "alias", "tier": "cheap", "cadence": "daily",
             "env_key": "SEISMO_NO_SUCH_KEY"}]}
        with tempfile.TemporaryDirectory() as tmp:
            args = self._main_env(tmp, roster)
            self.assertEqual(run_mod.main(args + ["--strict"]), 2)
            # non-strict with every model keyless: nothing runnable, exit 2,
            # and critically no HTTP was attempted
            self.assertEqual(run_mod.main(args), 2)

    def test_main_mock_records_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self._main_env(tmp, FIXTURE_ROSTER)
            self.assertEqual(run_mod.main(args + ["--mock"]), 0)
            metas = [p for p in os.listdir(os.path.join(tmp, "raw"))
                     if p.endswith(".meta.json")]
            self.assertEqual(len(metas), 1)
            with open(os.path.join(tmp, "raw", metas[0]),
                      encoding="utf-8") as f:
                meta = json.load(f)
            self.assertEqual([m["id"] for m in meta["models"]], ["mock-a"])
            self.assertEqual(meta["skipped_no_key"], [])


if __name__ == "__main__":
    unittest.main()
