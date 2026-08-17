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
  multiple-comparison correction (Bonferroni at alpha = 0.01 across all
  comparisons in the check).
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
- **Grading is mechanical** (deterministic code, versioned). If an LLM judge
  is ever introduced it must be an exact-pinned open-weights model, frozen
  for the life of the series, and its introduction is a charter amendment.
- Raw sessions (full outputs) are retained privately for regrading and
  post-incident forensics; grader improvements regrade history and are
  marked by grader_version in readings.
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
  baseline at probe-day granularity, Bonferroni-corrected across all
  comparisons in the run.
- Latency movement: threshold on relative p50 shift (watch at 50%,
  movement at 100%) - deliberately crude until the series justifies more.
- Data gaps are findings, not silence: an established series that returns
  no gradable calls, or an established model absent from a reading, raises
  a coverage finding. A detector that reports calm during an outage is
  worse than no detector.
- Detection parameters live in code, versioned; changing them is a charter
  amendment, not a tuning knob.

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

## 7. Open at ratification (TBD)

- Retired-probe publication lag.
- Weekly digest format and publication surface.
- Alert channel and editor sign-off procedure.
- Per-provider terms-of-service review for sustained automated evaluation.
- Sample sizes per probe per cadence (cost-accuracy trade), and the model
  roster's initial exposure weighting.
