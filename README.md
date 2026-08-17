# PipeRoll Seismograph

An independent observatory for model behavior: a fixed evaluation battery run
daily against the model APIs that agent fleets actually depend on, publishing
detected behavioral drift as witnessed readings - "model X changed on date Y,
in dimensions Z."

**Status: pre-launch, design phase.** No readings published yet. The second
instrument of [PipeRoll](https://piperoll.org), the agent-incident measurement
institution; the [registry](https://github.com/piperoll/registry) is the first.

## Why this exists

Providers ship silent behavioral changes; downstream agents discover them by
breaking. Six of the registry's first 46 records are model-update regressions,
every one with fleet-wide blast radius (PIR-2026-0004, 0022, 0025, 0029, 0033,
0034). This failure class is provider-side, unannounced, and correlated across
every deployment pinned to the model.

A day not measured is a baseline gone forever. When the next fleet regression
hits, only an entity already recording can say when it drifted and what
changed. This instrument must predate its justifying event - the same birth
certificate as the registry.

## Design decisions (settled, Aug 2026)

These were settled in the founding design discussion and bind the build:

1. **Readings, not ratings.** The seismograph publishes measurements with
   error bars ("refusal rate on battery segment C moved 4.2 points on date D,
   witnessed"). It never grades, ranks, scores, or certifies a model. This is
   the registry constitution's rule 7 carried over, and it is the structural
   defense against ratings-shopping capture: an opinion can be negotiated, a
   witnessed reading cannot.
2. **Tamper evidence is the product.** The entire value is being able to prove
   the measurement predates the event. Every run is witnessed (Rekor,
   following the registry's practice). The probe battery stays private, but
   its sha256 is committed publicly - proving the battery unchanged across the
   series without revealing it. Probes rotate on schedule; retired probes are
   published with a lag.
3. **Statistics, not string diffs.** Model outputs are stochastic even at
   temperature 0. Each probe is sampled N times; drift is a distribution shift
   against a rolling baseline, with change-point detection and
   multiple-comparison correction. False alarms are the death of the
   instrument: the weekly digest always publishes raw movement, alerts fire
   only at high confidence. Under-alerting is policy.
4. **Exposure-weighted coverage.** Models are covered in proportion to
   deployed agent authority, not prestige. Workhorse and cheap tiers (where
   fleets actually run) get daily coverage; premium tiers get the weekly
   battery. Aliases and pinned snapshots are both measured - drift behind a
   pinned version string is a headline finding.
5. **Open weights are measured as model @ provider.** Frozen weights do not
   drift; serving does (quantization, sampling, stack). For that segment the
   instrument measures serving fidelity, labeled as such.
6. **The frozen ruler.** All grading uses a pinned open-weights judge - exact
   weights, exact version, frozen for the life of the series and rerunnable by
   anyone. A closed-model judge drifts under you; a ruler that stretches
   measures nothing.
7. **Funding rules.** No pre-publication preview for providers, ever. No
   single provider's money or credits may be load-bearing - losing any
   provider's support must never silence coverage of that provider. All
   provider-donated API access is disclosed per provider. Subscriber-side
   credibility comes before issuer-side money. Free API tiers that train on
   inputs are unusable for the private battery (contamination).
8. **Separate charters, one institution.** The registry's contract is
   verified facts; the seismograph's is statistical readings with a stated
   false-positive rate. A seismograph alert becomes registry evidence only
   when damage materializes and passes normal record verification, like any
   external source.

## Architecture sketch

- **Daily canary**: ~30 highest-signal probes, small sample count, workhorse
  models, interactive API (serving-path-faithful). Cheap.
- **Weekly deep battery**: full probe set, larger samples, all covered models,
  batch APIs. An anomalous canary escalates the deep battery to same-day.
- **Battery dimensions** (seeded from the registry's regression records):
  tone/sycophancy, serving-stack quality, deprecation and format breaks,
  safety-filter boundary, instruction-following under pressure, guardrail
  drift, tool-call reliability, structured-output adherence, latency and
  token distributions.
- **Cost envelope**: roughly $120-150/month raw at founding scope, before any
  research credits.

## What is not decided yet

The methodology charter - probe design, baseline windows, alert thresholds,
rotation cadence, the exact model roster - is unwritten. No reading is
published before the charter is.

## Licensing

Readings and published data: CC BY 4.0. Tooling: MIT. Same terms as the
registry.
