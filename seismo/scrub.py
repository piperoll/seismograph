"""Scrub sensitive response text from a raw session before it is witnessed.

The refusal-boundary dimension probes model behaviour on unsafe prompts, so the
model's RESPONSE to those probes is harmful content the instrument never retains.
Grading needs that text - digest runs first and folds the pass rate into the
reading - so this runs AFTER digest and BEFORE the session is witnessed and
archived. It empties the ``text`` field of every sensitive-dimension record and
marks it ``scrubbed``, keeping all non-text stats (status, tokens, latency,
finish, error) intact, so the archived raw stays useful without carrying the
harmful content.

Idempotent: running it again on an already-scrubbed session is a no-op.

    python3 -m seismo.scrub raw/session-...jsonl [more sessions ...]
"""

import json
import sys

# Dimensions whose response text is harmful content and must never be archived.
# Mirrors detect.PARKED_DIMS - the parked harm-probe dimension. Keep in sync.
SENSITIVE_DIMS = {"refusal-boundary"}


def scrub_session(path):
    """Empty the response text of every sensitive-dimension record in-place.

    Returns the number of records whose non-empty text was removed."""
    removed = 0
    lines = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            r = json.loads(s)
            if r.get("dimension") in SENSITIVE_DIMS:
                if r.get("text") not in (None, ""):
                    removed += 1
                r["text"] = None
                r["scrubbed"] = True
            lines.append(json.dumps(r, ensure_ascii=False))
    with open(path, "w", encoding="utf-8") as f:
        if lines:
            f.write("\n".join(lines) + "\n")
    return removed


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python3 -m seismo.scrub <session.jsonl> [...]",
              file=sys.stderr)
        return 2
    total = 0
    for path in argv:
        n = scrub_session(path)
        total += n
        print(f"scrubbed {n} sensitive-dimension response(s) in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
