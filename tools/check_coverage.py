"""Post-run coverage check: did every model the roster expects for this
cadence land in today's reading, and did it actually answer?

Expected = roster models for the cadence (daily: cadence=daily; weekly: all
text models; decision: cadence=decision), minus any the run itself set aside
as keyless or access-pending (those are recorded, not silent). For each
expected model the reading must contain it with at least one graded call.

Exit 1 with a one-line report when anything is missing or fully dark, so the
canary step goes red and (when SEISMO_NTFY_TOPIC is set) a push goes out the
same hour - not the next evening's heartbeat.

    python3 tools/check_coverage.py readings/2026/reading-2026-10-05-daily.json
"""

import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def check(reading, roster):
    cadence = reading["cadence"]
    expected = expected_models(roster, cadence)
    skipped = set(reading.get("skipped_no_key") or []) | set(reading.get("skipped_access_pending") or [])
    got = reading.get("models", {})
    missing, dark, ok = [], [], []
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
    return {"cadence": cadence, "expected": len(expected), "skipped": sorted(skipped),
            "answered": len(ok), "missing": missing, "dark": dark}


def main(path):
    reading = json.load(open(path, encoding="utf-8"))
    roster = json.load(open(os.path.join(ROOT, "config", "models.json"), encoding="utf-8"))
    r = check(reading, roster)
    head = (f"coverage {reading['reading_date']} {r['cadence']}: "
            f"{r['answered']}/{r['expected']} expected models answered")
    if r["skipped"]:
        head += f"; set aside: {', '.join(r['skipped'])}"
    if not r["missing"] and not r["dark"]:
        print(head)
        return 0
    detail = []
    if r["missing"]:
        detail.append("MISSING from reading: " + ", ".join(r["missing"]))
    if r["dark"]:
        detail.append("fully errored: " + ", ".join(r["dark"]))
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
    raise SystemExit(main(sys.argv[1]))
