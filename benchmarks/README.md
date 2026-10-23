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
- Case04: complete, with independently accepted artifact scores A/B/C/D **89/83/96/90**. B/C Mercury calls: one each; B/D inspired probes: two each; helpers unverified. [Report](case04/README.md), [metrics](case04/results.json).
- Case05: complete, accepted artifact scores **97/89/89/94**, real B/C/D helpers **1/2/1**, B/C Mercury calls and B/D inspired probes. Solo completed; B/C timed out; D failed to open an upstream connection. [Report](case05/README.md), [unchanged sources](case05/solutions/README.md), [real rotation](case05/rotation.gif).

Unknown aggregate usage, quota delta and cost remain `null`, never measured zero. Read/shared-state isolation is degraded. Raw native logs, databases, journals and rollout/auth containers stay local. The [frozen task/protocol/evaluator/rubric manifest](protocol/frozen-inputs.json) records public reproducibility inputs. No full-component speedup follows from these runs.
