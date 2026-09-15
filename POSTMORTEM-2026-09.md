# Post-mortem: our own safety-testing traffic tripped a provider policy - and nearly took the instrument down


*This is PipeRoll's own incident. We record it in our own registry as PIR-2026-0054 (and its companion PIR-2026-0055), under the same conflict-of-interest disclosure (constitutional rule 4) we apply to every record touching the people who run PipeRoll. If we ask other operators to disclose their agent failures, the first operator held to that standard is us.*

## What happened

The seismograph measures a roster of frontier and open-weight models across twelve providers every day. One of its seven probe dimensions, `refusal-boundary`, was built to test whether models correctly *refuse* unsafe requests - so, by construction, it contained a small set of deliberately-unsafe prompts spanning prohibited categories (weapons, malware, fraud).

Two design choices turned that into an incident. First, those probes fired against the whole roster on every run, each provider hit on a **single shared key that also carries the instrument's core signal** - drift, latency, availability, capability. Second, there was no separation between that harmful-category traffic and the account the instrument depends on to function. Over roughly eleven days this came to on the order of a couple thousand harmful-category calls across the twelve labs.

On 2026-09-01 one provider's automated abuse detection flagged the traffic and issued a usage-policy notice against the key we use for that provider's models. It was the only provider that gave notice - it is the only one of the twelve that even offers a request-tagging field; the rest enforce silently.

## Why it mattered more than one notice

The harmful traffic and the availability signal shared a key. So an account restriction would not merely stop the probes - it would drop that model from the roster and register in our own data as an outage. **The measurement act was capable of destroying the measurement channel.** And because the provider consoles are reached under one identity, an enforcement action on one could correlate to others. A safety-testing instrument had built a way to attack the very thing it exists to measure.

## What we did

- **Removed every deliberately-unsafe probe** from both batteries and, critically, from the live secrets the runner actually reads - so the change was in force, not just in a file.
- **Set a stable request-identifier** on that provider's calls, so our evaluator traffic is attributable to one controlled source rather than reading as many abusive end users.
- **Scrubbed the private raw archive**: every harmful-probe response had its text removed, while the measurement fact - did the model comply or refuse - was retained for provenance.

During that cleanup we made a **second mistake worth disclosing**: the history rewrite was built from a local copy four days out of date, and the force-push deleted four days of raw sessions from the remote. They were fully recovered - the pipeline happens to write a fallback copy of every run - but the lesson stands: always compare against the remote before any history rewrite. (A third, related failure - briefly pushing the *draft of this very incident* to a public repository - is recorded as PIR-2026-0055.)

## What changed structurally

Refusal-behavior measurement is **parked, not killed**. If we bring it back, it runs as a *separate* instrument on dedicated, disclosed, expendable keys - one per provider, low frequency, walled off so an enforcement action can never touch the baseline availability clock. And the operating doctrine now: **no deliberately-unsafe traffic ever shares a key with a signal we depend on**, and **`git fetch` and diff against the remote before any history rewrite.**

## A note on the numbers we are *not* publishing

We are deliberately not publishing the per-model or per-probe "refusal rates" this episode produced. The grader was an unvalidated keyword detector we judged too crude to trust - crude enough that its output would mislead more than inform, and crude enough to be one of the reasons the instrument is parked. Publishing those figures as if they were findings would be publishing bad data as a model-safety ranking, which is exactly the readings-not-ratings line the whole institution rests on. The honest disclosure is *what we did and why it was wrong*, not a leaderboard built on a measurement we retired.

## What this says about agent operations generally

This is the failure mode the registry exists to catalogue: an autonomous system doing exactly what it was told, with no adversary, producing a consequence its designer did not price in. Here the designer was us. The lesson - that an agent's own outbound traffic is a policy-enforcement surface, and that safety-testing traffic can attack the system doing the testing - is one we would rather learn in public than have others learn quietly.

---
