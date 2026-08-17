"""Collection orchestrator: battery x roster -> raw session.

Collection is deliberately dumb: call, record, nothing else. Grading and
aggregation live in digest.py so history can be regraded when graders
improve. Sessions land in raw/ which is PRIVATE (outputs can echo probes).

Usage:
    python3 -m seismo.run --cadence daily [--mock] [--model gpt-5 ...]
"""

import argparse
import concurrent.futures
import datetime
import json
import os
import sys

from . import RUNNER_VERSION
from .battery import load_battery
from .providers import MockProvider, ProviderError, call_model


REQUIRED_MODEL_KEYS = ("id", "provider", "model", "identity", "tier",
                       "cadence", "env_key")


def validate_roster(roster):
    """A malformed roster entry must fail loudly - a missing env_key or
    cadence would otherwise drop the model from every run silently."""
    errors = []
    seen = set()
    for i, m in enumerate(roster.get("models", [])):
        where = f"model[{i}] ({m.get('id', '?')})"
        for key in REQUIRED_MODEL_KEYS:
            if key not in m:
                errors.append(f"{where}: missing {key}")
        if m.get("id") in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(m.get("id"))
        if m.get("cadence") not in ("daily", "weekly"):
            errors.append(f"{where}: cadence must be daily or weekly")
        if m.get("provider") == "openai_compat" and "base_url" not in m:
            errors.append(f"{where}: openai_compat requires base_url")
    return errors


def select_models(roster, cadence, only=None):
    """A weekly run covers everything; a daily run covers daily-cadence
    models only. An explicitly named --model overrides the cadence filter -
    the operator naming a model means run it."""
    selected = []
    for m in roster["models"]:
        if only:
            if m["id"] in only:
                selected.append(m)
            continue
        if cadence == "daily" and m.get("cadence") != "daily":
            continue
        selected.append(m)
    return selected


def missing_key_models(models):
    return [m["id"] for m in models
            if not os.environ.get(m.get("env_key", ""), "").strip()]


def _redact(message, models):
    """Strip any configured API key value out of an error message before it
    is stored - exception text (e.g. invalid-header ValueError) can embed
    the full key."""
    for m in models:
        key = os.environ.get(m.get("env_key", ""), "").strip()
        if key:
            message = message.replace(key, "[redacted]")
    return message


def run_session(battery, models, out_dir, cadence, mock=None, workers=4,
                skipped=None):
    started = datetime.datetime.now(datetime.timezone.utc)
    stamp = started.strftime("%Y-%m-%dT%H%M%SZ")
    os.makedirs(out_dir, exist_ok=True)
    session_path = os.path.join(out_dir, f"session-{stamp}-{cadence}.jsonl")
    meta_path = os.path.join(out_dir, f"session-{stamp}-{cadence}.meta.json")

    tasks = []
    for model in models:
        for probe in battery["probes"]:
            for sample in range(probe["samples"]):
                tasks.append((model, probe, sample))

    def one(task):
        model, probe, sample = task
        try:
            resp = call_model(model, probe["prompt"], probe.get("system"),
                              probe.get("params", {}), mock=mock,
                              probe_id=probe["id"])
        # catch everything: one bad response must cost one record, never the
        # session - a day not measured is a baseline gone forever
        except Exception as e:
            resp = {"text": None, "input_tokens": None, "output_tokens": None,
                    "thinking_tokens": None, "latency_ms": 0.0, "status": 0,
                    "finish": None,
                    "error": _redact(f"{type(e).__name__}: {e}", models)}
        return {
            "model_id": model["id"],
            "probe_id": probe["id"],
            "dimension": probe["dimension"],
            "sample": sample,
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "text": resp["text"],
            "input_tokens": resp["input_tokens"],
            "output_tokens": resp["output_tokens"],
            "thinking_tokens": resp.get("thinking_tokens"),
            "latency_ms": resp["latency_ms"],
            "status": resp["status"],
            "finish": resp.get("finish"),
            "error": resp["error"],
        }

    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for record in pool.map(one, tasks):
            records.append(record)

    with open(session_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    finished = datetime.datetime.now(datetime.timezone.utc)
    errors = sum(1 for r in records if r["error"])
    meta = {
        "runner_version": RUNNER_VERSION,
        "cadence": cadence,
        "battery": {"name": battery["battery"], "version": battery["version"],
                    "sha256": battery["_sha256"]},
        "models": [{"id": m["id"], "provider": m["provider"],
                    "model": m["model"], "identity": m["identity"],
                    "tier": m["tier"]} for m in models],
        "started": started.isoformat(),
        "finished": finished.isoformat(),
        "calls": len(records),
        "call_errors": errors,
        # models that should have run but could not - digest/detect read this
        # so a silently keyless model is a visible data gap, not a quiet hole
        "skipped_no_key": skipped or [],
        "mock": mock is not None,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return session_path, meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run the probe battery.")
    ap.add_argument("--battery", default="battery/canary-v0.json")
    ap.add_argument("--models", default="config/models.json")
    ap.add_argument("--cadence", choices=["daily", "weekly"], default="daily")
    ap.add_argument("--model", action="append",
                    help="limit to these model ids (repeatable)")
    ap.add_argument("--out", default="raw")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--mock", action="store_true",
                    help="offline dry run with the mock provider")
    ap.add_argument("--strict", action="store_true",
                    help="fail instead of skipping models with missing keys")
    args = ap.parse_args(argv)

    battery = load_battery(args.battery)
    with open(args.models, encoding="utf-8") as f:
        roster = json.load(f)
    roster_errors = validate_roster(roster)
    if roster_errors:
        print("invalid roster:\n" + "\n".join(roster_errors), file=sys.stderr)
        return 2

    models = select_models(roster, args.cadence, only=args.model)
    if not models:
        print("no models selected", file=sys.stderr)
        return 2

    skipped = []
    if not args.mock:
        skipped = missing_key_models(models)
        if skipped and args.strict:
            print(f"missing API keys for: {', '.join(skipped)}", file=sys.stderr)
            return 2
        models = [m for m in models if m["id"] not in skipped]
        if not models:
            print("no models with API keys available", file=sys.stderr)
            return 2

    mock = MockProvider() if args.mock else None
    session_path, meta = run_session(battery, models, args.out, args.cadence,
                                     mock=mock, workers=args.workers,
                                     skipped=skipped)
    if skipped:
        print(f"skipped (no key): {', '.join(skipped)}", file=sys.stderr)
    print(f"{session_path}  calls={meta['calls']} errors={meta['call_errors']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
