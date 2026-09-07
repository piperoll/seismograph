"""Divergence: the fixed-vs-dynamic gap (charter section 4).

detect.py answers "did a model change against ITSELF over time" - drift, one
tier at a time. This module answers a different question, across the two tiers
in the same run: "does a model score well on the fixed battery but worse on
fresh procedural probes of the SAME capability?"

A persistent fixed-over-dynamic gap is the gaming tripwire. If a model passes
the frozen Tier 1 probes it may have seen (training contamination) but fails
the Tier 2 probes it cannot have seen (generated this run), its Tier 1 score is
inflated by memorisation or evaluation-gaming, not underlying capability. The
gap is the evidence; naming a cause is a human editorial act, as everywhere in
this instrument.

Discipline, matching detect.py:
  - Probe-day units, never raw calls: repeat samples of one probe are
    correlated (charter 4). Pooled two-proportion z-test.
  - Benjamini-Hochberg FDR at ALPHA across all model x dimension comparisons.
  - PERSISTENT only: pooled across a trailing window of PAIRED readings (a day
    where both tiers ran), never a single day - a one-run gap is noise.
  - DIRECTIONAL: only fixed > dynamic counts. Dynamic > fixed is not a gaming
    signal (fresh probes are, if anything, easier to get right by luck on a
    tiny set); it is reported as context, never as divergence.
  - Under-alerting: "divergence" survives FDR AND is directional; "watch" is
    nominally significant but unconfirmed.
"""

import argparse
import glob
import json
import os
import sys

from .detect import ALPHA, BASELINE_WINDOW, MIN_BASELINE, two_proportion_p


def _load(readings_dir, cadence, dynamic):
    suffix = "-dynamic" if dynamic else ""
    pat = os.path.join(readings_dir, "*", f"reading-*-{cadence}{suffix}.json")
    out = {}
    for p in sorted(glob.glob(pat)):
        # the fixed glob also matches -dynamic files (they contain "-{cadence}");
        # exclude them explicitly so the two tiers never cross-contaminate
        if not dynamic and p.endswith(f"{cadence}-dynamic.json"):
            continue
        with open(p, encoding="utf-8") as f:
            r = json.load(f)
        out[r["reading_date"]] = r
    return out


def _units(reading, model_id, dim):
    """(pass_units, total_units) at probe-day granularity for one series in one
    reading, or None if the series is absent/ungradable."""
    m = reading["models"].get(model_id)
    d = m["dimensions"].get(dim) if m else None
    if not d or d["pass_rate"] is None or not d.get("probes"):
        return None
    return round(d["pass_rate"] * d["probes"]), d["probes"]


def compare_tiers(fixed_by_date, dynamic_by_date):
    """Pool the trailing window of paired dates and test fixed vs dynamic per
    model x dimension. Returns finding dicts (most-significant first)."""
    paired_dates = sorted(set(fixed_by_date) & set(dynamic_by_date))
    if len(paired_dates) < MIN_BASELINE:
        return {"verdict": "baseline-accruing", "paired": len(paired_dates),
                "needed": MIN_BASELINE, "findings": []}
    window = paired_dates[-BASELINE_WINDOW:]

    # gather every model x dimension that appears in BOTH tiers somewhere in
    # the window, then pool its probe-day units across the window
    pairs = {}
    for date in window:
        fx, dy = fixed_by_date[date], dynamic_by_date[date]
        common_models = set(fx["models"]) & set(dy["models"])
        for mid in common_models:
            fdims = fx["models"][mid]["dimensions"].keys()
            ddims = dy["models"][mid]["dimensions"].keys()
            for dim in set(fdims) & set(ddims):
                fu = _units(fx, mid, dim)
                du = _units(dy, mid, dim)
                if fu is None or du is None:
                    continue
                acc = pairs.setdefault((mid, dim),
                                       {"fp": 0, "fn": 0, "dp": 0, "dn": 0,
                                        "depth": 0})
                acc["fp"] += fu[0]; acc["fn"] += fu[1]
                acc["dp"] += du[0]; acc["dn"] += du[1]
                acc["depth"] += 1

    comparisons = []
    for (mid, dim), a in pairs.items():
        if a["depth"] < MIN_BASELINE or a["fn"] == 0 or a["dn"] == 0:
            continue
        fixed_rate = a["fp"] / a["fn"]
        dyn_rate = a["dp"] / a["dn"]
        p = two_proportion_p(a["fp"], a["fn"], a["dp"], a["dn"])
        comparisons.append({
            "model": mid, "dimension": dim, "metric": "tier_gap",
            "fixed": round(fixed_rate, 4), "dynamic": round(dyn_rate, 4),
            "gap": round(fixed_rate - dyn_rate, 4),
            "fixed_units": a["fn"], "dynamic_units": a["dn"],
            "paired_depth": a["depth"], "p": p,
        })

    # Benjamini-Hochberg over ALL comparisons (both directions are tested; the
    # correction must see every test done, per detect.py's reasoning)
    m = len(comparisons) or 1
    ordered = sorted(comparisons, key=lambda c: c["p"])
    bh_rank = 0
    for k, c in enumerate(ordered, start=1):
        if c["p"] <= (k / m) * ALPHA:
            bh_rank = k
    bh_p = ((bh_rank / m) * ALPHA) if bh_rank else 0.0

    findings = []
    for c in ordered:
        # directional: only fixed-over-dynamic is a gaming signal
        if c["gap"] <= 0:
            continue
        if c["p"] <= bh_p:
            c["level"] = "divergence"
        elif c["p"] < ALPHA:
            c["level"] = "watch"
        else:
            continue
        c["correction"] = "benjamini-hochberg"
        c["comparisons"] = m
        c["fdr_alpha"] = ALPHA
        findings.append(c)
    return {"verdict": "findings" if findings else "quiet",
            "latest_paired": window[-1], "paired_window": len(window),
            "findings": findings}


def report(readings_dir, cadence):
    fixed = _load(readings_dir, cadence, dynamic=False)
    dynamic = _load(readings_dir, cadence, dynamic=True)
    rep = compare_tiers(fixed, dynamic)
    rep["cadence"] = cadence
    return rep


def write_log(readings_dir="readings", out="divergence.json"):
    """Append-only divergence log - the Tier 2 counterpart of advisories.json.

    A divergence finding, once recorded, never disappears (corrections-not-
    slipped): a gap that later closes stays in the record with its date. Only
    'divergence'-level findings are logged; watches live in the current block.
    """
    prior = {"log": []}
    if os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            prior = json.load(f)
    log = prior.get("log", [])
    current: dict = {"cadence": {}}
    for cadence in ("daily", "weekly"):
        rep = report(readings_dir, cadence)
        current["cadence"][cadence] = {
            "verdict": rep["verdict"],
            "latest_paired": rep.get("latest_paired"),
            "findings": rep.get("findings", []),
        }
        for f in rep.get("findings", []):
            if f.get("level") != "divergence":
                continue
            key = (rep.get("latest_paired"), cadence, f["model"], f["dimension"])
            if any(tuple(e["key"]) == key for e in log):
                continue
            log.append({"key": list(key), "date": rep.get("latest_paired"),
                        "cadence": cadence, "finding": f})
    current["log"] = log
    with open(out, "w", encoding="utf-8") as f:
        json.dump(current, f, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    return current


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fixed-vs-dynamic divergence check (Tier 1 vs Tier 2).")
    ap.add_argument("--readings", default="readings")
    ap.add_argument("--cadence", choices=["daily", "weekly"], default="daily")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write-log", action="store_true",
                    help="update divergence.json (both cadences, append-only)")
    args = ap.parse_args(argv)

    if args.write_log:
        cur = write_log(args.readings)
        div = sum(1 for c in cur["cadence"].values()
                  for f in c["findings"] if f.get("level") == "divergence")
        print(f"divergence.json updated: {div} divergence(s) current, "
              f"{len(cur['log'])} in the log")
        return 0

    rep = report(args.readings, args.cadence)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0
    if rep["verdict"] == "baseline-accruing":
        print(f"divergence baseline accruing: {rep['paired']}/{rep['needed']} "
              f"paired {args.cadence} readings - no claim until both tiers have "
              "run together enough")
        return 0
    if rep["verdict"] == "quiet":
        print(f"{rep['latest_paired']}: no divergence "
              f"(paired window {rep['paired_window']})")
        return 0
    for f in rep["findings"]:
        print(f"[{f['level'].upper()}] {f['model']} {f['dimension']} "
              f"fixed {f['fixed']} vs dynamic {f['dynamic']} "
              f"(gap {f['gap']}, p={f['p']:.2g}, BH m={f['comparisons']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
