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


def compare(current, baseline_readings):
    """Compare one reading against a pooled baseline. Returns finding dicts."""
    comparisons = []
    for model_id, model in current["models"].items():
        for dim, stats in model["dimensions"].items():
            if stats["pass_rate"] is None:
                continue
            base_pass, base_n, base_lat = 0, 0, []
            for r in baseline_readings:
                bm = r["models"].get(model_id)
                if not bm:
                    continue
                bd = bm["dimensions"].get(dim)
                if bd and bd["pass_rate"] is not None:
                    base_pass += round(bd["pass_rate"] * bd["n"])
                    base_n += bd["n"]
                if bm["latency_ms"]["p50"] is not None:
                    base_lat.append(bm["latency_ms"]["p50"])
            if base_n == 0:
                continue
            cur_pass = round(stats["pass_rate"] * stats["n"])
            p = two_proportion_p(cur_pass, stats["n"], base_pass, base_n)
            comparisons.append({
                "model": model_id, "dimension": dim, "metric": "pass_rate",
                "current": stats["pass_rate"],
                "baseline": round(base_pass / base_n, 4),
                "n": stats["n"], "baseline_n": base_n, "p": p,
            })

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
        if cur is None or len(base) < MIN_BASELINE // 2:
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
    return findings


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
        extra = (f"p={f['p']:.2g} (m={f['bonferroni_m']})" if "p" in f
                 else f"shift={f['shift']}")
        print(f"[{f['level'].upper()}] {f['model']} {f['dimension']} "
              f"{f['metric']}: {f['baseline']} -> {f['current']}  {extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
