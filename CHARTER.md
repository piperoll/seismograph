# Seismograph Methodology Charter

**Status: RATIFIED 2026-09-15 by the editor (this signed commit).** Amendments
follow the registry's convention: by PR, dated, never silently. The draft-era
rule is now lifted: readings may be published under this ratified charter, subject
to the repository being public per section 7.

This charter is the seismograph's epistemic contract, separate from the
registry's (verified facts) by design: the seismograph publishes statistical
readings with a stated false-positive posture. The institution-wide rules of
the [PipeRoll constitution](https://piperoll.org/constitution/) - corrections
published never slipped, witnessing, never rate/certify/underwrite - bind this
instrument in full.

## 1. What the instrument publishes

- **Reading**: per-model, per-dimension aggregates from one battery run
  (pass rates, refusal rates, token and latency distributions). Readings
  contain no raw model text and no per-probe detail.
- **Movement**: a change against the rolling baseline that survives
  multiple-comparison correction (Benjamini-Hochberg FDR at alpha = 0.01
  across all comparisons in the check; see section 4).
- **Watch**: nominally significant movement that does not survive correction.
  Published as raw data in digests, never announced.
- **Divergence**: a persistent, statistically significant gap between a model's
  score on the **fixed** battery and its score on fresh **dynamic** probes of
  the same capability (see section 2, two-tier battery). It is the instrument's
  check on its own ruler: a large fixed-over-dynamic gap indicates the fixed
  probes may be memorised, special-cased, or otherwise contaminated, and that
  their drift signal is suspect. The gap is the finding; the reading of it
  (gaming vs contamination vs coincidence) is labelled editorial interpretation
  like any cause attribution, and it also triggers rotation of the fixed
  battery (section 2).
- The instrument never publishes ratings, rankings, grades, scores, or
  fitness-for-purpose claims about any model. Cause attribution ("provider
  changed X") is a human editorial act and is labeled as interpretation.

**Under-alerting is policy.** The weekly digest always publishes raw
movement; alert-grade announcements require movement level, a stable battery
(no rotation inside the comparison window), and editor sign-off.

## 2. The battery

- The probe battery is **private**. Public probes leak into training data and
  invite overfitting; a contaminated battery measures its own fame.
- The battery's **canonical sha256** (structure-level, whitespace-independent)
  is stamped into every reading and witnessed. The series is comparable
  exactly as far as the hash is unchanged.
- **Rotation**: probes are added or retired only at declared rotation points,
  which start a new battery version; readings across versions are never
  compared silently. Retired probes are published after a lag
  (duration: TBD at ratification).
- Battery content spans declared dimensions (structured-output, tool-call,
  instruction-following, refusal-boundary, capability, sycophancy,
  verbosity); per-dimension probe counts are public.

**Two tiers: a fixed ruler and a dynamic control.** The battery has two parts
with two different jobs. Do not conflate them.

- **Tier 1 - the fixed battery** (everything above): frozen, hash-pinned, run
  every cadence. Its job is DRIFT DETECTION - each model compared to itself over
  time - which requires an identical ruler, so it is never varied inside a
  version. This is the longitudinal signal (Movement / Watch).
- **Tier 2 - the dynamic battery**: probes procedurally generated from fixed
  templates with a fresh, **seeded** random parameterisation each run, measuring
  the SAME deterministic-ground-truth properties as Tier 1 (capability,
  structured-output, tool-call, instruction-following - never the
  judgement-shaped dimensions, which have no generatable ground truth). Grading
  stays mechanical. Generation is deterministic code with a witnessed seed and
  is **never LLM-generated**: an LLM generator's own drift would become the
  probe's drift and destroy the reproducibility the whole instrument rests on.
  Tier 2's job is NOT drift - its instances change every run and carry no
  longitudinal probe-level signal. Its job is the **gaming tripwire on Tier 1**:
  per model, the fixed-battery score is compared against the fresh-dynamic score
  for the same skill, and a persistent fixed-over-dynamic gap is a **Divergence**
  finding (section 1) - the signature of a fixed probe being memorised or
  special-cased. The load-bearing quantity is the delta, not either score alone.
- A Divergence is also the **principled trigger to rotate the fixed battery** -
  rotate when the control shows the ruler is compromised, not on a calendar.
- Honest scope: Tier 2 catches gaming that manifests as a fixed-vs-dynamic gap
  (memorisation / special-casing). A model that underperforms BOTH tiers equally
  leaves no gap and is caught only by the unmarked-traffic and low-salience
  defences (section 2a), not here. Dynamic instances carry instance-difficulty
  variance, so the delta needs sufficient samples to clear noise; Tier 2 may run
  at lower frequency than the daily fixed set to bound cost.

## 2a. Evaluation awareness (the measured system may know it is being measured)

- A behavioral observatory must assume the model can try to game the measurement.
  Frontier models increasingly detect evaluation context and can strategically
  alter or hide behaviour: OpenAI's GPT-6 Astra system card (Sep 2026) discloses
  a substantial decrease in chain-of-thought monitorability, demonstrated
  sandbagging ("evade our monitors when strategically underperforming in
  evaluations"), and ~50.6% evaluation-awareness at maximum reasoning effort.
- Three design responses, two of them already load-bearing in this instrument:
  1. **Unmarked, indistinguishable traffic.** The battery is private and probe
     traffic is deliberately unmarked (generic client identity, ordinary account
     signups, no probe-revealing headers) so the model cannot cheaply tell a
     reading from ordinary use. This raises the cost of selective gaming.
  2. **Low-salience, deterministically-gradeable probes preferred.** Weight the
     battery toward dimensions a model cannot sandbag without visibly failing a
     task it has no reason to fail - structured-output conformance, tool-call
     format, latency, mechanical capability - over dimensions whose "right"
     behaviour a model could recognise as an eval and shade (notably
     refusal-boundary, which is also parked for unrelated reasons).
  3. **No claim rests on a gameable dimension alone.** A published movement must
     survive on signals that are costly to fake; a shift seen only in a
     high-salience, judgement-shaped dimension is reported as context, not a
     movement.
- Honest limit, stated in the open: we cannot prove non-detection. Unmarked,
  low-salience measurement raises the cost of gaming; it does not eliminate it.
  A reading is therefore "did this model change against itself under identical,
  low-salience conditions," never "the model's true unconditioned behaviour."

## 3. Measurement

- Model outputs are stochastic even at temperature 0; every probe is sampled
  N times and all statistics are distributional. String-diffing is not
  measurement.
- **Settings are part of the instrument.** Every model runs at settings
  pinned in the versioned roster; the baseline policy is each provider's
  minimum-thinking channel (lowest reasoning effort, zero or minimal
  thinking budget). Effort has no cross-provider unit, and no cross-model
  comparison is ever published, so per-provider mechanisms under one policy
  is the correct uniformity. **Readings describe the pinned configuration
  only** - they are not a claim about model behavior at other settings.
  Changing any setting bumps the roster version and starts a new series
  segment; segments are never compared silently.
- **Scope: model APIs only.** The unit of measurement is model @ provider
  via a stable completion API. Agent products (hosted autonomous agents
  with tasks, tools, and side effects) have no stable probe surface and are
  out of scope for this instrument; their failures belong in the registry.
- **Grading is mechanical** (deterministic code, versioned). If an LLM judge
  is ever introduced it must be an exact-pinned open-weights model, frozen
  for the life of the series, and its introduction is a charter amendment.
- Raw sessions (full outputs) are retained privately for regrading and
  post-incident forensics; grader improvements regrade history and are
  marked by grader_version in readings.
- **The raw session is the witnessed anchor; readings are reproducible
  derivations.** Each run witnesses the raw session's hash and the running
  code commit in the public log at measurement time. A reading is the digest
  of that witnessed raw under a stated grader_version - it can be regenerated,
  and a grader improvement legitimately rewrites it, so the reading file
  itself is a snapshot, not the integrity root. The provenance claim is: "this
  measurement was witnessed on this date, and this reading is its faithful,
  reproducible derivation." Series and advisories, being derived from
  readings, inherit that chain.
- **Identity**: aliases and pinned snapshots are tracked as distinct series.
  Open-weight models are measured as model @ serving provider; that segment
  measures serving fidelity, not weights.
- Interactive (non-batch) calls are used wherever latency or serving-path
  fidelity is part of the measurement.

## 4. Baseline and detection

- Rolling baseline window: 14 readings per cadence; no comparative claim of
  any kind before 7 baseline readings exist ("baseline accruing"). The floor
  applies PER SERIES (model x dimension, and per metric): a model added to
  the roster accrues its own baseline before any claim is made about it.
- Unit of evidence is the probe-day, not the API call: repeat samples of one
  probe are correlated, and counting them as independent trials would
  inflate significance - the anti-conservative failure this instrument must
  never have.
- Pass-rate movement: two-sided two-proportion z-test against the pooled
  baseline at probe-day granularity. Multiple comparisons across the run are
  controlled by Benjamini-Hochberg FDR at alpha, NOT Bonferroni: with ~150
  model x dimension comparisons per run, Bonferroni's alpha/m threshold is
  unreachable by a test on a handful of probes, which would leave the
  instrument structurally unable to ever raise a movement. FDR controls the
  expected false-discovery share among flagged findings - the honest target
  for a many-parallel-tests monitor, and still conservative. "movement" =
  survives FDR; "watch" = nominally significant (p < alpha) but not
  FDR-confirmed. (Detection power also scales with battery depth: a larger
  probe set per dimension is the other half of making movements detectable.)
- Latency movement: threshold on relative p50 shift (watch at 50%,
  movement at 100%) - deliberately crude until the series justifies more.
  **Latency is advisory context, never a drift claim on its own**: the
  series includes the runner venue's network path, and daily percentiles
  above p50 carry small-sample noise (p95 at daily n is indicative; p99 is
  only computed over rolling multi-day windows). Timeouts and truncations
  are excluded from latency statistics and surface in finish-state mix
  instead, so degradation cannot masquerade as speed. A runner-venue change
  is a config event, marked on the series like any roster change.
- Data gaps are findings, not silence: an established series that returns
  no gradable calls, or an established model absent from a reading, raises
  a coverage finding. A detector that reports calm during an outage is
  worse than no detector.
- **Divergence (fixed vs dynamic, section 2 Tier 2)**: for each model and each
  deterministic dimension, the fixed-battery pass rate is compared against the
  same-run dynamic pass rate with a two-proportion test at probe-day
  granularity, under the same Benjamini-Hochberg FDR as movements. A Divergence
  is raised only on a **persistent** fixed-over-dynamic gap - sustained across a
  minimum run count, not a single day - because instance-difficulty variance in
  the dynamic tier makes one-day gaps noisy. Direction matters: only
  fixed-exceeds-dynamic is a contamination/gaming signal; dynamic-exceeds-fixed
  is treated as ordinary instance-difficulty noise, not a finding. A confirmed
  Divergence flags the fixed probe's drift signal as suspect and triggers
  battery rotation (section 2).
- Detection parameters live in code, versioned; changing them is a charter
  amendment, not a tuning knob.
- **Advisories are the instrument's published output.** Movement findings are
  appended to a dated, append-only advisory feed; a movement that later
  reverts stays in the record with its date (corrections-not-slipped applied
  to readings). The feed is public and free (see section 6 tiering).
- **Roster stillness.** A roster change (added model, changed setting) starts
  a new series segment and resets that series' baseline. Between ratifications
  the roster is held stable except to fix an outright-broken model, so
  baselines can accrue; churn defeats the whole comparison.

## 3a. Scope of the channel measured

The unit is model @ provider via a stable completion API, at the pinned
settings. Serving changes a provider makes *at the API* are in scope and are
exactly what the instrument is built to catch. Serving or behavior changes
made in a product harness *above* the API - a coding tool's own request
plumbing, effort-to-parameter mappings applied client-side, prompt scaffolding
- are out of scope: the instrument would correctly show a flat API series
while a harness-layer change altered the product experience. This boundary is
stated so a null reading is never mistaken for "nothing changed anywhere."

## 5. Witnessing

Every published reading is hash-anchored in a public transparency log
(Rekor, following registry practice), together with the battery hash. The
instrument's entire value is that its baselines provably predate the events
they are later cited against; an unwitnessed reading is an anecdote.

## 6. Coverage and funding

- Coverage is exposure-weighted: models are covered in proportion to
  deployed agent authority, not prestige. The roster and its cadences are
  public (config/models.json).
- No provider sees any reading, digest, or alert before the public does.
- No single provider's money, credits, or API access may be load-bearing:
  losing any provider's support must never end coverage of that provider.
  Provider-donated access is disclosed per provider.
- Free API tiers that train on inputs are never used for the private battery.

## 7. Visibility before first publication

Measurement and publication are decoupled (Aug 20 2026): the repository is
private until the first published digest; measurement begins immediately.
Every run is witnessed in the public transparency log from ignition - each
session meta pins the battery hash, roster version, and code commit, so the
full private history is retroactively verifiable against public entries the
day the repository opens. The repository MUST be public before the first
reading is published. Stating that the instrument exists and how many
witnessed readings it has taken is permitted while private; stating any
reading, movement, or finding is not.

## 8. Settled at ratification (2026-09-15)

The draft-era open items are resolved here. Changes after this are charter
amendments: by PR, dated, never silently.

**Publication tiering.** The early-warning function is a public duty and is never
tiered: the conditions board (current levels plus a trailing window) and EVERY
movement, watch, and advisory in the append-only feed are public and free forever.
Licensed: the full-resolution historical series, bulk machine feeds, and any
attested parametric-grade delivery. Academic and research access to the full series
is granted free on request. Every reading remains Rekor-witnessed at measurement
time regardless of tier, so unpublished history stays provable. The registry's
CC BY 4.0 absolutism is untouched; the two instruments have different value
physics. Tiering is fixed here, at the instrument's birth, precisely so it can
never be a rug-pull imposed later.

**Dynamic tier (section 2, Tier 2).** Built and deployed daily. The seeded
procedural generators live in `seismo/dynamic.py` (generator version pinned) and
the Divergence detector in `seismo/divergence.py`: a directional fixed-over-dynamic
gap, tested at probe-day granularity with a two-proportion test under
Benjamini-Hochberg FDR at the same alpha as section 4, and a persistence floor
equal to the baseline minimum. Parameters are as pinned in code; changing them is
an amendment. Anti-gaming now rests on section 2a and this tripwire together.

**Retired-probe publication lag: 90 days.** A probe retired at a rotation point is
published complete - prompt, parameters, grader - 90 days after retirement, so a
historical reading eventually becomes fully auditable without exposing a live
battery.

**Digest surface.** The public conditions board and the append-only advisory feed
are the published digest, continuously, rather than a separate periodic artifact.
A dated summary note is optional editorial, not required.

**Alerting and sign-off.** Movements append to the public advisory feed
automatically; the feed is the instrument's product. Calling a movement out as a
named, alert-grade advisory requires editor sign-off - a signed commit by the
editor - consistent with the under-alerting policy of sections 1 and 4.
Operational failure alerts (a missed run, a model gone dark) go to a private
channel, never the public feed.

**Provider terms-of-service.** Each provider's terms for sustained automated
evaluation, including whether any tier trains on API inputs, are tracked per
provider; a tier that trains on inputs is never used for the battery (section 6),
promotional credits included. Reviewed at each ratification sitting.

**Sample sizes and exposure weighting.** As pinned per battery in the private
battery files and in the versioned roster; the current roster is the initial
exposure weighting. Sample or roster changes are marked series events and bump the
roster version.

**Settings-sweep calibration.** An occasional (roughly quarterly) run across
temperature and effort levels, for models that accept them, is published as a dated
calibration note, never as a series. Daily cadence stays single-channel at the
pinned settings.

**Dual-channel experiment.** Not adopted. May be adopted later and declared as an
experiment if so; there is no standing default-settings series today.
