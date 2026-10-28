# Post-mortem: raw sessions sat in this public repository's workflow artifacts for six weeks

*This is PipeRoll's own incident, recorded in our registry as [PIR-2026-0111](https://piperoll.org/pir/2026-0111/). PipeRoll is run by a single human operator, its founder, working with a Claude agent (Anthropic) that writes and operates this instrument. Anthropic models are on the measured roster, so this is a conflict-of-interest disclosure under constitutional rule 4. The account was reviewed by an OpenAI Codex agent, whose lab's models are also on the roster. It is our second confidentiality failure, after [PIR-2026-0055](https://piperoll.org/pir/2026-0055/).*

All times are UTC.

## What happened

From its first version on 2026-08-20, the canary workflow ended every run by uploading the run's raw session directory as a GitHub Actions artifact, `raw-session-<run id>`, kept for 90 days. The step ran unconditionally (`if: always()`). The agent wrote it while this repository was private, as a stopgap until raw sessions had a private home. The private archive, `seismograph-raw`, started receiving sessions on 2026-08-31, but the stopgap was never retired.

On 2026-09-01, during the cleanup recorded as [PIR-2026-0054](https://piperoll.org/pir/2026-0054/), every raw-session artifact that existed then was deleted. They held unscrubbed responses to the deliberately-unsafe probes being removed that day. The upload step itself stayed in place, so new artifacts kept accumulating from the next run on.

On 2026-09-15 this repository became public at launch. GitHub lets signed-in users download the workflow artifacts of a public repository. Every artifact still within its 90 days became downloadable, and each later run added another, until 2026-10-28.

The pre-launch audit checked this repository's git history and found no battery files, raw sessions, operator notes or keys in what it inspected. It did not cover Actions artifacts, which are not part of git history.

## What was exposed

The exposed artifacts came from runs after the 2026-09-01 cleanup, for every run whose upload step produced an artifact. They held:

- **The models' responses to the probes**, one record per probe, keyed by probe id, with token counts, latency and finish state. The prompts themselves are not stored in raw sessions. But responses often restate or work through the task, so the content of the daily, weekly deep and decision batteries could be partly reconstructed from them.
- **Refusal-boundary responses in some runs.** By then the refusal-boundary dimension held only probes that test over-refusal of benign requests; the deliberately-unsafe probes were gone. A scrub step removing refusal-boundary response text before upload was added on 2026-09-23. Before that, those responses were uploaded as they were. After it, a run that failed before reaching the scrub step could still upload them.
- **Run metadata**: roster, versions, battery name and hash, and the dynamic tier's seed. None of it carries fixed-battery content. The dynamic tier is generated fresh each run from public code and a witnessed seed, so its seed is disclosed by design.

We have no evidence that would tell us whether anyone downloaded these artifacts: no artifact download record is available to us, and this organisation has no audit log. Downloading needed a signed-in GitHub account, which is no barrier to a determined reader. We treat the content as exposed.

## How it was found and fixed

The operating agent noticed the artifact step on 2026-10-26 while reviewing the workflow for unrelated work. It reported the step to the operator and asked before deleting anything, because deleting artifacts cannot be undone. Its report listed the problem among routine follow-ups rather than flagging it as urgent. On 2026-10-28 the operator approved, and that day:

- the 86 raw-session artifacts then listed were deleted, and the listing was checked again: no artifact whose name starts with `raw-session-` remains;
- all 189 session names witnessed in this repository were matched to files in the private archive, and none was missing. That was a filename coverage check, not a byte-for-byte comparison with the deleted artifacts, and it does not cover sessions from failed runs that never reached witnessing;
- the upload was replaced ([#95](https://github.com/piperoll/seismograph/pull/95)). Raw sessions now go only to the private archive, pushed even when a run fails, with each archived copy scrubbed. A run keeps a backup artifact only if it failed or the archive push failed. That backup is encrypted, kept for 30 days, and not kept at all if the encryption secret is missing. An open follow-up ([#96](https://github.com/piperoll/seismograph/pull/96)) proposes scrubbing the backup before encryption as well.

We also checked the rest of what this repository serves: git history on all branches, the remaining artifacts (board site, Pages deploy, one repeatability report of digested readings), caches, releases and recent run logs. We found no raw response text in any of them.

Two days passed between detection and deletion. Asking before an irreversible step was right, but an active exposure should have been raised as urgent the moment it was found.

## What changes

- **A public repository's Actions artifacts count as publication.** Anything uploaded there is treated like a commit to `main`. Raw sessions, battery material and unscrubbed text never go to an artifact in plain form.
- **Every visibility change audits everything the host serves**, not only git history: artifacts, caches, Pages deploys, releases, logs, and pull-request refs (the lesson of 0055).
- **A stopgap is written with its end condition in code**, so it switches off when the condition is met, not when someone remembers.
- **The battery is treated as possibly exposed.** Replacement probes will be built and run in parallel before the current ones retire, under the charter's rotation rule, so the baseline is not broken by a sudden swap. Until then we do not claim the battery's secrecy for any content run between 2026-09-01 and 2026-10-28.

## What we are not publishing

No probe text, response text or per-probe detail appears here, on the same grounds as every other seismograph statement: describing the exposed material in detail would complete the exposure.
