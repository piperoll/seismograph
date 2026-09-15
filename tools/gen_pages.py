"""Static, crawlable content pages for the seismograph.

The board at / is an interactive single-page app; a crawler that does not run
JavaScript sees an empty body. These pages are the opposite: fully server-
rendered HTML with real content, one canonical URL each, ordinary <a> links
between them, and no dependency on JavaScript to show anything.

Generated from the same stripped series + advisories the board uses, so they
carry no parked-dimension data and no probe text. Called by gen_board.py.

Pages:
  /methodology/            - how the instrument works (static prose)
  /models/                 - index of every measured model
  /models/<slug>/          - one model: coverage status, its findings, history
  /findings/               - index of every published finding
  /findings/<slug>/        - one finding: baseline, rule, coverage, evidence links
"""

import html
import base64
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlencode

BASE = "https://seismo.piperoll.org"
REPO = "https://github.com/piperoll/seismograph"

CSS = (
    ":root{--paper:#f5f3ec;--panel:#fffefb;--ink:#242c2b;--muted:#69716e;"
    "--rule:#dcded5;--teal:#176d6c;--rust:#a55232;--mono:ui-monospace,"
    "SFMono-Regular,Consolas,monospace;--serif:Georgia,'Times New Roman',serif}"
    "*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);"
    "font:16px/1.6 system-ui,-apple-system,sans-serif}a{color:var(--teal)}"
    ".wrap{max-width:760px;margin:0 auto;padding:0 22px}"
    ".mh{border-bottom:1px solid var(--ink);padding:20px 0;margin-bottom:8px;"
    "font:600 13px var(--mono);letter-spacing:.04em}.mh a{color:inherit;text-decoration:none}"
    ".mh span{color:var(--muted);font-weight:400}"
    "h1{font:400 clamp(28px,5vw,42px)/1.12 var(--serif);letter-spacing:-.02em;margin:26px 0 6px}"
    "h2{font:400 24px var(--serif);margin:32px 0 8px}h3{font:600 15px var(--mono);margin:24px 0 6px}"
    ".eyebrow{font:11px var(--mono);text-transform:uppercase;letter-spacing:.12em;color:var(--teal);margin-top:24px}"
    ".lede{color:var(--muted);font-size:18px;margin:0 0 8px}"
    ".pill{display:inline-block;font:600 11px var(--mono);border:1px solid var(--rule);"
    "border-radius:3px;padding:2px 8px;vertical-align:middle}.pill.mv{border-color:var(--teal);color:var(--teal)}"
    ".pill.wt{color:var(--muted)}"
    ".ba{font:600 26px var(--mono);margin:10px 0}.ba .to{color:var(--muted);font-weight:400;margin:0 10px}"
    ".meta{color:var(--muted);font:13px var(--mono);margin:4px 0}"
    ".card{border:1px solid var(--rule);border-radius:6px;background:var(--panel);padding:14px 18px;margin:12px 0}"
    ".card h3{margin-top:0}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,240px),1fr));gap:2px 20px}"
    ".row{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid #eff0e9;font-size:14px}"
    ".row .s{color:var(--muted);font:12px var(--mono);text-align:right}"
    "table{border-collapse:collapse;width:100%;font-size:14px;margin:10px 0}"
    "td,th{text-align:left;padding:6px 10px;border-bottom:1px solid var(--rule)}th{font:600 12px var(--mono);color:var(--muted)}"
    "footer{border-top:1px solid var(--rule);margin-top:48px;padding:20px 0 40px;color:var(--muted);"
    "font:12px/1.8 var(--mono)}footer a{color:var(--muted)}"
    ".note{color:var(--muted);font-size:14px}"
)


def esc(s):
    return html.escape(str(s if s is not None else ""))


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")


def page(title, description, path, body, og_type="article"):
    url = BASE + path
    return (
        '<!doctype html><html lang="en"><head>'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light">'
        f"<title>{esc(title)}</title>"
        f'<meta name="description" content="{esc(description)}">'
        f'<link rel="canonical" href="{url}">'
        '<link rel="icon" type="image/svg+xml" href="/favicon.svg">'
        f'<meta property="og:type" content="{og_type}"><meta property="og:site_name" content="PipeRoll">'
        f'<meta property="og:title" content="{esc(title)}">'
        f'<meta property="og:description" content="{esc(description)}">'
        f'<meta property="og:url" content="{url}">'
        '<meta property="og:image" content="https://seismo.piperoll.org/og.png">'
        '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
        '<meta property="og:image:alt" content="PipeRoll Seismograph: AI model behaviour, measured over time.">'
        '<meta name="twitter:card" content="summary_large_image">'
        '<meta name="twitter:image" content="https://seismo.piperoll.org/og.png">'
        f"<style>{CSS}</style></head><body><div class=\"wrap\">"
        '<header class="mh"><a href="https://piperoll.org">PIPEROLL</a> '
        '<span>/ <a href="/">SEISMOGRAPH</a></span></header>'
        f"<main>{body}</main>"
        '<footer><a href="/">Interactive board</a> &middot; '
        '<a href="/methodology/">Methodology</a> &middot; '
        '<a href="/models/">Models</a> &middot; <a href="/findings/">Findings</a><br>'
        f'Live readings from the <a href="{REPO}">PipeRoll seismograph</a>, witnessed daily in Rekor. '
        'Machine-readable: <a href="/advisories.json">advisories.json</a> &middot; '
        '<a href="/series.json">series.json</a> &middot; <a href="/llms.txt">llms.txt</a>. '
        'CC BY 4.0. Readings, not ratings.</footer>'
        '</div>'
        '<script data-goatcounter="https://piperoll.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>'
        "</body></html>"
    )


def _write(sited, path, content):
    """path like '/models/foo/' -> site/models/foo/index.html"""
    rel = path.strip("/")
    d = os.path.join(sited, rel) if rel else sited
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(content)


def reading_witnesses(root):
    """Link a reading to a bundle with the same SHA-256 digest.

    This associates artifacts; it does not verify the signature or Rekor proof.
    Missing or mismatched bundles use the explicitly labelled directory fallback.
    """
    root = Path(root)
    links = {}
    for bundle in sorted((root / "witness").glob("*-reading-*.json.bundle.json")):
        match = re.search(r"reading-(\d{4}-\d{2}-\d{2})-(daily|weekly)\.json\.bundle\.json$", bundle.name)
        if not match:
            continue
        date, cadence = match.groups()
        reading = root / "readings" / date[:4] / f"reading-{date}-{cadence}.json"
        try:
            digest = json.loads(bundle.read_text())["messageSignature"]["messageDigest"]
            if digest.get("algorithm") != "SHA2_256":
                continue
            if base64.b64decode(digest["digest"], validate=True) != hashlib.sha256(reading.read_bytes()).digest():
                continue
        except (OSError, ValueError, KeyError, TypeError):
            continue
        links[f"{date}|{cadence}"] = f"{REPO}/blob/main/witness/{bundle.name}"
    return links


# --- finding derivation (mirrors the board's findingItems) -------------------

def finding_items(advisories, cad):
    items, g = [], {}
    for e in advisories.get("log", []):
        if e.get("cadence") != cad or not e.get("finding"):
            continue
        f = e["finding"]
        key = (f["model"], f.get("dimension"), f.get("metric"))
        o = g.get(key)
        if not o:
            o = {"model": f["model"], "f": f, "level": "movement",
                 "onset": e["date"], "latest": e["date"], "n": 0,
                 "dimension": f.get("dimension"), "metric": f.get("metric")}
            g[key] = o
        o["n"] += 1
        if e["date"] < o["onset"]:
            o["onset"], o["f"] = e["date"], f
        if e["date"] > o["latest"]:
            o["latest"] = e["date"]
    items.extend(g.values())
    block = (advisories.get("cadence") or {}).get(cad) or {}
    cd = block.get("reading_date")
    for f in block.get("findings", []):
        if f.get("metric") == "coverage":
            continue
        if not (_num(f.get("baseline")) and _num(f.get("current"))):
            continue
        latency = str(f.get("metric", "")).startswith("latency")
        if f.get("level") == "movement" and not latency:
            continue
        items.append({"model": f["model"], "f": f,
                      "level": "context" if latency else f.get("level"),
                      "onset": cd, "latest": cd, "n": 1,
                      "dimension": f.get("dimension"), "metric": f.get("metric"),
                      "latency": latency})
    return items


def _num(v):
    return isinstance(v, (int, float))


NAMES = {"capability": "Capability", "instruction-following": "Instruction following",
         "structured-output": "Structured output", "tool-call": "Tool call",
         "sycophancy": "Sycophancy probes", "verbosity": "Verbosity probes"}
ASSESS = {"assessed": "Assessed", "partial": "Assessment limited",
          "baseline": "Baseline accruing", "coverage": "Insufficient coverage",
          "absent": "No reading"}


def _headline(f):
    m = f.get("metric")
    if m == "thinking_tokens_mean":
        base = "Thinking-token use"
    elif m == "latency_p50":
        base = "Median latency"
    elif m == "latency_p95":
        base = "p95 latency"
    elif m == "pass_rate":
        base = (NAMES.get(f.get("dimension"), f.get("dimension")) or "") + " pass rate"
    else:
        base = m or "finding"
    up = (f.get("current") or 0) >= (f.get("baseline") or 0)
    sub = ""
    d = f.get("dimension")
    if d and d != "-" and m != "pass_rate":
        sub = " on the " + (NAMES.get(d, d) or "").lower().replace(" probes", "") + " probe set"
    return base + (" rose" if up else " fell") + sub


def _fmt(v, f):
    if not _num(v):
        return "&mdash;"
    m = f.get("metric")
    if m == "pass_rate":
        return f"{v*100:.0f}%"
    if str(m).startswith("latency"):
        return f"{v/1000:.2f} s"
    if m == "thinking_tokens_mean":
        return f"{v:,.0f} tok"
    return f"{v:.1f}"


def _rule(f):
    m, lvl = f.get("metric"), f.get("level")
    if m == "pass_rate":
        return ("Survives Benjamini-Hochberg FDR at &alpha;=0.01" if lvl == "movement"
                else "Nominally significant (p&lt;0.01), unconfirmed")
    if m == "thinking_tokens_mean":
        return ("Relative shift past the serving-tripwire threshold" if lvl == "movement"
                else "Relative shift past the watch threshold, unconfirmed")
    if str(m).startswith("latency"):
        return "Relative p50 shift past threshold, operational context (never a standalone drift claim)"
    return ""


def finding_slug(it):
    f = it["f"]
    metric = {"thinking_tokens_mean": "thinking", "latency_p50": "latency-p50",
              "latency_p95": "latency-p95", "pass_rate": "pass-rate"}.get(f.get("metric"), slug(f.get("metric")))
    parts = [it["onset"], slug(it["model"])]
    if f.get("dimension") and f.get("dimension") != "-":
        parts.append(slug(f.get("dimension")))
    parts.append(metric)
    return "-".join(p for p in parts if p)


def model_slug(mid):
    return slug(mid)


# --- page builders -----------------------------------------------------------

def build_static_pages(series, advisories, sited, witnesses=None):
    """Generate all static pages; return the list of URL paths for the sitemap."""
    paths = []
    daily_models = (series.get("daily", {}) or {}).get("models", {}) or {}
    weekly_models = (series.get("weekly", {}) or {}).get("models", {}) or {}
    all_ids = sorted(set(daily_models) | set(weekly_models))

    # assessment status lookup, per cadence
    assess = {}
    for cad in ("daily", "weekly"):
        block = (advisories.get("cadence") or {}).get(cad) or {}
        for a in block.get("assessment", []):
            assess.setdefault(a["model"], {})[cad] = a

    items = {cad: finding_items(advisories, cad) for cad in ("daily", "weekly")}
    items_by_model = {}
    for cad, lst in items.items():
        for it in lst:
            it["cad"] = cad
            items_by_model.setdefault(it["model"], []).append(it)

    # ---- methodology ----
    _write(sited, "/methodology/", _methodology())
    paths.append("/methodology/")

    # ---- model index + pages ----
    rows = []
    for mid in all_ids:
        st = (assess.get(mid, {}).get("daily") or assess.get(mid, {}).get("weekly") or {})
        label = ASSESS.get(st.get("status"), "measured")
        nf = len(items_by_model.get(mid, []))
        badge = f' &middot; {nf} finding{"s" if nf != 1 else ""}' if nf else ""
        rows.append(f'<div class="row"><a href="/models/{model_slug(mid)}/">{esc(mid)}</a>'
                    f'<span class="s">{esc(label)}{badge}</span></div>')
    _write(sited, "/models/", page(
        "Models measured - PipeRoll Seismograph",
        "Every large language model API the PipeRoll seismograph measures daily or weekly, with its current assessment status.",
        "/models/",
        f'<div class="eyebrow">Coverage</div><h1>Models measured</h1>'
        f'<p class="lede">Every model the seismograph measures against its own past. '
        f'{len(all_ids)} models across daily and weekly batteries. Never ranked.</p>'
        + "".join(rows)))
    paths.append("/models/")
    for mid in all_ids:
        _write(sited, f"/models/{model_slug(mid)}/",
               _model_page(mid, daily_models.get(mid), weekly_models.get(mid),
                           assess.get(mid, {}), items_by_model.get(mid, [])))
        paths.append(f"/models/{model_slug(mid)}/")

    # ---- findings index + pages ----
    flat = []
    seen = set()
    for cad in ("daily", "weekly"):
        for it in items[cad]:
            s = finding_slug(it)
            if s in seen:
                continue
            seen.add(s)
            flat.append(it)
    flat.sort(key=lambda it: (0 if it["level"] == "movement" else 1, it["onset"]), reverse=False)
    flat.sort(key=lambda it: it["onset"], reverse=True)
    frows = []
    for it in flat:
        lvl = it["level"]
        latency = str(it["metric"] or "").startswith("latency")
        plabel = "Movement" if lvl == "movement" else ("Context" if latency else "Watch")
        pcls = "mv" if lvl == "movement" else "wt"
        frows.append(f'<div class="row"><a href="/findings/{finding_slug(it)}/">'
                     f'{esc(it["model"])} &middot; {_headline(it["f"])}</a>'
                     f'<span class="s"><span class="pill {pcls}">{plabel}</span> {esc(it["onset"])}</span></div>')
    _write(sited, "/findings/", page(
        "Published findings - PipeRoll Seismograph",
        "Every change the PipeRoll seismograph flagged against a model's own witnessed baseline: movements, watches, and operational-context findings.",
        "/findings/",
        '<div class="eyebrow">The feed</div><h1>Published findings</h1>'
        '<p class="lede">Every change the detector flagged against a model\'s own '
        'witnessed baseline. Pass-rate Movements survive multiple-comparison '
        'correction; thinking-token Movements cross a relative-shift threshold. '
        'Watches are unconfirmed; latency is operational context.</p>'
        + ("".join(frows) if frows else '<p class="note">No findings currently published.</p>')))
    paths.append("/findings/")
    for it in flat:
        _write(sited, f"/findings/{finding_slug(it)}/", _finding_page(it, series, witnesses))
        paths.append(f"/findings/{finding_slug(it)}/")

    return paths


def _methodology():
    body = (
        '<div class="eyebrow">Methodology</div>'
        '<h1>How the seismograph works</h1>'
        '<p class="lede">An independent record of when the model APIs that agent '
        'fleets depend on quietly change behaviour. It measures each model against '
        'its own past, and never ranks models.</p>'
        '<h2>What it measures</h2>'
        '<p>Every day a fixed, private probe battery runs against the model APIs in '
        'the roster. Responses are graded by deterministic, versioned code - no LLM '
        'judge. The public board shows per-model, per-dimension pass rates, '
        'token and latency distributions for the active dimensions. No raw model text and no per-probe '
        'detail is ever published.</p>'
        '<h2>Two batteries</h2>'
        '<p>A <b>daily canary</b> (a fast, shallow tripwire) runs against the '
        'daily-cadence models; a <b>weekly deep battery</b> runs against all models '
        'for more statistical power. They are different rulers and their series are '
        'never pooled.</p>'
        '<h2>Movements, watches, and the decision rules</h2>'
        '<p>A finding compares one model to its own rolling, witnessed baseline. '
        'The rule depends on the metric:</p>'
        '<table><tr><th>metric</th><th>rule</th></tr>'
        '<tr><td>probe pass rate</td><td>Two-proportion test with Benjamini-Hochberg '
        'FDR control. <b>Movement</b> survives at &alpha;=0.01; <b>watch</b> is '
        'nominally significant but unconfirmed.</td></tr>'
        '<tr><td>thinking-token use</td><td>Relative-shift threshold - a serving-'
        'configuration tripwire. Not a significance test.</td></tr>'
        '<tr><td>latency</td><td>Relative-shift threshold, treated as operational '
        'context, never a standalone drift claim.</td></tr></table>'
        '<p>Under-alerting is deliberate policy: the feed publishes raw movement, '
        'and alert-grade announcements require editor sign-off.</p>'
        '<h2>Witnessing</h2>'
        '<p>Every run is signed into the Rekor public transparency log at measurement '
        'time. A baseline provably predates the event it is later cited against, so '
        'the record cannot be back-dated.</p>'
        '<h2>Readings, not ratings</h2>'
        '<p>The seismograph never grades, ranks, scores, or certifies a model. It '
        'answers "did this model change?", never "which model is best?". Cause is a '
        'separate question it does not settle.</p>'
        '<h2>What it is not, yet</h2>'
        '<p>The instrument is early. Its strongest asset is accumulated measurement '
        'that predates a disputed change. What it still needs to establish is its '
        'detection power: how large a change it reliably catches, how quickly, and '
        'its false-alarm rate.</p>'
        '<h3>Full detail</h3>'
        f'<p><a href="{REPO}/blob/main/CHARTER.md">Methodology charter</a> &middot; '
        f'<a href="{REPO}/blob/main/README.md">README</a> &middot; '
        f'<a href="{REPO}">code, readings, and witness bundles</a>.</p>'
    )
    return page("How the PipeRoll Seismograph works - methodology",
                "How PipeRoll's seismograph measures LLM API behavioural drift: a fixed private probe battery, deterministic grading, a daily canary and weekly deep battery, movement/watch decision rules, and Rekor witnessing. Readings, not ratings.",
                "/methodology/", body)


def _model_page(mid, dm, wm, assess, its):
    sources = [(cad, src) for cad, src in (("daily", dm), ("weekly", wm)) if src]
    cadences = " and ".join(cad for cad, _ in sources)
    rows, notes, explore, summaries = [], [], [], []
    for cad, src in sources:
        dates = src.get("dates") or []
        st = assess.get(cad) or {}
        status = ASSESS.get(st.get("status"), "Assessment not reported")
        elig = (f" ({st.get('eligible')}/{st.get('attempted')} metrics eligible)"
                if st.get("attempted") else "")
        rng = f"{dates[0]} to {dates[-1]}" if dates else "no readings"
        rows.append(
            f'<tr><th>{cad} battery</th><td>{len(dates)} readings ({esc(rng)})<br>'
            f'Latest assessment: {esc(status)}{elig}</td></tr>')
        summaries.append(f"{cad}: {status}")
        if st.get("status") == "assessed":
            note = "No findings in completed eligible tests on the latest reading."
        elif st.get("status") == "partial":
            note = "Only some metrics could be assessed; the rest lacked baseline or coverage."
        elif st.get("status") == "baseline":
            note = "No assessment completes until enough baseline readings accumulate."
        elif st.get("status") == "coverage":
            note = "The latest reading could not be assessed because it lacked gradable calls."
        else:
            note = "No assessment conclusion is available for the latest reading."
        notes.append(f'<p class="note">{cad.capitalize()}: {note}</p>')
        params = urlencode({"model": mid, "cadence": cad})
        explore.append(f'<a href="/#dossier?{esc(params)}">Open the {cad} dossier</a>')
    cards = ""
    for it in its:
        f = it["f"]
        latency = str(it["metric"] or "").startswith("latency")
        plabel = "Movement" if it["level"] == "movement" else ("Context" if latency else "Watch")
        pcls = "mv" if it["level"] == "movement" else "wt"
        cards += (
            f'<div class="card"><h3><a href="/findings/{finding_slug(it)}/">{_headline(f)}</a> '
            f'<span class="pill {pcls}">{plabel}</span></h3>'
            f'<div class="ba">{_fmt(f.get("baseline"), f)}<span class="to">&rarr;</span>'
            f'{_fmt(f.get("current"), f)}</div>'
            f'<div class="meta">{esc(it["cad"])} battery &middot; {_rule(f)} '
            f'&middot; first flagged {esc(it["onset"])}</div></div>')
    src = dm or wm or {}
    body = (
        '<div class="eyebrow">Model</div>'
        f'<h1>{esc(mid)}</h1>'
        f'<p class="lede">Measured against its own past on the {cadences} '
        'batteries. Each battery has its own history and assessment.</p>'
        '<table>'
        f'<tr><th>provider channel</th><td>{esc(src.get("provider") or "-")}</td></tr>'
        + "".join(rows) + '</table><h2>Published findings</h2>'
        + (cards or "".join(notes))
        + '<h3>Explore</h3><p>' + " &middot; ".join(explore)
        + '. Each dossier shows this model and battery, with the full dimension history.</p>'
    )
    findings_note = (f"{len(its)} published finding{'s' if len(its) != 1 else ''}. "
                     if its else "")
    return page(
        f"{mid} - drift readings - PipeRoll Seismograph",
        f"Behavioural-drift readings for {mid}, measured against its own past. {findings_note}"
        + "Latest assessments: " + "; ".join(summaries) + ". Readings, not ratings.",
        f"/models/{model_slug(mid)}/", body)


def _finding_page(it, series, witnesses=None):
    f = it["f"]
    cad = it["cad"]
    latency = str(it["metric"] or "").startswith("latency")
    plabel = "Movement" if it["level"] == "movement" else ("Context" if latency else "Watch")
    pcls = "mv" if it["level"] == "movement" else "wt"
    reading_url = f"{REPO}/blob/main/readings/{it['onset'][:4]}/reading-{it['onset']}-{cad}.json"
    witness_url = (witnesses or {}).get(f"{it['onset']}|{cad}")
    witness_label = "Rekor witness bundle" if witness_url else "Rekor witness directory"
    witness_url = witness_url or f"{REPO}/tree/main/witness"
    persist = (f"still flagged {it['latest']} ({it['n']} readings)"
               if it["latest"] > it["onset"] else "latest reading")
    # coverage: call errors on the onset reading, from series
    errs = None
    m = ((series.get(cad, {}) or {}).get("models", {}) or {}).get(it["model"])
    if m and it["onset"] in (m.get("dates") or []):
        i = m["dates"].index(it["onset"])
        ce = m.get("call_errors") or []
        errs = ce[i] if i < len(ce) else None
    head = _headline(f)
    body = (
        '<div class="eyebrow">Published finding</div>'
        f'<h1>{esc(it["model"])}: {head.lower()}</h1>'
        f'<p class="lede"><span class="pill {pcls}">{plabel}</span> on the {esc(cad)} '
        'battery. This model measured against its own witnessed baseline.</p>'
        f'<div class="ba">{_fmt(f.get("baseline"), f)}<span class="to">&rarr;</span>'
        f'{_fmt(f.get("current"), f)}</div>'
        '<table>'
        f'<tr><th>model</th><td><a href="/models/{model_slug(it["model"])}/">{esc(it["model"])}</a></td></tr>'
        f'<tr><th>dimension</th><td>{esc(NAMES.get(f.get("dimension"), f.get("dimension")) or "model-level")}</td></tr>'
        f'<tr><th>metric</th><td>{esc(f.get("metric"))}</td></tr>'
        f'<tr><th>decision rule</th><td>{_rule(f)}</td></tr>'
        f'<tr><th>first flagged</th><td>{esc(it["onset"])} &middot; {esc(persist)}</td></tr>'
        + (f'<tr><th>coverage</th><td>{errs} call error{"s" if errs != 1 else ""} on this reading</td></tr>'
           if errs is not None else "")
        + '</table>'
        '<h3>Trace the evidence</h3>'
        f'<p><a href="{reading_url}">The witnessed reading</a> for this date and battery, '
        f'and the <a href="{witness_url}">{witness_label}</a>. '
        f'The full series is in <a href="/series.json">series.json</a>.</p>'
        '<p class="note">This entry records an observation under the stated decision rule. '
        'Watches remain unconfirmed; latency is operational context. '
        'The instrument does not establish the cause of a change.</p>'
    )
    desc = (f"{plabel}: {it['model']} {head.lower()}, {_fmt(f.get('baseline'), f)} to "
            f"{_fmt(f.get('current'), f)}, first flagged {it['onset']}. "
            "Measured against the model's own witnessed baseline.")
    desc = re.sub(r"&[a-z]+;", "", desc)
    return page(f"{it['model']}: {head.lower()} - PipeRoll Seismograph",
                desc, f"/findings/{finding_slug(it)}/", body)
