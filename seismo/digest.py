"""Raw session -> public reading.

The reading is the publishable artifact: per-model, per-dimension aggregates
only. No raw model text ever enters a reading (outputs can echo probes), and
no per-probe detail (a per-probe series would let outsiders reconstruct the
battery by elimination). Probe counts per dimension are public - methodology
transparency without content disclosure.

Usage:
    python3 -m seismo.digest raw/session-...jsonl [--battery battery/canary-v0.json]
"""

import argparse
import json
import math
import os
import sys

from . import GRADER_VERSION
from .battery import load_battery
from .grade import grade, looks_like_refusal


def percentile(values, pct):
    """Nearest-rank percentile; deterministic, no interpolation surprises."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def _mean_std(values):
    if not values:
        return None, None
    mean = sum(values) / len(values)
    if len(values) < 2:
        return round(mean, 1), 0.0
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return round(mean, 1), round(math.sqrt(var), 1)


def build_reading(session_path, battery, cadence=None):
    meta_path = session_path.replace(".jsonl", ".meta.json")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    if meta["battery"]["sha256"] != battery["_sha256"]:
        raise ValueError(
            "battery file does not match the one this session ran "
            f"(session {meta['battery']['sha256'][:12]}, "
            f"loaded {battery['_sha256'][:12]})")

    graders = {p["id"]: p["grader"] for p in battery["probes"]}
    records = []
    with open(session_path, encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))

    def classify_error(e):
        """Public-safe error category: raw provider strings stay in the
        private archive (they can echo request details); readings carry
        only these classes."""
        t = (e or "").lower()
        if "quota" in t or "billing" in t or "balance" in t:
            return "quota-or-billing"
        if "rate limit" in t or "rate_limited" in t or '"code": 429' in t or "429" in t:
            return "rate-limit"
        if "truncated with no visible output" in t:
            return "truncation"
        if "timed out" in t or "timeout" in t:
            return "timeout"
        if "invalid" in t or "not allowed" in t or "does not exist" in t or "unsupported" in t:
            return "request-rejected"
        if "socket" in t or "connection" in t or "dns" in t:
            return "network"
        return "other"

    models = {}
    graded_detail = []
    for m in meta["models"]:
        model_records = [r for r in records if r["model_id"] == m["id"]]
        dims = {}
        for r in model_records:
            dims.setdefault(r["dimension"], []).append(r)

        dim_out = {}
        for dim, recs in sorted(dims.items()):
            ok_recs = [r for r in recs if not r["error"]]
            passes = 0
            refusals = 0
            blocked = 0
            for r in ok_recs:
                spec = graders[r["probe_id"]]
                # provider-side refusal signals (structured refusal channel,
                # safety block) outrank the text lexicon: a block with empty
                # text IS a refusal, not a non-answer
                provider_refused = r.get("finish") in ("blocked", "refusal")
                refused = provider_refused or looks_like_refusal(r["text"] or "")
                blocked += r.get("finish") == "blocked"
                if spec["type"] == "refusal":
                    passed = refused == spec["expect"]
                    detail = f"refused={refused}"
                else:
                    passed, detail = grade(r["text"], spec)
                passes += passed
                refusals += refused
                graded_detail.append({"model_id": m["id"],
                                      "probe_id": r["probe_id"],
                                      "sample": r["sample"],
                                      "passed": passed, "detail": detail})
            tokens = [r["output_tokens"] for r in ok_recs
                      if r["output_tokens"] is not None]
            tok_mean, tok_std = _mean_std(tokens)
            dim_out[dim] = {
                "probes": len({r["probe_id"] for r in recs}),
                "n": len(ok_recs),
                "n_error": len(recs) - len(ok_recs),
                "n_blocked": blocked,
                "pass_rate": (round(passes / len(ok_recs), 4)
                              if ok_recs else None),
                "refusal_rate": (round(refusals / len(ok_recs), 4)
                                 if ok_recs else None),
                "output_tokens": {"mean": tok_mean, "std": tok_std},
            }

        err_classes = {}
        for r in model_records:
            if r["error"]:
                c = classify_error(r["error"])
                err_classes[c] = err_classes.get(c, 0) + 1

        latencies = [r["latency_ms"] for r in model_records if not r["error"]]
        models[m["id"]] = {
            "provider": m["provider"],
            "model": m["model"],
            "identity": m["identity"],
            "tier": m["tier"],
            "dimensions": dim_out,
            "latency_ms": {"p50": percentile(latencies, 50),
                           "p95": percentile(latencies, 95)},
            "calls": len(model_records),
            "call_errors": sum(1 for r in model_records if r["error"]),
            "errors_by_class": err_classes,
        }

    reading = {
        "instrument": "piperoll-seismograph",
        "reading_date": meta["started"][:10],
        "cadence": cadence or meta["cadence"],
        "battery": meta["battery"],
        "runner_version": meta["runner_version"],
        "code_commit": meta.get("code_commit"),
        "roster_version": meta.get("roster_version"),
        "grader_version": GRADER_VERSION,
        "mock": meta.get("mock", False),
        "skipped_no_key": meta.get("skipped_no_key", []),
        "models": models,
    }
    return reading, graded_detail


def write_reading(reading, out_dir="readings"):
    year = reading["reading_date"][:4]
    os.makedirs(os.path.join(out_dir, year), exist_ok=True)
    name = f"reading-{reading['reading_date']}-{reading['cadence']}.json"
    path = os.path.join(out_dir, year, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reading, f, indent=2, sort_keys=True)
        f.write("\n")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Digest a raw session into a public reading.")
    ap.add_argument("session", help="raw session .jsonl path")
    ap.add_argument("--battery", default="battery/canary-v0.json")
    ap.add_argument("--out", default="readings")
    ap.add_argument("--graded-out", default=None,
                    help="optional private per-probe grading detail (jsonl)")
    args = ap.parse_args(argv)

    battery = load_battery(args.battery)
    reading, detail = build_reading(args.session, battery)
    path = write_reading(reading, args.out)
    if args.graded_out:
        with open(args.graded_out, "w", encoding="utf-8") as f:
            for d in detail:
                f.write(json.dumps(d) + "\n")
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
