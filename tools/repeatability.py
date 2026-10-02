"""Summarise a repeatability run: the same Tier 2 seed, re-run back to back.

Reads readings-repeat/run-*/<year>/reading-*-dynamic.json and prints, per
model and dimension, the pass rate in each repeat and the spread across
repeats. Because the probes and the hour are identical, the spread is pure
sampling noise - the number the detector's thresholds should be judged
against. Nothing here is a fleet measurement; it is calibration.
"""

import glob
import json
import os
import statistics
import sys


def load(root):
    runs = []
    for d in sorted(glob.glob(os.path.join(root, "run-*"))):
        files = glob.glob(os.path.join(d, "*", "reading-*-dynamic.json"))
        if files:
            runs.append(json.load(open(sorted(files)[-1], encoding="utf-8")))
    return runs


def main(root="readings-repeat"):
    runs = load(root)
    if len(runs) < 2:
        print("need at least two repeats"); return 1
    seed = runs[0].get("battery", {}).get("seed") or runs[0].get("dynamic_seed")
    print(f"# Repeatability: {len(runs)} repeats of one Tier 2 seed\n")
    print("| model | dimension | " + " | ".join(f"r{i+1}" for i in range(len(runs)))
          + " | max-min | sd |")
    print("|---|---|" + "---|" * len(runs) + "---|---|")
    spreads = []
    for mid in sorted(runs[0]["models"]):
        dims = runs[0]["models"][mid]["dimensions"]
        for dim in sorted(dims):
            rates = []
            for r in runs:
                v = ((r["models"].get(mid) or {}).get("dimensions") or {}).get(dim) or {}
                rates.append(v.get("pass_rate"))
            ok = [x for x in rates if x is not None]
            if len(ok) < 2:
                continue
            spread = max(ok) - min(ok)
            sd = statistics.pstdev(ok)
            spreads.append(spread)
            print(f"| {mid} | {dim} | " + " | ".join("-" if x is None else f"{x:.3f}" for x in rates)
                  + f" | {spread:.3f} | {sd:.3f} |")
    if spreads:
        spreads.sort()
        print(f"\nseries: {len(spreads)}; max-min spread median {statistics.median(spreads):.3f}, "
              f"p90 {spreads[int(len(spreads) * 0.9) - 1 if len(spreads) >= 10 else -1]:.3f}, "
              f"max {spreads[-1]:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
