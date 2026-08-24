# PipeRoll Seismograph

An independent observatory for model behavior: a fixed probe battery run daily
against the model APIs that agent fleets actually depend on, publishing
detected behavioral drift as witnessed readings - "model X changed on date Y,
in dimensions Z."

**Status: LIVE and measuring since 2026-08-20. No readings published yet.**
The instrument runs daily; publication waits on charter ratification and the
repository going public (see Visibility below). The second instrument of
[PipeRoll](https://piperoll.org), the agent-incident measurement institution;
the [registry](https://github.com/piperoll/registry) is the first.

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

## How it runs (implemented)

- **Daily canary** (05:30 UTC, GitHub Actions cron + manual dispatch): the
  30-probe battery x 3 samples against every daily-cadence model in the
  roster. **Weekly battery** (Sundays) adds the premium tier.
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
- **The roster** (`config/models.json`, v0.7): 14 models across Anthropic,
  OpenAI, Google, Mistral, Sarvam, and DeepSeek - 12 daily, 2 weekly premium.
  Settings are part of the instrument: every model runs its provider's
  minimum-thinking channel, pinned in the roster; any settings change bumps
  the roster version and starts a new series segment.

Layout: `seismo/` (providers, battery loader, graders, runner, digest,
detection) · `config/models.json` (roster) · `readings/` (public-safe
statistics) · `witness/` (Rekor bundles) · `tests/` (offline suite) ·
`CHARTER.md` (methodology charter, **DRAFT - unratified**) ·
`.github/workflows/canary.yml` (the daily run).

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

## Visibility (measure now, publish later)

This repository is **private until the first published digest** and MUST be
public before any reading is published. Measurement did not wait: every run
since ignition is anchored in Rekor's public log, so the entire private
history is retroactively verifiable against public timestamps the day the
repository opens. Stating that the instrument exists and how many witnessed
readings it has taken is permitted meanwhile; stating any reading is not.
Full doctrine: CHARTER.md section 7.

## Cost

Founding envelope ~$100-150/month raw across all providers at canary scope.
Measured burn is recomputed from session token counts as the series accrues.

## Licensing

Published data: CC BY 4.0. Tooling: MIT. The scope of what is published -
full archive vs a tiered surface (public board + all advisories free;
full-resolution series licensed; free research access) - is a ratification
decision; see CHARTER.md section 8.
