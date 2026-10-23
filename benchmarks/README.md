# Benchmark records

[Русский](README.ru.md) · [Protocol and limitations](../docs/benchmarking.md) · [Case02 results](case02/results.json)

Sanitized records distinguish execution status, artifact acceptance and integration evidence. Case02 requested `gpt-6.1-sol`/`xhigh`, running A/B concurrently, then C/D.

| Case02 arm | Score /100 | Total arm seconds | Execution status | Artifact accepted |
|---|---:|---:|---|---|
| A: solo | 95 | 1200.937 | `timed_out` | Yes |
| B: requested full flow | 97 | 1201.562 | `timed_out` | Yes |
| C: no inspired probes | 95 | 1040.469 | `completed_unverified` | Yes |
| D: no Mercury | 96 | 1201.109 | `timed_out` | Yes |

Artifact acceptance followed independent checks/review, including 4D geometry; process status remains unchanged. Deadline-censored durations are not completion latency; first-accepted-artifact time was not measured.

Case02 had **zero successful Mercury calls** and unconfirmed native helpers. B/D each performed two Harness²-inspired planning probes, with zero upstream Harness² calls. No causal contribution or acceleration follows. A later adapter smoke verified one zero-cost Mercury decision; this separate evidence does not change case02.

- Case01: invalidated by a runtime source-hash race; excluded.
- Case03: aborted after Windows SDK materialized future deny targets as directories; immutable.
- Case04: currently running its frozen runtime with a native subscription transport observer; final evidence pending.

Unknown aggregate usage, quota delta and cost remain `null`, never measured zero. Read/shared-state isolation is degraded. Raw native logs, databases, journals and rollout/auth containers are retained locally and must not be published. Frozen task/rubric/evaluator links will be added after case04 completes.
