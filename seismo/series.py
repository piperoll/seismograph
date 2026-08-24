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


def build_series(readings_dir="readings"):
    files = sorted(glob.glob(os.path.join(readings_dir, "*", "reading-*.json")))
    out = {"instrument": "piperoll-seismograph", "models": {}}
    meta_last = None
    for f in files:
        r = json.load(open(f, encoding="utf-8"))
        meta_last = r
        cadence = r["cadence"]
        date = r["reading_date"]
        for mid, m in r["models"].items():
            s = out["models"].setdefault(mid, {
                "provider": m.get("provider"), "tier": m.get("tier"),
                "cadence": cadence, "dates": [], "overall": [],
                "dims": {}, "latency_p50": [], "latency_p95": [],
                "call_errors": [], "roster_version": [],
            })
            # a model can appear in both cadences (weekly runs the full
            # roster); keep its own cadence's series plus any extra points,
            # deduped by date with the later file winning
            if date in s["dates"]:
                idx = s["dates"].index(date)
                for k in ("overall", "latency_p50", "latency_p95",
                          "call_errors", "roster_version"):
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
            s["roster_version"].append(r.get("roster_version"))
            for dim, arr in s["dims"].items():
                while len(arr) < len(s["dates"]):
                    arr.append(None)
    if meta_last:
        out["battery"] = meta_last["battery"]
        out["grader_version"] = meta_last["grader_version"]
        out["latest_reading"] = max(
            d for s in out["models"].values() for d in s["dates"])
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
