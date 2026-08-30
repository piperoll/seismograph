# Seismograph Methodology Charter

**Status: DRAFT - not ratified. No reading is published under a draft
charter.** Ratification is a signed commit by the editor changing this line;
amendments after ratification follow the registry's convention: by PR, dated,
never silently.

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

## 8. Open at ratification (TBD)

- Retired-probe publication lag.
- Weekly digest format and publication surface.
- Alert channel and editor sign-off procedure.
- Per-provider terms-of-service review for sustained automated evaluation
  (includes the credit-tier train-on-inputs check per provider; a tier that
  trains on API inputs is never used for the private battery, per rule in
  section 6 - promotional credits do not bypass this).
- Sample sizes per probe per cadence (cost-accuracy trade), and the model
  roster's initial exposure weighting.
- **Settings-sweep calibration**: an occasional (roughly quarterly) run of
  the battery across temperature / effort levels for models that accept
  them, published as a dated calibration note, never as a series. Daily
  cadence stays single-channel at the pinned settings.
- **Dual-channel experiment**: optionally, one model carrying a second
  standing series at provider-default settings, to measure the gap between
  the pinned channel and the default experience. Declared as an experiment
  if adopted.
- **Publication tiering (added Aug 24)**: whether "published readings" means
  the full-resolution archive or a tiered surface. Proposal under
  consideration: the conditions board (current levels, a trailing window)
  and EVERY movement/advisory are public and free forever - the
  early-warning function is a public duty and is never tiered; the
  full-resolution historical series, bulk machine feeds, and attested
  parametric-grade delivery are licensed; academic research access is
  granted free on request. Every reading remains Rekor-witnessed at
  measurement time regardless of tier, so unpublished history stays
  provable. This must be settled BEFORE the first public reading - tiering
  announced at birth is a business model, tiering imposed later is a
  rug-pull. (The registry's CC BY absolutism is untouched by this item;
  the two instruments have different value physics.)
