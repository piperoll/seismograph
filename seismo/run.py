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
import subprocess
import sys
import time

from . import RUNNER_VERSION
from .battery import load_battery
from .providers import MockProvider, ProviderError, call_model


def code_commit():
    """Commit hash of the running code, pinned into every session meta.

    The witnessed manifest must bind readings to the exact grader/runner
    code even while the repo is private: the public Rekor entry then proves
    "this code existed at this date" when the repo opens later. Falls back
    to SEISMO_CODE_COMMIT (set by CI on detached/shallow checkouts), else
    None - a visible gap in the meta rather than a fabricated value."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True,
            stderr=subprocess.DEVNULL).strip() or None
    except Exception:
        return os.environ.get("SEISMO_CODE_COMMIT")


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


_ACCESS_PENDING_SIGNS = (
    "does not exist", "not found", "model_not_found", "no access",
    "does not have access", "do not have access", "not available",
    "unsupported model", "invalid model", "model not found")


def looks_access_pending(resp):
    """True when a call to a model flagged availability=pending fails with a
    not-found / no-access signal - the model exists in the roster but the
    account cannot reach it yet (staged ahead of API rollout). Distinct from a
    transient failure: only clear not-available signals count, so a 500 or a
    rate limit never masquerades as 'pending'."""
    if resp.get("status") == 404:
        return True
    err = (resp.get("error") or "").lower()
    return bool(err) and any(s in err for s in _ACCESS_PENDING_SIGNS)


def run_session(battery, models, out_dir, cadence, mock=None, workers=4,
                skipped=None, roster_version=None):
    started = datetime.datetime.now(datetime.timezone.utc)
    stamp = started.strftime("%Y-%m-%dT%H%M%SZ")
    os.makedirs(out_dir, exist_ok=True)
    session_path = os.path.join(out_dir, f"session-{stamp}-{cadence}.jsonl")
    meta_path = os.path.join(out_dir, f"session-{stamp}-{cadence}.meta.json")

    # Availability preflight: a model flagged availability=pending is staged
    # ahead of its API rollout. Probe it once; if the account cannot reach it
    # yet (not-found / no-access), set it aside as access-pending for this run -
    # exactly like a keyless model - so it neither floods the reading with
    # errors nor raises a coverage finding. The instant the probe succeeds it
    # joins the run normally: no config flip needed to start measuring.
    access_pending = []
    if not mock and battery["probes"]:
        probe0 = battery["probes"][0]
        reachable = []
        for model in models:
            if model.get("availability") != "pending":
                reachable.append(model)
                continue
            try:
                r = call_model(model, probe0["prompt"], probe0.get("system"),
                               probe0.get("params", {}), mock=mock,
                               probe_id=probe0["id"])
            except Exception as e:  # a thrown error is not a clean not-found; run it
                r = {"status": 0, "error": _redact(f"{type(e).__name__}: {e}", models)}
            if looks_access_pending(r):
                access_pending.append(model["id"])
                print(f"  access-pending: {model['id']} not reachable yet "
                      f"(staged); skipping this run", file=sys.stderr, flush=True)
            else:
                reachable.append(model)
        models = reachable

    # probe-major order: adjacent tasks hit DIFFERENT providers, so each
    # provider sees the battery spread across the whole run instead of 4
    # workers hammering its 90 calls contiguously (model-major order cost
    # mistral-large 45/90 to rate limits on day one).
    tasks = []
    for probe in battery["probes"]:
        for sample in range(probe["samples"]):
            for model in models:
                tasks.append((model, probe, sample))

    SLOW_CALL_S = 30  # a single call over this is worth surfacing live

    def _log(msg):
        # stderr, flushed: the Actions live log streams it as it happens, so a
        # long run is not a black box and a dragging model is visible in
        # real time.
        print(msg, file=sys.stderr, flush=True)

    def one(task):
        model, probe, sample = task
        t0 = time.monotonic()
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
        dt = time.monotonic() - t0
        if dt >= SLOW_CALL_S:
            _log(f"  slow: {model['id']} {probe['id']} took {dt:.0f}s")
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
    total = len(tasks)
    started_at = time.monotonic()
    expected = {}
    for t in tasks:
        expected[t[0]["id"]] = expected.get(t[0]["id"], 0) + 1
    per_model = {}
    _log(f"running {total} calls across {len(models)} models, "
         f"{workers} workers")
    step = max(50, total // 20)  # heartbeat every ~5% (min 50 calls)
    # as_completed, not map: results stream as they finish, so one slow call
    # never blocks the heartbeat and progress is real. Record order does not
    # matter - the digest groups by model and probe.
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, t) for t in tasks]
        for fut in concurrent.futures.as_completed(futures):
            record = fut.result()
            records.append(record)
            per_model[record["model_id"]] = per_model.get(
                record["model_id"], 0) + 1
            done = len(records)
            if done % step == 0 or done == total:
                elapsed = time.monotonic() - started_at
                rate = done / elapsed if elapsed else 0
                eta = (total - done) / rate if rate else 0
                errs = sum(1 for r in records if r["error"])
                # models still owing the most calls are the laggards
                lag = sorted(((mid, expected[mid] - per_model.get(mid, 0))
                              for mid in expected), key=lambda x: -x[1])[:3]
                lag = ", ".join(f"{mid}:{n}" for mid, n in lag if n > 0)
                _log(f"  {done}/{total} ({100 * done // total}%) "
                     f"errors={errs} elapsed={elapsed:.0f}s "
                     f"eta={eta:.0f}s  behind: {lag or 'none'}")

    with open(session_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    finished = datetime.datetime.now(datetime.timezone.utc)
    errors = sum(1 for r in records if r["error"])
    meta = {
        "runner_version": RUNNER_VERSION,
        "code_commit": code_commit(),
        # the roster is where effort/temperature policy lives; a reading is
        # only attributable to the provider if its settings are pinned here
        "roster_version": roster_version,
        "cadence": cadence,
        "battery": {"name": battery["battery"], "version": battery["version"],
                    "sha256": battery["_sha256"]},
        "models": [{"id": m["id"], "provider": m["provider"],
                    "model": m["model"], "identity": m["identity"],
                    "tier": m["tier"],
                    "request_overrides": m.get("request_overrides"),
                    "thinking_budget": m.get("thinking_budget")}
                   for m in models],
        "started": started.isoformat(),
        "finished": finished.isoformat(),
        "calls": len(records),
        "call_errors": errors,
        # models that should have run but could not - digest/detect read this
        # so a silently keyless model is a visible data gap, not a quiet hole
        "skipped_no_key": skipped or [],
        # staged models the account cannot reach yet (availability=pending):
        # noted, not errored, not a coverage gap - auto-joins when access lands
        "skipped_access_pending": access_pending,
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
                                     roster_version=roster.get("roster_version"),
                                     skipped=skipped)
    if skipped:
        print(f"skipped (no key): {', '.join(skipped)}", file=sys.stderr)
    print(f"{session_path}  calls={meta['calls']} errors={meta['call_errors']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
