# Offload a useful artifact and distinguish rate limits from quota

The resilient two-task cohort used source `4f794d7` and the same installed CLI in
both arms. Ledger completed at 100/100 in both: Solo 647.438 seconds, Flow 631.282
seconds, 14 physical requests each. Flow used 13 XHigh requests plus one High
review request. That worker returned 479 output tokens; the useful critical-path
work still mostly remained with the chief. The observed 2.5% elapsed reduction is
below the preregistered 10% threshold and establishes no stable or causal gain.

ZIP Flow stopped on its first upstream HTTP 429. Its historical error body was
not retained, so that exact response cannot now be called a temporary limit or
exhausted quota. Solo completed normally. These outcomes remain in the failed
cohort, without replacing either arm or pooling it into a later positive result.

## One independent artifact instead of generic review only

Where the user supplies a stable public CLI contract, the initial context-only
reviewer/high may return a standard-library black-box unittest proposal, at most
150 lines with at least five meaningful tests through that public interface, using
the required task language/framework (standard-library unittest for these Python tasks).
It reads no files, uses no tools, writes nothing and provides no production code.
The chief writes production, included examples and README concurrently, reviews
and integrates the proposed test module once, then tests the actual CLI. It does
not independently produce a duplicate version of that assigned module.

An untested proposal is not acceptance evidence. Critical numerical, parsing,
security and atomic boundaries stay under chief ownership and verification. If
the public interface is not yet stable, retain the bounded risk-review fallback.
Parent permissions, supported role settings and one-writer ownership are preserved.
The context-only reviewer's documented shell capability is disabled; discovery and
other worker roles keep their existing capabilities. No unsupported role-level
permission or delegation override is introduced.
This scheduling change has to earn its own measured result; it promises no speedup.

## Cautious HTTP 429 recovery

Recovery remains opt-in, one native HTTP resend maximum, stream retries zero.
Every admitted request is still stateless and reserves the shared physical-attempt
budget. In recovery mode inspect only complete JSON error bodies up to 4096 bytes,
with identity encoding, strict UTF-8/JSON and duplicate-key rejection. Read through
a bounded `read1` path; register the nested HTTPError socket for cancellation and
close it before cooldown. Persist fixed classifications and numeric timings only,
never provider messages, raw bodies or raw headers.

Only explicitly recognized temporary-rate type/code pairs may be retried. Known
quota/billing/usage-limit errors and unknown responses remain nonretryable. An
account-level usage percentage does not identify the native request's rate bucket.

Honor a valid Retry-After minimum, expressed as integer seconds or an HTTP date,
and add bounded jitter. Missing headers use bounded fallback backoff; invalid or
ambiguous headers defer. Valid delays above 60 seconds or the remaining task budget
also defer: never clamp the server delay and then retry earlier. Apply the same
valid-delay rule to selected transient server errors. Waits check cancellation and
the shared deadline, and are included in the existing measured request duration.
Inspection and cooldown reserve/replay nothing; the native resend is a fresh POST
that consumes another slot out of the original 80.

## Prospective stop condition

After unit and current-CLI synthetic verification and a real integration prerequisite,
freeze one new two-task cohort using these changes. Both arms retain the literal
old tasks, graders, strict 100/100, Sol XHigh, 1500 seconds and 80 physical attempts.
Neutral recovery settings are identical. Each task must complete and be accepted in
both arms, with Flow quality no lower and a successful-time ratio at least 1.10.
Keep timed generation quiet: finish tooling and independent grading between pairs,
do not run additional modeling experiments while a pair is timed. Keep all earlier
negative data. Run each new pair once; no unchanged retry-until-win and no further
candidate ladder in this bounded follow-up. Report a failed primary condition honestly.

[Rate-limit handling](https://developers.openai.com/api/docs/guides/rate-limits),
[Retry-After semantics](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after),
[HTTPError response bodies](https://docs.python.org/3/library/urllib.error.html#urllib.error.HTTPError),
[supported custom-agent capabilities](https://learn.chatgpt.com/docs/agent-configuration/subagents).

## Outcome and default-policy rollback

The one allowed follow-up completed both native arms for both tasks. Ledger was
599.609/719.281 seconds and 13/23 physical attempts (Solo/Flow); ZIP was
925.687/1207.984 seconds and 15/23 attempts. The fixed speed objective failed on
both tasks. The Ledger audit records two worker proposals integrated in separate
chief writes, a public-test failure and repair, and more chief context rather than
less. Counts alone do not assign every second to an orchestration decision.

Do not promote the test-code proposal policy. Restore the active balanced
context-only risk-review contract from source `4f794d7`; preserve the tested
proposal variant exactly in frozen runtime 13 and its immutable results. Retain
the independently verified transport diagnostics and cautious rate-limit recovery,
with their existing opt-in/default-off boundary. The context-only reviewer's
supported shell capability remains disabled. Ordinary auto-routing still chooses
one agent when independent work has not been declared. No universal, statistical
or 10% speedup is claimed for this release.
