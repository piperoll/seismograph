# Quiet, Watch, Movement - the instrument's vocabulary

The seismograph speaks in exactly three words. This document defines them,
states what each obligates the instrument to have done before using it, and -
just as binding - what none of them mean. The definitions restate CHARTER.md
(sections 1 and 4) in reader-facing form; where wording differs, the charter
governs.

## The three states

**QUIET** - the instrument compared every established series against its own
baseline today and found nothing to say. Quiet is a *result*, not an absence:
it is only reported after a full reading graded and every comparison ran. A
day with no reading is a **gap**, never quiet - gaps raise coverage findings
(a detector that reports calm during an outage is worse than no detector).

**WATCH** - a change that is nominally significant (p < 0.01 on the series'
own test) but does not survive false-discovery correction across the ~150
comparisons the run makes. A watch is published as raw data and carried in
the advisory feed, but it is never announced and never a claim. Most watches
are expected to be noise; that is what "does not survive correction" means.
A watch asks the *instrument* to keep looking. It asks the reader for
nothing.

**MOVEMENT** - a change that survives Benjamini-Hochberg FDR at alpha = 0.01.
This is the strongest claim the instrument ever makes, and the whole claim
is: *this model, measured the same way on the same battery, is behaving
differently than its own recent past.* Direction is reported but not judged -
a movement can be an improvement. Alert-grade announcement additionally
requires a stable battery inside the comparison window and editor sign-off
(under-alerting is policy).

The **fleet state** shown on the board headline is the strongest active
non-latency finding level today: MOVEMENT if any core movement is active,
else WATCH if any core watch, else QUIET.

## What must be true before either flag can exist

- **A floor**: no comparative claim of any kind before 7 baseline readings
  exist for that series (model x dimension x metric). Below the floor the
  verdict is "baseline accruing" - the instrument stays silent while the
  ruler is short. The rolling baseline window is 14 readings.
- **Honest units**: the unit of evidence is the probe-day, not the API call;
  repeat samples of one probe are correlated and are never counted as
  independent trials.
- **A stable ruler**: a roster or battery change starts a new series segment
  and resets that baseline. Series are isolated by battery hash.
- **Versioned parameters**: thresholds and alpha live in code; changing them
  is a charter amendment, not a tuning knob.

## What none of the states mean

- **Not a rating.** No state says anything about which model is better. The
  instrument compares each model only to itself; rows sit in roster order;
  there is no leaderboard and never will be (constitutional rule 7).
- **Movement is not "the model got worse."** It is "the model changed."
  Cause attribution - "the provider changed X" - is a human editorial act
  and is always labeled as interpretation, never emitted by the detector.
- **Quiet is not safety.** The battery samples seven behavioral dimensions
  with a finite probe set through one access channel (the public API). Quiet
  means *this instrument* saw nothing; absence of evidence here is not
  evidence of absence (the registry's completeness rule, applied to a
  different organ).
- **A watch is not a finding-in-waiting.** Watches are expected to be mostly
  noise. Treating every watch as news would make the feed unreadable and the
  instrument untrustworthy; that is why announcement requires movement level
  plus editorial sign-off.

## Special finding classes

- **Latency** is advisory *context*, never a drift claim and never the
  headline: the series includes the runner venue's network path, so a
  latency shift alone cannot distinguish the model's serving stack from the
  road to it. Latency findings use crude relative-shift thresholds (watch at
  +/-50% of baseline median p50, movement at +/-100%), are excluded from the
  permanent advisory log, and never set the fleet state - whatever the
  statistics say.
- **Thinking-token levels** are a serving-configuration instrument: a silent
  effort or routing remap shows here first (thresholds: watch at 50%
  relative shift in a dimension's mean, movement at 100%, including
  appeared-from-zero). These are core findings and can headline.
- **Coverage** findings fire when an established series returns no gradable
  calls or an established model is absent from a reading. Data gaps are
  findings, not silence.

## Lifecycle of a finding

1. A series crosses its 7-reading floor and becomes comparable.
2. A reading lands; every established series is tested against its pooled
   baseline; BH-FDR runs across the whole run's comparisons.
3. Findings surface as watch or movement in that reading's advisory set;
   movements append to the dated, append-only advisory feed, which is
   committed and witnessed with the run.
4. A movement that later reverts **stays in the record with its date** -
   corrections-not-slipped applies to readings too. The feed is history,
   not status.
5. A roster or battery change closes the segment; the next segment accrues
   its own baseline from scratch.

## One-line summary

Quiet: we measured; nothing to say. Watch: the needle twitched; probably
noise; we keep looking. Movement: the same ruler, applied the same way,
says this model changed against itself - and that is all it says.
