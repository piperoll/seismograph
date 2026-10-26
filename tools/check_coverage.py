"""Post-run coverage check: did every model the roster expects for this
cadence land in today's reading, and did it actually answer?

Expected = roster models for the cadence (daily: cadence=daily; weekly: all
text models; decision: cadence=decision), minus any the run itself set aside
as keyless or access-pending (those are recorded, not silent). For each
expected model the reading must contain it with at least one graded call.

Exit 1 with a one-line report when anything is missing, fully dark,
billing-blocked, or truncating empty at or above the floor, so the canary step goes red and (when SEISMO_NTFY_TOPIC is set) a push goes out the
same hour - not the next evening's heartbeat.

    python3 tools/check_coverage.py readings/2026/reading-2026-10-05-daily.json
"""

import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# empty-truncation alert: at least this many calls AND this share of the
# model's calls on one reading (a single long-tail probe never pages)
TRUNCATION_FLOOR = 5
TRUNCATION_SHARE = 0.05

# providers whose request quota is a per-day allowance (Google resets at
# midnight Pacific). On Sundays the weekly deep battery runs the same Pacific
# day as the daily canary, so a model whose daily allowance is smaller than
# the two batteries combined runs out partway through the weekly - every
# weekly in Oct 2026 for gemini-3.1-pro-preview (daily 87 calls clean, weekly
# 47-64 of 174 refused). That is a quota-size fact, not a billing outage, and
# "top up" is the wrong instruction for it.
DAILY_QUOTA_PROVIDERS = {"google"}


def expected_models(roster, cadence):
    out = []
    for m in roster["models"]:
        c = m.get("cadence")
        if cadence == "decision":
            if c == "decision":
                out.append(m["id"])
        elif c != "decision" and (cadence == "weekly" or c == "daily"):
            out.append(m["id"])
    return sorted(out)


def shared_daily_quota(mid, roster_by_id, same_day):
    """True when a weekly quota refusal is explained by the same Pacific day's
    daily run having already spent the model's allowance: a daily-quota
    provider, and today's daily reading shows the model answering with no
    quota/billing refusals at all. A real billing outage after the daily would
    look the same for one weekly; the next daily (fully dark or partial) pages
    on it, so the cost of this exception is at most one day's delay."""
    cfg = roster_by_id.get(mid) or {}
    if cfg.get("provider") not in DAILY_QUOTA_PROVIDERS or not same_day:
        return False
    d = (same_day.get("models") or {}).get(mid)
    if not d or not d.get("calls"):
        return False
    return (d.get("errors_by_class") or {}).get("quota-or-billing", 0) == 0 and d["calls"] > d.get("call_errors", 0)


def check(reading, roster, same_day=None):
    """same_day: the daily reading for the same date, consulted only for a
    weekly reading (see shared_daily_quota)."""
    cadence = reading["cadence"]
    roster_by_id = {m["id"]: m for m in roster["models"]}
    expected = expected_models(roster, cadence)
    skipped = set(reading.get("skipped_no_key") or []) | set(reading.get("skipped_access_pending") or [])
    got = reading.get("models", {})
    pending = {m["id"] for m in roster["models"] if m.get("availability") == "pending"}
    missing, dark, billing, ok, truncating, confirmed, shared_quota = [], [], [], [], [], [], []
    for mid in expected:
        if mid in skipped:
            continue
        m = got.get(mid)
        if not m:
            missing.append(mid)
        elif m.get("calls", 0) and m.get("call_errors", 0) >= m["calls"]:
            cls = max((m.get("errors_by_class") or {"unknown": 1}).items(), key=lambda kv: kv[1])[0]
            dark.append(f"{mid} ({cls})")
        else:
            ok.append(mid)
            # a quota/billing refusal on ANY call is a condition that will not
            # clear by itself: the next run is fully dark. Oct 10 2026: the
            # shared DeepInfra balance ran out at the first second of the run,
            # 42/87 calls failed on each of 12 models, and nothing paged
            # because none was fully dark.
            n_bill = (m.get("errors_by_class") or {}).get("quota-or-billing", 0)
            if n_bill and cadence == "weekly" and shared_daily_quota(mid, roster_by_id, same_day):
                shared_quota.append(f"{mid} ({n_bill}/{m['calls']})")
            elif n_bill:
                billing.append(f"{mid} ({n_bill}/{m['calls']})")
            # empty truncations are a SETTINGS defect, not model behaviour: the
            # reasoning or the answer did not fit the budget we set. Oct 2026:
            # gemini-3.8-flash sat at 9-14 empty truncations per reading for ten
            # days (an ignored thinking parameter) and nothing paged, while the
            # truncated answers quietly depressed its pass rates. Page from the
            # first reading that crosses the floor so headroom/thinking gets
            # fixed before a baseline accrues on the artefact.
            n_trunc = (m.get("errors_by_class") or {}).get("truncation", 0)
            if n_trunc >= TRUNCATION_FLOOR and n_trunc >= TRUNCATION_SHARE * m["calls"]:
                truncating.append(f"{mid} ({n_trunc}/{m['calls']})")
            # a pre-staged model answering is the signal to drop its
            # availability=pending flag (cosmetic, but it is how the roster
            # log records first contact)
            if mid in pending and m.get("calls", 0) > m.get("call_errors", 0):
                confirmed.append(f"{mid} ({m['calls'] - m.get('call_errors', 0)}/{m['calls']})")
    return {"cadence": cadence, "expected": len(expected), "skipped": sorted(skipped),
            "answered": len(ok), "missing": missing, "dark": dark, "billing": billing,
            "truncating": truncating, "access_confirmed": confirmed,
            "shared_quota": shared_quota}


def failed_ids(r):
    """Roster ids worth a targeted rerun: missing, fully errored, or billing-blocked."""
    strip = lambda s: s.split(" (")[0]
    return sorted(set(r["missing"]) | {strip(x) for x in r["dark"]} | {strip(x) for x in r["billing"]})


def main(path, list_failed=False):
    reading = json.load(open(path, encoding="utf-8"))
    roster = json.load(open(os.path.join(ROOT, "config", "models.json"), encoding="utf-8"))
    same_day = None
    if reading.get("cadence") == "weekly":
        daily_path = os.path.join(os.path.dirname(path), f"reading-{reading['reading_date']}-daily.json")
        if os.path.exists(daily_path):
            same_day = json.load(open(daily_path, encoding="utf-8"))
    r = check(reading, roster, same_day)
    if list_failed:
        print(",".join(failed_ids(r)))
        return 0
    head = (f"coverage {reading['reading_date']} {r['cadence']}: "
            f"{r['answered']}/{r['expected']} expected models answered")
    if r["skipped"]:
        head += f"; set aside: {', '.join(r['skipped'])}"
    if r["access_confirmed"]:
        # informational, never a failure: first contact for a pre-staged model
        print("ACCESS CONFIRMED (drop availability=pending): " + ", ".join(r["access_confirmed"]))
    if r["shared_quota"]:
        # informational, never a failure and never a push: the weekly ran out of
        # a per-day allowance the same day's daily had already used (see
        # DAILY_QUOTA_PROVIDERS). The gap is real data loss; the fix is a larger
        # daily quota from the provider, not a top-up.
        print("SHARED DAILY QUOTA (weekly partial, same-day daily answered clean; not billing - "
              "raise the provider's per-day quota to close the gap): " + ", ".join(r["shared_quota"]))
    if not r["missing"] and not r["dark"] and not r["billing"] and not r["truncating"]:
        print(head)
        return 0
    detail = []
    if r["missing"]:
        detail.append("MISSING from reading: " + ", ".join(r["missing"]))
    if r["dark"]:
        detail.append("fully errored: " + ", ".join(r["dark"]))
    if r["billing"]:
        detail.append("quota/billing errors on partial readings (top up before the next run): "
                      + ", ".join(r["billing"]))
    if r["truncating"]:
        detail.append("empty truncations at or above the floor (a settings defect - raise "
                      "token_headroom or fix the thinking setting, then bump the roster): "
                      + ", ".join(r["truncating"]))
    msg = head + ". " + ". ".join(detail) + "."
    print("COVERAGE SHORT:", msg)
    topic = os.environ.get("SEISMO_NTFY_TOPIC", "").strip()
    if topic:
        try:
            req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"),
                                         headers={"Title": "seismograph: coverage short",
                                                  "Priority": "high", "Tags": "warning"})
            urllib.request.urlopen(req, timeout=20).read()
        except Exception as e:  # the check result matters more than the push
            print(f"ntfy push failed (non-fatal): {e}")
    return 1


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--failed"]
    raise SystemExit(main(args[0], list_failed="--failed" in sys.argv[1:]))
