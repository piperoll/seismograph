"""Derive series.json - the compact time-series artifact the board reads.

Raw readings stay canonical (one witnessed file per day); this is the
browser-facing digest of them: per model, per dimension, the daily rates as
parallel arrays keyed by date. One fetch, then every window/filter is
client-side arithmetic. Regenerated after each run; never hand-edited.

Usage: python3 -m seismo.series [--readings readings] [--out series.json]
"""

import argparse
import glob
import json
import os


def _build_cadence(readings_dir, cadence):
    """One cadence's series. Daily (canary battery) and weekly (deep battery)
    are DIFFERENT batteries and share reading dates, so they are built
    separately and never merged - a daily point and a weekly point on the same
    date are distinct series, not a collision."""
    files = sorted(glob.glob(os.path.join(
        readings_dir, "*", f"reading-*-{cadence}.json")))
    models = {}
    meta_last = None
    for f in files:
        r = json.load(open(f, encoding="utf-8"))
        meta_last = r
        date = r["reading_date"]
        for mid, m in r["models"].items():
            s = models.setdefault(mid, {
                "provider": m.get("provider"), "tier": m.get("tier"),
                "dates": [], "overall": [], "dims": {},
                "latency_p50": [], "latency_p95": [], "call_errors": [],
                "errors_by_class": [], "roster_version": [],
                "thinking_mean": [], "cost_usd_est": [],
            })
            # same cadence + same date = a re-run; later file wins
            if date in s["dates"]:
                idx = s["dates"].index(date)
                for k in ("overall", "latency_p50", "latency_p95",
                          "call_errors", "errors_by_class", "roster_version",
                          "thinking_mean", "cost_usd_est"):
                    s[k].pop(idx)
                for d in s["dims"].values():
                    d.pop(idx)
                s["dates"].pop(idx)
            tot_n = tot_p = 0
            for dim, v in sorted(m["dimensions"].items()):
                arr = s["dims"].setdefault(dim, [None] * len(s["dates"]))
                if v.get("pass_rate") is not None and v["n"] > 0:
                    arr.append(v["pass_rate"])
                    tot_n += v["n"]; tot_p += v["pass_rate"] * v["n"]
                else:
                    arr.append(None)
            s["dates"].append(date)
            s["overall"].append(round(tot_p / tot_n, 4) if tot_n else None)
            s["latency_p50"].append(m["latency_ms"]["p50"])
            s["latency_p95"].append(m["latency_ms"]["p95"])
            s["call_errors"].append(m["call_errors"])
            s["errors_by_class"].append(m.get("errors_by_class") or {})
            tn = tp = 0
            for v in m["dimensions"].values():
                t = v.get("thinking_tokens") or {}
                if t.get("mean") is not None and t.get("n"):
                    tn += t["n"]; tp += t["mean"] * t["n"]
            s["cost_usd_est"].append(m.get("cost_usd_est"))
            s["thinking_mean"].append(round(tp / tn, 1) if tn else None)
            s["roster_version"].append(r.get("roster_version"))
            for dim, arr in s["dims"].items():
                while len(arr) < len(s["dates"]):
                    arr.append(None)
    block: dict = {"models": models}
    if meta_last:
        block["battery"] = meta_last["battery"]
        block["grader_version"] = meta_last["grader_version"]
        block["latest_reading"] = max(
            (d for s in models.values() for d in s["dates"]), default=None)
    return block


def build_series(readings_dir="readings"):
    out: dict = {"instrument": "piperoll-seismograph"}
    for cadence in ("daily", "weekly"):
        out[cadence] = _build_cadence(readings_dir, cadence)
    # back-compat convenience: `models` mirrors the daily series (the primary
    # board view); the deep weekly series lives under out["weekly"].
    out["models"] = out["daily"]["models"]
    out["battery"] = out["daily"].get("battery")
    out["latest_reading"] = out["daily"].get("latest_reading")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Derive series.json from readings/")
    ap.add_argument("--readings", default="readings")
    ap.add_argument("--out", default="series.json")
    args = ap.parse_args(argv)
    series = build_series(args.readings)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(series, f, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    n = len(series.get("models", {}))
    print(f"series.json: {n} models, "
          f"{os.path.getsize(args.out)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
