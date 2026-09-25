# PipeRoll Seismograph

An independent observatory for model behavior: a fixed probe battery run daily
against the model APIs that agent fleets actually depend on, publishing
detected behavioral drift as witnessed readings - "model X changed on date Y,
in dimensions Z."

**Status: LIVE, measuring since 2026-08-20, and PUBLISHING.** Charter ratified
2026-09-15; the repository is public and readings publish under it. The second
instrument of [PipeRoll](https://piperoll.org), the agent-incident measurement
institution; the [registry](https://github.com/piperoll/registry) is the first.

## Why this exists

Providers ship silent behavioral changes; downstream agents discover them by
breaking. Six of the registry's records are model-update regressions, every one
with fleet-wide blast radius. This failure class is provider-side, unannounced,
and correlated across every deployment pinned to the model.

A day not measured is a baseline gone forever. When the next fleet regression
hits, only an entity already recording can say when it drifted and what
changed. This instrument must predate its justifying event - the same birth
certificate as the registry.

## How it runs (implemented)

- **Daily canary** (08:30 UTC, GitHub Actions cron + manual dispatch): the
  29-probe canary battery against every daily-cadence model in the roster - a
  fast, shallow tripwire. **Weekly deep battery** (Sundays): an 87-probe battery
  against ALL models, giving per-dimension statistical power and, in the
  capability dimension, verifiable-answer probes (math, logic, unambiguous
  facts) that catch reasoning-quality drift mechanically - the proxy for
  semantic grading without an LLM judge. The fixed batteries stay frozen so
  their baselines accrue undisturbed.
- **Two tiers - a fixed ruler and a dynamic control.** Tier 1 is the fixed
  battery above: identical probes every run, so a model's change against its
  own past is drift. Tier 2 runs alongside it - a *seeded, procedurally
  generated* battery whose task families are fixed but whose concrete instances
  are new every run (arithmetic, counting, format-conformance, tool-call shape),
  never LLM-generated and graded deterministically from the seed. A model cannot
  memorise or pre-answer probes that do not exist until the run starts. A
  persistent gap where a model scores well on the fixed battery but worse on the
  same-capability fresh probes is a **Divergence** finding - the tripwire for a
  score inflated by contamination or evaluation-gaming rather than capability.
  This is the concrete answer to the frontier's growing eval-gaming concern:
  more capable models are better at recognising and shading tests.
- **Pipeline per run**: restore the private battery from a secret (hash-checked
  on load) -> `seismo.run` collects raw responses (threaded, probe-major
  interleave so no provider is hammered contiguously; one bad response costs
  one record, never the session) -> `seismo.digest` reduces the session to a
  statistics-only reading -> the session meta and the reading are signed
  keyless (cosign) into **Rekor** -> reading + witness bundles are committed
  here; the raw session is pushed to a separate, permanently private archive.
- **Every reading pins its full provenance**: battery sha256, roster version,
  runner version, grader version, and the git commit of the running code. A
  reading is a self-describing, citable document.
- **The roster** (`config/models.json`, v0.19): 28 models across 12 labs -
  Anthropic, OpenAI, Google, xAI, DeepSeek, Moonshot, Mistral, Alibaba, Zhipu,
  Meta, MiniMax, and Sarvam - 21 daily, 7 weekly. Settings are part of the
  instrument: every model runs its provider's minimum-thinking channel, pinned
  in the roster; any settings change bumps the roster version and starts a new
  series segment.

Layout: `seismo/` (providers, battery loader, procedural generators, graders,
runner, digest, drift + divergence detection) · `config/models.json` (roster) ·
`readings/` (public-safe statistics; `-dynamic` files are the Tier 2 series) ·
`series.json` / `advisories.json` / `divergence.json` (derived board, movement
feed, fixed-vs-dynamic gaps) · `witness/` (Rekor bundles) · `tests/` (offline
suite) · `CHARTER.md` (methodology charter, **ratified 2026-09-15**) ·
`.github/workflows/canary.yml` (the daily run) · `heartbeat.yml` (coverage watch).

Not in this repository, by construction: the probe battery (private; only its
sha256 is public), API keys (Actions secrets), raw model outputs (separate
private archive - outputs can echo probes, so raw sessions are never
publishable, even after probe rotation).

## Design decisions (settled Aug 2026, now binding via CHARTER.md)

1. **Readings, not ratings.** The seismograph publishes measurements with
   error bars. It never grades, ranks, scores, or certifies a model, and no
   public surface ever orders models by performance. This is the registry
   constitution's rule 7 carried over, and it is the structural defense
   against ratings-shopping capture: an opinion can be negotiated, a
   witnessed reading cannot.
2. **Tamper evidence is the product.** Every run is witnessed in Rekor at
   measurement time. The battery stays private; its sha256 is committed
   publicly, proving the series ran unchanged without revealing it. Probes
   rotate at declared points; retired probes are published complete (prompt,
   params, grader config) after a lag, so every historical reading eventually
   becomes fully auditable.
3. **Statistics, not string diffs.** Outputs are stochastic even at
   temperature 0; each probe is sampled N times and the unit of evidence is
   the probe-day. Drift is a distribution shift against a rolling baseline
   with multiple-comparison correction. Under-alerting is policy: digests
   always publish raw movement, alert-grade announcements require editor
   sign-off.
4. **Exposure-weighted coverage.** Models are covered in proportion to
   deployed agent authority, not prestige. Aliases and pinned snapshots are
   distinct series - drift behind a pinned version string is a headline
   finding.
5. **Open weights are measured as model @ provider.** Frozen weights do not
   drift; serving does. That segment measures serving fidelity, labeled as
   such.
6. **The frozen ruler.** Grading is mechanical - deterministic, versioned
   code, public in this repository. If an LLM judge is ever introduced it
   must be an exact-pinned open-weights model, frozen for the life of the
   series; its introduction is a charter amendment. Grader improvements
   regrade history from the raw archive and are marked by grader_version.
7. **Funding rules.** No pre-publication preview for providers, ever. No
   single provider's money or credits may be load-bearing. All
   provider-donated API access is disclosed per provider. Free tiers that
   train on inputs are never used for the battery (contamination), and
   promotional credits do not bypass that rule.
8. **Unmarked traffic.** Providers are not told which accounts carry the
   battery, so readings describe the service as ordinarily delivered.
   Methodology is public; sampling identity is not - the mystery-shopper
   posture standard for instruments of this class.
9. **Separate charters, one institution.** The registry's contract is
   verified facts; the seismograph's is statistical readings with a stated
   false-positive posture. A seismograph alert becomes registry evidence only
   when damage materializes and passes normal record verification.

## What a serving-configuration change looks like here

Providers routinely run server-side serving experiments - quantization,
routing, reasoning-effort semantics - usually without notice, and public
disputes about them are otherwise settled by anecdote. In this instrument,
that class surfaces mechanically: the battery runs a pinned minimum-thinking
channel, so a silent change to effort semantics appears as a level shift in
per-dimension thinking-token counts (published in every reading), corroborated
by latency and output-token distributions, before any pass rate moves. The
detector watches these series like any other: a relative shift against the
rolling baseline raises a watch or movement finding, and thinking appearing at
all on a previously zero-thinking channel is flagged as its own anomaly. Scope
honesty: readings cover the model API channel only; serving changes made in a
product harness above the API (a coding tool's own plumbing) are out of scope
for this instrument.

## Visibility

The measurement clock started 2026-08-20; the repository opened and the first
readings published on 2026-09-15, under the ratified charter. Every run since
ignition was anchored in Rekor's public log, so the entire pre-publication
history is retroactively verifiable against public timestamps - the baselines
provably predate the events they are later cited against, which is the whole
point. Full doctrine: CHARTER.md section 7.

## Incident disclosure

We hold ourselves to the registry's standard. The seismograph's own governance
incident - a refusal-boundary probe set that drew a provider usage-policy notice,
and a data-loss during its cleanup - is disclosed in
[POSTMORTEM-2026-09.md](POSTMORTEM-2026-09.md) and recorded in the registry as
PIR-2026-0054 and PIR-2026-0055. If we ask other operators to disclose their agent
failures, the first held to that standard is us.

## Cost

Founding envelope was ~$100-150/month at single-battery canary scope; the daily
Tier 2 run and the expanded roster roughly double that. Measured burn is
recomputed from session token counts as the series accrues, never estimated.

## Licensing

Published data: CC BY 4.0. Tooling: MIT. The scope of what is published -
full archive vs a tiered surface (public board + all advisories free;
full-resolution series licensed; free research access) - is a ratification
decision; see CHARTER.md section 8.
