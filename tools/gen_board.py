"""Generate the public conditions board (site/index.html) and its companion
machine-readable feeds.

The board is a single self-contained HTML page: tools/board_template.html with
a `__PAYLOAD__` slot that we fill with the live series JSON. The template embeds
its own CSS + JS and makes no external requests. Data comes from the witnessed
readings in readings/ (rebuilt fresh every run via seismo.series), so the board
always matches the readings it is derived from.

Not published on any public surface: the `refusal-boundary` dimension. It is the
parked harm-probe dimension; per the charter/flip-runbook decision we withhold
the per-model breakdown from public surfaces (it carries no probe text, but a
per-model refusal-boundary rate reads as a named-model harmful-compliance
ranking). It stays in the private raw archive only. Everything the board and the
served feeds show is stripped of it here.

Usage: python3 tools/gen_board.py [out_path]   (default: site/index.html)
"""

import json
import os
import shutil
import sys

ROOT = os.environ.get("SEISMO_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from seismo.series import build_series  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "site", "index.html")
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "board_template.html")

# The dimension withheld from every public surface (parked harm-probe dimension).
PARKED_DIMS = {"refusal-boundary"}


def _strip_models(cadence_block):
    """Drop parked dimensions from every model's dims, in place."""
    for m in (cadence_block.get("models") or {}).values():
        dims = m.get("dims")
        if isinstance(dims, dict):
            for d in PARKED_DIMS:
                dims.pop(d, None)


def _strip_findings(obj):
    """Drop findings/log entries that name a parked dimension, in place.
    Handles the advisories.json / divergence.json shape (cadence blocks with
    `findings` lists, plus a top-level `log`)."""
    def keep(entry):
        f = entry.get("finding", entry) if isinstance(entry, dict) else {}
        return not (isinstance(f, dict) and f.get("dimension") in PARKED_DIMS)

    if not isinstance(obj, dict):
        return
    if isinstance(obj.get("log"), list):
        obj["log"] = [e for e in obj["log"] if keep(e)]
    # findings live under cadence blocks that may be top-level (daily/weekly) or
    # nested under a "cadence" wrapper.
    parents = [obj, obj.get("cadence")]
    for parent in parents:
        if not isinstance(parent, dict):
            continue
        for cad in ("daily", "weekly"):
            block = parent.get(cad)
            if isinstance(block, dict) and isinstance(block.get("findings"), list):
                block["findings"] = [e for e in block["findings"] if keep(e)]


def _copy_feed(name, sited, transform=None):
    src = os.path.join(ROOT, name)
    if not os.path.exists(src):
        return
    data = json.load(open(src, encoding="utf-8"))
    if transform:
        transform(data)
    with open(os.path.join(sited, name), "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
        f.write("\n")


def main():
    series = build_series(os.path.join(ROOT, "readings"))
    for cad in ("daily", "weekly"):
        if isinstance(series.get(cad), dict):
            _strip_models(series[cad])
    if isinstance(series.get("models"), dict):  # the daily alias
        _strip_models({"models": series["models"]})

    # The journal reads published findings; strip parked-dimension findings and
    # embed the advisories feed alongside the series.
    advisories = {}
    adv_src = os.path.join(ROOT, "advisories.json")
    if os.path.exists(adv_src):
        advisories = json.load(open(adv_src, encoding="utf-8"))
        _strip_findings(advisories)

    # Embed as the board payload. Escape "<" so no "</script>" sequence can break
    # out of a <script type="application/json"> block.
    def _embed(obj):
        return json.dumps(obj, separators=(",", ":")).replace("<", "\\u003c")

    seo_latest = series.get("latest_reading") or \
        __import__("datetime").date.today().isoformat()
    template = open(TEMPLATE, encoding="utf-8").read()
    for slot in ("__PAYLOAD__", "__ADVISORIES__"):
        if slot not in template:
            raise SystemExit(f"board_template.html has no {slot} slot")
    page = (template.replace("__PAYLOAD__", _embed(series))
                    .replace("__ADVISORIES__", _embed(advisories))
                    .replace("__LATEST_READING__", seo_latest))

    sited = os.path.dirname(os.path.abspath(OUT))
    os.makedirs(sited, exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(page)

    # Machine-readable feeds served alongside the board (all parked-dimension
    # stripped). series.json + advisories.json are the exact objects we embedded.
    for name, obj in (("series.json", series), ("advisories.json", advisories)):
        with open(os.path.join(sited, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, separators=(",", ":"))
            f.write("\n")
    _copy_feed("divergence.json", sited, _strip_findings)

    # Figures for llms.txt. Roster totals come from config/models.json (the
    # authority). The lab count is a curated roster fact (DeepInfra alone hosts
    # four labs behind one API key, so it cannot be derived from provider keys);
    # keep ROSTER_LABS in step with README.md's roster paragraph.
    ROSTER_LABS = 12
    daily = series.get("daily", {}).get("models", {}) or {}
    n_daily = len(daily)
    try:
        roster = json.load(open(os.path.join(ROOT, "config", "models.json")))
        n_models = len(roster.get("models", roster))
    except Exception:
        n_models = n_daily
    n_labs = ROSTER_LABS
    latest = series.get("latest_reading") or "unknown"
    n_read = len({d for m in daily.values() for d in (m.get("dates") or [])})

    _llms = f"""# PipeRoll Seismograph

> An independent observatory for AI model behavioural drift. It runs a fixed,
> private probe battery every day against the model APIs that agent fleets depend
> on, and publishes detected behavioural change as witnessed statistical readings:
> "model X changed on date Y, in dimension Z." It measures each model against its
> OWN past, never against other models - it is not a leaderboard and never ranks,
> rates, scores, or certifies a model.

The seismograph is the second instrument of PipeRoll, the agent-incident
measurement institution (the first is the verified incident registry at
piperoll.org). Roster: {n_models} models across {n_labs} labs ({n_daily} measured
daily on the canary battery, the rest weekly on the deep battery).
Baseline running since 2026-08-20. Latest daily reading: {latest};
{n_read} daily readings witnessed.

## What the readings mean
- Reading: a per-model, per-dimension aggregate from one battery run (pass rates,
  refusal rates, token and latency distributions). No raw model text, no per-probe
  detail is ever published.
- Movement: a change against the model's rolling baseline that survives
  Benjamini-Hochberg FDR correction at alpha 0.01 - the strongest claim the
  instrument makes.
- Watch: nominally significant but unconfirmed, possibly noise. Under-alerting is
  policy: the feed publishes raw movement, announcements require editor sign-off.
- Drift means a model changing against itself over time, at pinned minimum-thinking
  settings. Dimensions: capability, instruction-following, structured-output,
  tool-call, sycophancy, verbosity.

## How it works
- The probe battery is private; its sha256 is public and witnessed with every
  reading, so the series is provably unchanged without revealing the probes.
- Every reading is hash-anchored in the Rekor public transparency log at
  measurement time, so baselines provably predate the events they are later cited
  against.
- Two tiers: a fixed frozen ruler (drift) plus a seeded procedural dynamic control
  (an anti-gaming tripwire; a persistent fixed-over-dynamic gap is a Divergence
  finding). Grading is mechanical, deterministic code - no LLM judge.
- Readings are the published artifact; the private raw sessions are the witnessed
  anchor, and readings are their reproducible derivations.

## The readings (machine-readable, updated every run)
- Movement + watch feed: https://seismo.piperoll.org/advisories.json - every
  detected movement and watch, append-only, witnessed each run. This is "what
  changed."
- Full series: https://seismo.piperoll.org/series.json - per-model, per-dimension
  time series behind the board (pass rates, token and latency distributions).
- Divergence (fixed-vs-dynamic gaps): https://seismo.piperoll.org/divergence.json -
  the anti-gaming tripwire; a persistent gap is a Divergence finding.
- All three are also in the repository, and every reading is a witnessed document
  in witness/ (Rekor bundles). No raw model text or per-probe detail is published.

## Key resources
- Methodology charter (ratified 2026-09-15): https://github.com/piperoll/seismograph/blob/main/CHARTER.md
- How it runs (README): https://github.com/piperoll/seismograph/blob/main/README.md
- Repository (code, readings, witness bundles): https://github.com/piperoll/seismograph
- PipeRoll incident registry (the first instrument): https://piperoll.org
- The conditions board (this site): current levels, a trailing window, and every
  movement/advisory - public and free forever.
"""
    open(os.path.join(sited, "llms.txt"), "w", encoding="utf-8").write(_llms)

    # Favicon: the PipeRoll wax seal (shared institutional identity), served
    # same-origin so the board stays free of external requests.
    favicon = os.path.join(os.path.dirname(TEMPLATE), "favicon.svg")
    if os.path.exists(favicon):
        shutil.copyfile(favicon, os.path.join(sited, "favicon.svg"))

    # SEO: robots + a one-URL sitemap (the board is a single page; the feeds and
    # llms.txt are linked from it).
    open(os.path.join(sited, "robots.txt"), "w", encoding="utf-8").write(
        "User-agent: *\nAllow: /\nSitemap: https://seismo.piperoll.org/sitemap.xml\n")
    lastmod = latest if latest and latest != "unknown" else \
        __import__("datetime").date.today().isoformat()
    # lastmod = the latest reading date (each reading is a substantive content
    # change to the board). priority/changefreq omitted - search engines ignore
    # them.
    open(os.path.join(sited, "sitemap.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'<url><loc>https://seismo.piperoll.org/</loc><lastmod>{lastmod}</lastmod></url>\n'
        '</urlset>\n')

    # custom domain for GitHub Pages: OPT-IN via SEISMO_CNAME (default off).
    # Emitting a CNAME makes github.io 301-redirect to that domain immediately,
    # so it must only be set once the domain is verified + serving in GitHub
    # Pages - otherwise the board goes dark at both URLs.
    cname = os.environ.get("SEISMO_CNAME", "").strip()
    if cname:
        open(os.path.join(sited, "CNAME"), "w", encoding="utf-8").write(cname + "\n")

    n_weekly = len(series.get("weekly", {}).get("models", {}) or {})
    print(f"wrote {OUT} {len(page)} bytes; {n_read} daily readings; "
          f"{n_daily} daily / {n_weekly} weekly models; roster {n_models}/{n_labs} labs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
