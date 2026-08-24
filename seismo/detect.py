"""Advisory baseline comparison across readings.

Charter decision 3 governs everything here: under-alerting is policy. This
module never says "drift" - it reports "movement" (survives Bonferroni
correction) and "watch" (nominally significant, could be noise). Claims about
causes belong to humans; this is a needle, not an analyst.

With fewer than MIN_BASELINE readings the verdict is always "baseline
accruing" - the instrument stays silent while the ruler is short.

Usage:
    python3 -m seismo.detect [--readings readings] [--cadence daily]
"""

import argparse
import glob
import json
import math
import os
import sys

MIN_BASELINE = 7
BASELINE_WINDOW = 14
ALPHA = 0.01
LATENCY_WATCH = 0.5   # relative p50 shift vs baseline median
THINKING_WATCH = 0.5    # relative shift in mean thinking tokens per dimension
THINKING_MOVEMENT = 1.0  # a silent effort/serving remap shows here first
LATENCY_MOVEMENT = 1.0


def two_proportion_p(x1, n1, x2, n2):
    """Two-sided p-value for difference of proportions (pooled z-test)."""
    if n1 == 0 or n2 == 0:
        return 1.0
    p1, p2 = x1 / n1, x2 / n2
    pooled = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (p1 - p2) / se
    return math.erfc(abs(z) / math.sqrt(2))


def load_readings(readings_dir, cadence):
    paths = sorted(glob.glob(os.path.join(readings_dir, "*",
                                          f"reading-*-{cadence}.json")))
    out = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            out.append(json.load(f))
    return out


def _series_stats(baseline_readings, model_id, dim):
    """Pooled baseline for one model+dimension series at PROBE granularity.

    Repeat samples of the same probe at temperature 0 are correlated, not
    independent trials - treating calls as Bernoulli trials understates the
    standard error by ~sqrt(samples) and manufactures spurious movement. The
    unit of evidence is the probe-day: pass_rate x probe count per reading.
    Returns (pass_units, total_units, readings_with_series).
    """
    passes, units, depth = 0, 0, 0
    for r in baseline_readings:
        bm = r["models"].get(model_id)
        bd = bm["dimensions"].get(dim) if bm else None
        if bd and bd["pass_rate"] is not None and bd.get("probes"):
            passes += round(bd["pass_rate"] * bd["probes"])
            units += bd["probes"]
            depth += 1
    return passes, units, depth


def compare(current, baseline_readings):
    """Compare one reading against a pooled baseline. Returns finding dicts.

    The charter's 7-reading floor applies PER SERIES (model x dimension), not
    to the readings directory: a model added to the roster yesterday accrues
    its own baseline before any claim is made about it.
    """
    comparisons = []
    coverage = []
    for model_id, model in current["models"].items():
        for dim, stats in model["dimensions"].items():
            base_pass, base_units, depth = _series_stats(
                baseline_readings, model_id, dim)
            if stats["pass_rate"] is None:
                if depth >= MIN_BASELINE:
                    coverage.append({
                        "model": model_id, "dimension": dim,
                        "metric": "coverage", "level": "watch",
                        "detail": "established series returned no gradable "
                                  "calls in the current reading"})
                continue
            if depth < MIN_BASELINE:
                continue
            n_units = stats.get("probes") or 0
            if not n_units:
                continue
            cur_pass = round(stats["pass_rate"] * n_units)
            p = two_proportion_p(cur_pass, n_units, base_pass, base_units)
            comparisons.append({
                "model": model_id, "dimension": dim, "metric": "pass_rate",
                "current": stats["pass_rate"],
                "baseline": round(base_pass / base_units, 4),
                "n_units": n_units, "baseline_units": base_units,
                "baseline_depth": depth, "p": p,
            })

    # an established model absent from the current reading entirely is the
    # loudest data gap of all - a detector that reports calm during a total
    # outage is worse than no detector
    baseline_model_ids = set()
    for r in baseline_readings[-MIN_BASELINE:]:
        baseline_model_ids.update(r["models"].keys())
    for model_id in sorted(baseline_model_ids - current["models"].keys()):
        depth = sum(1 for r in baseline_readings if model_id in r["models"])
        if depth >= MIN_BASELINE:
            coverage.append({
                "model": model_id, "dimension": "-", "metric": "coverage",
                "level": "watch",
                "detail": "established model missing from current reading"})

    m = len(comparisons) or 1
    findings = []
    for c in comparisons:
        if c["p"] < ALPHA / m:
            c["level"] = "movement"
        elif c["p"] < ALPHA:
            c["level"] = "watch"
        else:
            continue
        c["bonferroni_m"] = m
        findings.append(c)

    # Latency: threshold on relative shift, not a test - serving latency is
    # too regime-prone for a clean parametric model at this sample size.
    for model_id, model in current["models"].items():
        cur = model["latency_ms"]["p50"]
        base = [r["models"][model_id]["latency_ms"]["p50"]
                for r in baseline_readings
                if model_id in r["models"]
                and r["models"][model_id]["latency_ms"]["p50"] is not None]
        if cur is None or len(base) < MIN_BASELINE:
            continue
        base_med = sorted(base)[len(base) // 2]
        if base_med == 0:
            continue
        shift = abs(cur - base_med) / base_med
        if shift >= LATENCY_WATCH:
            findings.append({
                "model": model_id, "dimension": "-", "metric": "latency_p50",
                "current": cur, "baseline": base_med,
                "shift": round(shift, 2),
                "level": ("movement" if shift >= LATENCY_MOVEMENT else "watch"),
            })
    # Thinking tokens: the serving-configuration tripwire. The battery pins
    # a minimum-thinking channel, so a provider silently remapping
    # reasoning-effort semantics (or changing serving in a way that alters
    # hidden computation) shifts this series before any pass rate moves.
    # Same threshold style as latency: regime-prone, so relative shift.
    for model_id, model in current["models"].items():
        for dim, v in model["dimensions"].items():
            th = (v.get("thinking_tokens") or {})
            cur = th.get("mean")
            if cur is None or th.get("n", 0) < 5:
                continue
            base = []
            for r in baseline_readings:
                bm = r["models"].get(model_id)
                if not bm or dim not in bm["dimensions"]:
                    continue
                bt = (bm["dimensions"][dim].get("thinking_tokens") or {})
                if bt.get("mean") is not None and bt.get("n", 0) >= 5:
                    base.append(bt["mean"])
            if len(base) < MIN_BASELINE:
                continue
            base_med = sorted(base)[len(base) // 2]
            if base_med < 1:
                # a series that was ~zero thinking suddenly thinking at all
                # is itself the anomaly
                if cur >= 32:
                    findings.append({
                        "model": model_id, "dimension": dim,
                        "metric": "thinking_tokens_mean",
                        "current": round(cur, 1), "baseline": round(base_med, 1),
                        "shift": None, "level": "watch",
                        "note": "thinking appeared on a previously zero-thinking channel"})
                continue
            shift = abs(cur - base_med) / base_med
            if shift >= THINKING_WATCH:
                findings.append({
                    "model": model_id, "dimension": dim,
                    "metric": "thinking_tokens_mean",
                    "current": round(cur, 1), "baseline": round(base_med, 1),
                    "shift": round(shift, 2),
                    "level": ("movement" if shift >= THINKING_MOVEMENT else "watch"),
                })
    return findings + coverage


def report(readings, cadence):
    if len(readings) < MIN_BASELINE + 1:
        return {"cadence": cadence, "verdict": "baseline-accruing",
                "readings": len(readings),
                "needed": MIN_BASELINE + 1, "findings": []}
    current = readings[-1]
    baseline = readings[-(BASELINE_WINDOW + 1):-1]
    findings = compare(current, baseline)
    return {"cadence": cadence,
            "verdict": "findings" if findings else "quiet",
            "reading_date": current["reading_date"],
            "baseline_readings": len(baseline),
            "findings": findings}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Advisory drift check vs rolling baseline.")
    ap.add_argument("--readings", default="readings")
    ap.add_argument("--cadence", choices=["daily", "weekly"], default="daily")
    ap.add_argument("--json", action="store_true", help="machine output")
    args = ap.parse_args(argv)

    readings = load_readings(args.readings, args.cadence)
    rep = report(readings, args.cadence)

    if args.json:
        print(json.dumps(rep, indent=2))
        return 0
    if rep["verdict"] == "baseline-accruing":
        print(f"baseline accruing: {rep['readings']}/{rep['needed']} "
              f"{args.cadence} readings - no claims until the ruler is long enough")
        return 0
    if rep["verdict"] == "quiet":
        print(f"{rep['reading_date']}: quiet "
              f"(baseline {rep['baseline_readings']} readings)")
        return 0
    for f in rep["findings"]:
        if f["metric"] == "coverage":
            print(f"[{f['level'].upper()}] {f['model']} {f['dimension']} "
                  f"coverage: {f['detail']}")
            continue
        extra = (f"p={f['p']:.2g} (m={f['bonferroni_m']})" if "p" in f
                 else f"shift={f['shift']}")
        print(f"[{f['level'].upper()}] {f['model']} {f['dimension']} "
              f"{f['metric']}: {f['baseline']} -> {f['current']}  {extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
