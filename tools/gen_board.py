#!/usr/bin/env python3
"""Seismograph preview board v2 - reads the seismograph repo, emits one HTML file."""
import json, glob, html, os, sys
ROOT = os.environ.get("SEISMO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "site", "index.html")
DIMS = ["capability","instruction-following","refusal-boundary","structured-output","sycophancy","tool-call","verbosity"]
DIMSHORT = {"capability":"capability","instruction-following":"instruction","refusal-boundary":"refusal","structured-output":"structured","sycophancy":"sycophancy","tool-call":"tool-call","verbosity":"verbosity"}

readings = []
for f in sorted(glob.glob(ROOT+"/readings/2026/*.json")):
    r = json.load(open(f)); readings.append(r)
daily = [r for r in readings if r["cadence"]=="daily" and r["battery"]["name"]!="dynamic"]
weekly = [r for r in readings if r["cadence"]=="weekly" and r["battery"]["name"]=="deep"]
latest = daily[-1]
cfg = json.load(open(ROOT+"/config/models.json"))
roster = cfg.get("models",cfg)
order = [m["id"] for m in roster]
def _group(mid):
    if "@" in mid: return mid.split("@",1)[1]
    for pre,g in (("claude","anthropic"),("gpt","openai"),("gemini","google")):
        if mid.startswith(pre): return g
    return mid
prov = {m["id"]: _group(m["id"]) for m in roster}
LAB = {"claude":"Anthropic","gpt":"OpenAI","gemini":"Google","grok":"xAI","kimi":"Moonshot",
       "deepseek":"DeepSeek","mistral":"Mistral","sarvam":"Sarvam","qwen3":"Alibaba",
       "glm":"Zhipu","llama":"Meta","minimax":"MiniMax"}
def _lab(mid):
    stem=mid.split("@")[0]
    for pre,l in LAB.items():
        if stem.startswith(pre): return l
    return stem
labs = {_lab(m["id"]) for m in roster}
cad_of = {m["id"]: m.get("cadence","daily") for m in roster}
adv = json.load(open(ROOT+"/advisories.json"))
findings = adv.get("cadence",{}).get("daily",{}).get("findings",[])

def overall(m):
    tot=n=0
    for dv in (m.get("dimensions") or {}).values():
        pr=dv.get("pass_rate")
        if pr is None: continue
        tot += pr*dv["n"]; n += dv["n"]
    return (tot/n) if n else None

# ---- assemble series per model ----
def build(models_readings):
    out={}
    for r in models_readings:
        for mid,m in r["models"].items():
            e=out.setdefault(mid,{"dates":[],"overall":[],"dims":{d:[] for d in DIMS},"think":{d:[] for d in DIMS},
                                  "errors":[],"eclass":[],"cost":[],"lat50":[],"lat95":[],"calls":[]})
            e["dates"].append(r["reading_date"])
            e["overall"].append(overall(m))
            for d in DIMS:
                dv=(m.get("dimensions") or {}).get(d) or {}
                e["dims"][d].append(dv.get("pass_rate"))
                tk=(dv.get("thinking_tokens") or {}).get("mean")
                e["think"][d].append(tk)
            e["errors"].append(sum((m.get("errors_by_class") or {}).values()))
            e["eclass"].append(m.get("errors_by_class") or {})
            e["cost"].append(m.get("cost_usd_est"))
            lm=m.get("latency_ms") or {}
            e["lat50"].append(lm.get("p50")); e["lat95"].append(lm.get("p95"))
            e["calls"].append(m.get("calls"))
    return out
D = build(daily); W = build(weekly)

def pooled(e, k):
    """probe-weighted pooled overall over last k readings"""
    vals=[v for v in e["overall"][-k:] if v is not None]
    return sum(vals)/len(vals) if vals else None

def fmt_pct(v): return "&ndash;" if v is None else f"{round(v*100)}%"

# ---- trendline svg ----
def spark(e, wpx=230, hpx=46, accent="var(--key)"):
    ys=[v for v in e["overall"] if v is not None]
    if not ys: return "<span class='quiet'>no data</span>"
    pts=[(i,v) for i,v in enumerate(e["overall"]) if v is not None]
    n=len(e["dates"]); lo=min(min(ys),0.55); hi=1.0
    X=lambda i: 10+(wpx-20)*(i/max(n-1,1)); Y=lambda v: 8+(hpx-18)*(1-(v-lo)/(hi-lo))
    base=[v for v in e["overall"][:7] if v is not None]
    band=""
    if len(base)>=3:
        b1,b2=min(base),max(base)
        band=f"<rect x='10' y='{Y(b2):.1f}' width='{wpx-20}' height='{max(Y(b1)-Y(b2),1.5):.1f}' class='band'/>"
    path="L".join(f"{X(i):.1f},{Y(v):.1f}" for i,v in pts)
    dots=""
    if len(pts)<=14:
        for i,v in pts:
            last = (i==pts[-1][0])
            dots+=(f"<circle cx='{X(i):.1f}' cy='{Y(v):.1f}' r='{3 if last else 2.4}' "
                   f"class='{'dotend' if last else 'dot'}' data-tip='{e['dates'][i]}: {round(v*100)}%'/>")
    return (f"<svg width='{wpx}' height='{hpx}' role='img'>{band}"
            f"<path d='M{path}' class='trend'/>{dots}</svg>")

# ---- flags ----
advmap={}
for f in findings:
    advmap.setdefault(f.get("model"),[]).append(f)
def flags(mid,e):
    out=[]
    for f in advmap.get(mid,[]):
        lvl=f["level"]; met=f.get("metric","")
        if met=="latency_p50":
            out.append(f"<span class='chip lat'>{lvl}: latency p50 {round(f['baseline'])}&rarr;{round(f['current'])} ms <i>(context, not logged)</i></span>")
        elif "thinking" in met:
            out.append(f"<span class='chip {lvl}'>{lvl}: thinking tokens {DIMSHORT.get(f.get('dimension'),f.get('dimension'))} {round(f['baseline'])}&rarr;{round(f['current'])}</span>")
        else:
            out.append(f"<span class='chip {lvl}'>{lvl}: {DIMSHORT.get(f.get('dimension'),f.get('dimension'))} {fmt_pct(f.get('baseline'))}&rarr;{fmt_pct(f.get('current'))}</span>")
    lows=[(d,e["dims"][d][-1]) for d in DIMS if e["dims"][d][-1] is not None and e["dims"][d][-1]<0.75]
    for d,v in lows:
        out.append(f"<span class='chip low'>low today: {DIMSHORT[d]} {fmt_pct(v)}</span>")
    errs=e["errors"][-1]
    if errs: out.append(f"<span class='chip err'>{errs} errored call{'s' if errs>1 else ''}</span>")
    if not out: return "<span class='quiet' title='no advisory findings; every dimension at or above 75%; zero errored calls'>nothing to flag</span>"
    return " ".join(out)

# ---- rows ----
def rows(series, cad):
    outp=[]; seen_prov=None
    ids=[i for i in order if i in series and (cad=="weekly" or cad_of[i]=="daily")]
    gorder=[]
    for i in ids:
        if prov[i] not in gorder: gorder.append(prov[i])
    ids=sorted(ids, key=lambda i: gorder.index(prov[i]))  # stable: keeps roster order within group
    for mid in ids:
        e=series[mid]; p=prov[mid]
        if p!=seen_prov:
            outp.append(f"<tr class='ghead'><td colspan='7'>{p}</td></tr>"); seen_prov=p
        today=e["overall"][-1]
        l50=e["lat50"][-1]; l95=e["lat95"][-1]
        lat= "&ndash;" if l50 is None else f"{round(l50)} / {round(l95)}"
        w7=pooled(e,7); w30=pooled(e,30)
        nd=len([v for v in e['overall'] if v is not None])
        outp.append(
          f"<tr class='mrow' data-mid='{mid}' data-cad='{cad}' tabindex='0'>"
          f"<td class='mid'>{mid}</td><td>{spark(e)}</td>"
          f"<td class='big'>{fmt_pct(today)}</td>"
          f"<td class='win'>{fmt_pct(w7)}<span class='n'> ({min(nd,7)}d)</span></td>"
          f"<td class='win'>{fmt_pct(w30)}<span class='n'> ({min(nd,30)}d)</span></td>"
          f"<td class='notes'>{flags(mid,e) if cad=='daily' else weekly_flag(e)}</td>"
          f"<td class='lat'>{lat}</td></tr>")
    return "\n".join(outp)

def weekly_flag(e):
    n=len([v for v in e["overall"] if v is not None])
    return f"<span class='quiet'>baseline accruing ({n} of 7 deep readings)</span>"

# ---- fleet tiles ----
fleet_cost=sum(c for c in D[max(D,key=lambda k:0)]["cost"][-1:] if c) if False else \
           sum((latest["models"][m].get("cost_usd_est") or 0) for m in latest["models"])
priced=sum(1 for m in latest["models"].values() if m.get("cost_usd_est") is not None)
n_read=len(daily); n_models=len(order); n_labs=len(labs)
# Latency findings are context by charter - they never set the headline state
# and are counted separately, whatever level the detector assigned them.
core=[f for f in findings if f.get("metric")!="latency_p50"]
n_lat=len(findings)-len(core)
n_mv=sum(1 for f in core if f["level"]=="movement")
n_watch=sum(1 for f in core if f["level"]=="watch")
state = "MOVEMENT" if n_mv else ("WATCH" if n_watch else "QUIET")
datelist=" &middot; ".join(d.replace("2026-","") for d in [r["reading_date"] for r in daily])

# ---- advisory feed panel ----
def advrow(f):
    lvl=f["level"]; mid=f.get("model","fleet"); met=f.get("metric","")
    if met=="latency_p50":
        what=f"latency p50 {round(f['baseline'])} ms &rarr; {round(f['current'])} ms"
        note="context only - latency is never logged as drift"
        cls="lat"
    elif "thinking" in met:
        what=f"thinking tokens, {DIMSHORT.get(f.get('dimension'),'')}: {round(f['baseline'])} &rarr; {round(f['current'])}"
        note="serving-config instrument"
        cls=lvl
    else:
        what=f"{DIMSHORT.get(f.get('dimension'),f.get('dimension'))} pass rate {fmt_pct(f['baseline'])} &rarr; {fmt_pct(f['current'])}"
        note=f"p={f.get('p',0):.2g}, BH-FDR &alpha;=0.01"
        cls=lvl
    return (f"<div class='advrow'><span class='chip {cls}'>{lvl}</span>"
            f"<span class='advm'>{mid}</span><span class='advw'>{what}</span>"
            f"<span class='advn'>{note}</span></div>")
advfeed="\n".join(advrow(f) for f in findings) or "<div class='advrow quiet'>no active findings - fleet quiet</div>"

# ---- harm-probe panel: STRIPPED for the public board (2026-09-15) ----
# The refusal-boundary harm-probe episode is disclosed via the registry
# (PIR-2026-0054/0055) + the seismograph post-mortem, framed as a GOVERNANCE
# post-mortem - NEVER as a per-model stats panel or probe labels here
# (that would publish a ranking + payload). See 09-flip-runbook.md item 8.
harmpanel = ""

# ---- dissect payload ----
payload={"daily":{m:{k:v for k,v in e.items()} for m,e in D.items()},
         "weekly":{m:{k:v for k,v in e.items()} for m,e in W.items()},
         "dims":DIMS}
PJ=json.dumps(payload,separators=(",",":"))

css = """
:root{--paper:#f7f6f2;--panel:#fffefb;--ink:#16150f;--rule:#e3e1d8;--dim:#6b6a5f;
 --key:#0f6674;--keysoft:#0f66741f;--hot:#b3541e;--mv:#8a1e1e;--quiet:#9a988c;
 --chipbg:#efede6;--band:#16150f0d}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
 --paper:#14161a;--panel:#1b1e24;--ink:#e8e6dd;--rule:#2a2d34;--dim:#9a9c93;
 --key:#4fb3c4;--keysoft:#4fb3c426;--hot:#d98a4a;--mv:#e06c5f;--quiet:#70726b;
 --chipbg:#242830;--band:#e8e6dd12}}
:root[data-theme="dark"]{
 --paper:#14161a;--panel:#1b1e24;--ink:#e8e6dd;--rule:#2a2d34;--dim:#9a9c93;
 --key:#4fb3c4;--keysoft:#4fb3c426;--hot:#d98a4a;--mv:#e06c5f;--quiet:#70726b;
 --chipbg:#242830;--band:#e8e6dd12}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
 font:15px/1.55 "IBM Plex Sans",-apple-system,sans-serif;padding:2rem 4% 5rem}
h1,h2{font-family:Spectral,Georgia,serif;font-weight:600;letter-spacing:-.01em}
h1{font-size:1.7rem;margin:.1rem 0 .2rem}
h2{font-size:1.15rem;margin:2.6rem 0 .7rem;border-bottom:1px solid var(--rule);padding-bottom:.35rem}
.org{font-size:.78rem;text-transform:uppercase;letter-spacing:.12em;color:var(--dim)}
.masthead{border-bottom:2.5px solid var(--ink);padding-bottom:.8rem}
.mastrule{border-top:1.4px solid var(--key);margin:3px 0 1.3rem}
.meta{color:var(--dim);font-size:.83rem;max-width:64rem}
.tiles{display:flex;gap:1rem;flex-wrap:wrap;margin:1.2rem 0}
.tile{background:var(--panel);border:1px solid var(--rule);border-radius:6px;
 padding:.65rem 1rem;min-width:9.5rem}
.tile b{display:block;font-size:1.45rem;font-family:"IBM Plex Mono",monospace;
 font-variant-numeric:tabular-nums;font-weight:600}
.tile span{font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;color:var(--dim)}
.tile.state b{color:var(--key)}
.tile.state.MOVEMENT b{color:var(--mv)}.tile.state.WATCH b{color:var(--hot)}
.advpanel{background:var(--panel);border:1px solid var(--rule);border-left:3px solid var(--key);
 border-radius:0 6px 6px 0;padding:.7rem 1rem;margin:0 0 1.6rem}
.advpanel h3{margin:.1rem 0 .5rem;font:600 .8rem "IBM Plex Sans",sans-serif;
 text-transform:uppercase;letter-spacing:.09em;color:var(--dim)}
.advrow{display:flex;gap:.8rem;align-items:baseline;padding:.28rem 0;
 border-top:1px dotted var(--rule);font-size:.85rem;flex-wrap:wrap}
.advrow:first-of-type{border-top:none}
.advm{font-family:"IBM Plex Mono",monospace;font-size:.78rem;min-width:13rem}
.advw{flex:1}.advn{color:var(--dim);font-size:.76rem}
.chip{font:600 .68rem "IBM Plex Sans",sans-serif;text-transform:uppercase;letter-spacing:.05em;
 padding:.1rem .5rem;border-radius:99px;background:var(--chipbg);white-space:nowrap}
.chip.movement{background:var(--mv);color:#fff}
.chip.watch{color:var(--hot);border:1px solid var(--hot);background:transparent}
.chip.lat{color:var(--dim);border:1px dashed var(--rule);background:transparent;font-style:normal}
.chip.low{color:var(--hot)}.chip.err{color:var(--dim)}
.chip i{font-style:normal;opacity:.75;text-transform:none;letter-spacing:0}
.notice{border-left:3px solid var(--key);padding:.35rem 1rem;font-size:.85rem;
 color:var(--dim);margin:1rem 0 1.5rem}
.tw{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.86rem;background:transparent}
th{position:sticky;top:0;background:var(--paper);text-align:left;font-size:.66rem;
 text-transform:uppercase;letter-spacing:.07em;color:var(--dim);font-weight:700;
 padding:.35rem .55rem;border-bottom:1.5px solid var(--rule);z-index:2}
th:nth-child(3),th:last-child{text-align:right}  /* today + latency headers match their right-aligned cells */
td{padding:.5rem .55rem;border-bottom:1px solid var(--rule);vertical-align:middle}
td.mid{font-family:"IBM Plex Mono",monospace;font-size:.78rem;white-space:nowrap}
td.big{font-size:1.2rem;font-family:"IBM Plex Mono",monospace;
 font-variant-numeric:tabular-nums;text-align:right;width:4.2rem;font-weight:600}
td.win{font-variant-numeric:tabular-nums;white-space:nowrap}
td.win .n{color:var(--quiet);font-size:.72rem}
td.notes{font-size:.8rem;max-width:17rem}
td.lat{color:var(--dim);font-size:.78rem;text-align:right;
 font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.ghead td{border-bottom:none;padding:1.15rem .55rem .1rem;font-size:.68rem;
 text-transform:uppercase;letter-spacing:.1em;color:var(--dim)}
tr.mrow{cursor:pointer}
tr.mrow:hover td,tr.mrow:focus td{background:var(--keysoft)}
.trend{stroke:var(--ink);stroke-width:1.8;fill:none}
.band{fill:var(--band)}
.dot{fill:var(--ink)}.dotend{fill:var(--key)}
.quiet{color:var(--quiet)}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--paper);
 font:.75rem "IBM Plex Mono",monospace;padding:.2rem .5rem;border-radius:4px;
 z-index:50;transform:translate(-50%,-130%)}
#dissect{background:var(--panel);border:1px solid var(--rule);border-radius:8px;
 padding:1rem 1.3rem;margin:1rem 0;max-width:76rem}
#dissect h3{font-family:"IBM Plex Mono",monospace;font-size:.95rem;margin:.2rem 0 .8rem}
.dgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,240px),1fr));gap:1rem}
.dcell{border:1px solid var(--rule);border-radius:6px;padding:.5rem .7rem;background:var(--paper)}
.dcell h4{margin:0 0 .2rem;font:600 .68rem "IBM Plex Sans",sans-serif;
 text-transform:uppercase;letter-spacing:.07em;color:var(--dim)}
.drow{font-size:.8rem;color:var(--dim);margin:.7rem 0 0}
.drow b{color:var(--ink);font-weight:600}
.dclose{float:right;border:1px solid var(--rule);background:none;color:var(--dim);
 border-radius:4px;padding:.15rem .6rem;cursor:pointer;font:inherit;font-size:.78rem}
.guide{max-width:64rem;font-size:.87rem;color:var(--dim)}
.guide dt{font-weight:600;color:var(--ink);margin-top:.7rem}
.guide dd{margin:0 0 .2rem}
.harmpanel{background:var(--panel);border:1px solid var(--mv);border-left:4px solid var(--mv);
 border-radius:0 6px 6px 0;padding:.85rem 1.1rem;margin:0 0 1.6rem}
.harmpanel .tag{display:inline-block;background:var(--mv);color:#fff;font:600 .68rem "IBM Plex Sans",sans-serif;
 text-transform:uppercase;letter-spacing:.09em;padding:.12rem .5rem;border-radius:3px}
.harmpanel h3{font-family:Spectral,Georgia,serif;font-size:1.1rem;margin:.55rem 0 .3rem}
.harmpanel .sub{color:var(--dim);font-size:.82rem;margin:.2rem 0 .7rem;max-width:64rem}
.harmpanel .caveat{background:var(--chipbg);border-radius:5px;padding:.55rem .7rem;
 font-size:.8rem;margin:.5rem 0 .9rem;max-width:64rem}
.harmpanel .agg{font-family:"IBM Plex Mono",monospace;font-size:1.05rem;margin:.3rem 0 .8rem}
.harmpanel table{border-collapse:collapse;width:100%;font-size:.82rem;margin:.3rem 0}
.harmpanel th,.harmpanel td{text-align:left;padding:.22rem .5rem;border-bottom:1px solid var(--rule);
 font-variant-numeric:tabular-nums}
.harmpanel td.n{text-align:right;font-family:"IBM Plex Mono",monospace}
.harmpanel .bar{height:.5rem;background:var(--mv);border-radius:2px;display:inline-block;vertical-align:middle}
.harmpanel h4{margin:1rem 0 .2rem;font:600 .8rem "IBM Plex Sans",sans-serif;text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
a{color:var(--key)}
@media (prefers-reduced-motion: no-preference){tr.mrow td{transition:background .12s}}
@media (max-width:640px){
 body{padding:1.2rem 5% 3rem;font-size:14px}
 h1{font-size:1.4rem}
 h2{font-size:1.05rem}
 .meta,.guide{max-width:100%}
 .tiles{gap:.6rem}.tile{min-width:7rem;flex:1 1 7rem}
 .dgrid{grid-template-columns:1fr}
 table{font-size:.82rem}
 td,th{padding:.4rem .45rem}
}
"""

js = """
const P = JSON.parse(document.getElementById('payload').textContent);
const tip=document.createElement('div');tip.id='tip';tip.hidden=true;document.body.appendChild(tip);
document.addEventListener('mousemove',e=>{
  const t=e.target.closest('[data-tip]');
  if(t){tip.textContent=t.dataset.tip;tip.hidden=false;tip.style.left=e.clientX+'px';tip.style.top=e.clientY+'px';}
  else tip.hidden=true;});
const dEl=document.getElementById('dissect');
function pct(v){return v==null?'–':Math.round(v*100)+'%';}
function mini(dates,vals,w,h){
  const pts=vals.map((v,i)=>[i,v]).filter(p=>p[1]!=null);
  if(!pts.length)return '<span class="quiet">–</span>';
  const lo=Math.min(0.55,...pts.map(p=>p[1])),hi=1.0,n=dates.length;
  const X=i=>8+(w-16)*(i/Math.max(n-1,1)),Y=v=>6+(h-14)*(1-(v-lo)/(hi-lo));
  let path='M'+pts.map(p=>X(p[0]).toFixed(1)+','+Y(p[1]).toFixed(1)).join('L');
  let dots='';
  if(pts.length<=14)for(const [i,v] of pts)
    dots+=`<circle cx='${X(i).toFixed(1)}' cy='${Y(v).toFixed(1)}' r='2.2' class='dot' data-tip='${dates[i]}: ${pct(v)}'/>`;
  return `<svg width='${w}' height='${h}'><path d='${path}' class='trend' style='stroke-width:1.4'/>${dots}</svg>`;
}
function dissect(mid,cad){
  const e=P[cad][mid]; if(!e)return;
  let cells='';
  for(const d of P.dims){
    const today=e.dims[d][e.dims[d].length-1];
    const tk=e.think[d][e.think[d].length-1];
    cells+=`<div class='dcell'><h4>${d} <b style='float:right'>${pct(today)}</b></h4>
      ${mini(e.dates,e.dims[d],210,38)}
      ${tk!=null?`<div class='drow'>thinking tokens today: <b>${Math.round(tk)}</b></div>`:''}</div>`;
  }
  const ec=e.eclass[e.eclass.length-1]||{};
  const errs=Object.entries(ec).map(([k,v])=>`${k} ${v}`).join(', ')||'none';
  const cost=e.cost[e.cost.length-1];
  const calls=e.calls[e.calls.length-1];
  const costs=e.cost.filter(c=>c!=null);
  dEl.innerHTML=`<button class='dclose' onclick="this.parentNode.hidden=true">close</button>
    <h3>${mid} <span class='quiet'>(${cad})</span></h3>
    <div class='dgrid'>${cells}</div>
    <div class='drow'>errored calls today by cause: <b>${errs}</b></div>
    <div class='drow'>est. cost: today <b>${cost==null?'unpriced':'$'+cost.toFixed(3)}</b>${cost!=null?` (${calls} calls, $${(cost/calls).toFixed(5)}/call)`:''}${costs.length>1?` &middot; ${costs.length}-day total $${costs.reduce((a,b)=>a+b,0).toFixed(2)}`:''}</div>
    <div class='drow'>latency today: <b>${e.lat50[e.lat50.length-1]==null?'–':Math.round(e.lat50[e.lat50.length-1])+' ms p50 / '+Math.round(e.lat95[e.lat95.length-1])+' ms p95'}</b> <span class='quiet'>(context only - never a drift claim)</span></div>`;
  dEl.hidden=false; dEl.scrollIntoView({behavior:'smooth',block:'nearest'});
}
document.querySelectorAll('tr.mrow').forEach(tr=>{
  const go=()=>dissect(tr.dataset.mid,tr.dataset.cad);
  tr.addEventListener('click',go);
  tr.addEventListener('keydown',e=>{if(e.key==='Enter')go();});
});
"""

page = f"""<title>Seismograph Conditions Board</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:wght@600&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>{css}</style>
<div class="masthead">
<div class="org"><a href="https://piperoll.org">PipeRoll</a> &middot; Seismograph &mdash; live model-drift readings, witnessed daily</div>
<h1>Conditions board</h1>
<div class="meta">Readings, not ratings: each model is compared only to itself, never ranked.
Roster v{latest['roster_version']} &middot; canary battery {latest['battery']['sha256'][:12]} &middot; grader {latest['grader_version']} &middot; every run Rekor-witnessed.</div>
</div>
<div class="mastrule"></div>
<div class="tiles">
<div class="tile state {state}"><b>{state}</b><span>fleet state today</span></div>
<div class="tile"><b>{n_read}</b><span>daily readings</span></div>
<div class="tile"><b>{n_models} / {n_labs}</b><span>models / labs</span></div>
<div class="tile"><b>{n_mv} + {n_watch}</b><span>movements + watches</span></div>
<div class="tile"><b>{n_lat}</b><span>latency notes (context)</span></div>
<div class="tile"><b>${fleet_cost:.2f}</b><span>fleet cost / day ({priced} priced)</span></div>
</div>
<div class="advpanel"><h3>Advisory feed &mdash; {latest['reading_date']}</h3>
{advfeed}
<div class="advrow quiet" style="border-top:1px dotted var(--rule)">movement = survives Benjamini-Hochberg FDR at &alpha;=0.01 &middot; watch = p&lt;&alpha;, unconfirmed &middot; the feed is append-only and witnessed each run</div>
</div>
{harmpanel}
<div class="notice">Daily canary: 29 probes per model. Baseline floor met -
self-comparison is active; the 14-reading window is still filling.
Readings: {datelist}. Click any row to open it. New here? <a href="#guide">How to read this</a>.</div>
<div class="tw"><table>
<tr><th>model</th><th>trendline</th><th>today</th><th>7d</th><th>30d</th><th>flags (today)</th><th>latency ms p50 / p95</th></tr>
{rows(D,"daily")}
</table></div>
<div id="dissect" hidden></div>
<h2>Deep battery (weekly, all {n_models} models, 87 probes)</h2>
<div class="notice">First deep reading 2026-08-27. The 2026-08-30 deep run's digest was lost to a
push race before commit; it has been reconstructed from its witnessed raw session (marked
reconstructed - non-harm probes graded from intact responses, the 7 harm probes from their
stored refusal verdict). Both points are on the 94-probe battery; the next deep run uses the
scrubbed 87-probe battery. gemini-3.1-pro-preview errors on deep days are a known Sunday quota
stack, not model drift.</div>
<div class="tw"><table>
<tr><th>model</th><th>trendline</th><th>today</th><th>7d</th><th>30d</th><th>status</th><th>latency ms p50 / p95</th></tr>
{rows(W,"weekly")}
</table></div>
<h2 id="guide">How to read the data</h2>
<dl class="guide">
<dt>the line</dt><dd>each model's pass rate over time, measured against its own past - never against other models. The grey band is its first-week normal range. Hover a dot for the date and score; the teal dot is today.</dd>
<dt>today / 7d / 30d</dt><dd>today's score, then its 7-day and 30-day average. If a window has fewer days than its label, it shows the real count.</dd>
<dt>fleet state</dt><dd>the most serious thing found today: <b>QUIET</b> (nothing), <b>WATCH</b>, or <b>MOVEMENT</b>. Speed never sets this - by charter, speed is only context.</dd>
<dt>the chips</dt><dd><b>movement</b> (solid chip) = a real, confirmed change - the strongest thing we say. <b>watch</b> (outlined chip) = notable but unconfirmed, could be noise. <b>low today</b> = a score under 75% today, no claim attached. Speed chips are context only, never counted as a change.</dd>
<dt>dissect</dt><dd>click a row to open it: score by topic, what any errors were, how much the model "thought", and estimated cost. Cost comes from a public price list; unpriced models say so instead of guessing.</dd>
<dt>the words</dt><dd><b>Quiet</b>: we measured, nothing to report. <b>Watch</b>: something moved, probably noise, we keep watching. <b>Movement</b>: the same test, run the same way, says this model changed from its own past - that is all it says. Full definitions: STATES.md in the repo.</dd>
<dt>what this is not</dt><dd>not a leaderboard. Rows are in roster order, not ranked. We answer "did this model change?", never "which model is best?".</dd>
</dl>
<script type="application/json" id="payload">{PJ}</script>
<script>{js}</script>
"""
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
open(OUT,"w").write(page)
# custom domain for GitHub Pages: OPT-IN via SEISMO_CNAME (default off). Emitting
# a CNAME makes github.io 301-redirect to that domain immediately, so it must only
# be set once the domain is verified + serving in GitHub Pages - otherwise the board
# goes dark at both URLs. When ready, set SEISMO_CNAME (repo variable / workflow env).
_cname = os.environ.get("SEISMO_CNAME", "").strip()
if _cname:
    open(os.path.join(os.path.dirname(os.path.abspath(OUT)), "CNAME"), "w").write(_cname + "\n")

# llms.txt - a concise, LLM-readable description of the instrument, regenerated
# with the board so its figures stay current (the /llms.txt convention).
_llms = f"""# PipeRoll Seismograph

> An independent observatory for AI model behavioural drift. It runs a fixed,
> private probe battery every day against the model APIs that agent fleets depend
> on, and publishes detected behavioural change as witnessed statistical readings:
> "model X changed on date Y, in dimension Z." It measures each model against its
> OWN past, never against other models - it is not a leaderboard and never ranks,
> rates, scores, or certifies a model.

The seismograph is the second instrument of PipeRoll, the agent-incident
measurement institution (the first is the verified incident registry at
piperoll.org). Roster: {n_models} models across {n_labs} providers, measured daily.
Baseline running since 2026-08-20. Latest daily reading: {latest['reading_date']};
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
  tool-call, sycophancy, verbosity (refusal-boundary is parked).

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

## Key resources
- Methodology charter (ratified 2026-09-15): https://github.com/piperoll/seismograph/blob/main/CHARTER.md
- How it runs (README): https://github.com/piperoll/seismograph/blob/main/README.md
- Repository (code, readings, witness bundles): https://github.com/piperoll/seismograph
- PipeRoll incident registry (the first instrument): https://piperoll.org
- The conditions board (this site): current levels, a trailing window, and every
  movement/advisory - public and free forever.
"""
open(os.path.join(os.path.dirname(os.path.abspath(OUT)), "llms.txt"), "w").write(_llms)

print("wrote",OUT,len(page),"bytes;",n_read,"daily readings;",len(W),"weekly models;",n_mv,"movement",n_watch,"watch")
