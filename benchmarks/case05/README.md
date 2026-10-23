# Case05: observed results and boundaries

[Русский](README.ru.md) · [Metrics](results.json) · [Hashes](evidence-hashes.json) · [Evaluated sources](solutions/README.md) · [Source manifest](source-manifest.json) · [Protocol](../protocol/)

Separate case using frozen runtime 343d395: Sol 6.1 XHigh, A/B then C/D. Blind review assessed 26 criteria and five critical gates; accepted artifacts: 4/4. Artifact acceptance preserves original execution status.

| Arm | Score /100 | Artifact accepted | Total arm seconds | Original status | Native requests |
|---|---:|---|---:|---|---:|
| A | 97 | True | 1463.437 | `completed_unverified` | 29 |
| B | 89 | True | 1501.032 | `timed_out` | 58 |
| C | 89 | True | 1500.906 | `timed_out` | 40 |
| D | 94 | True | 1334.063 | `failed` | 53 |

Observed integrations:

| Arm | Parent-linked helpers | Mercury successes | Inspired probes |
|---|---:|---:|---:|
| A | n/a | 0 | 0 |
| B | 1 | 1 | 2 |
| C | 2 | 1 | 0 |
| D | 1 | 0 | 2 |

Helper identity requires native parent-child linkage, never a requested model/effort. Unknown count stays null. Local Harness²-inspired probes are not the upstream executor; Mercury calls alone do not establish routing accuracy.

Complete aggregate usage requires completed, known-usage requests across every phase. Known-completed lower bounds remain separate; cumulative budget counters are never summed. Unmeasured money/quota stays unknown. RSS/CPU covers sampled root/probe PIDs, excluding descendants/remote models.

Frozen discovery, submitted-test and terminal failures remain unchanged. A missing supplemental run is not_run, never fabricated or used to replace frozen evidence. Deadline censoring is not completion latency. Do not pool this changed-runtime case with 02/04 or infer causal contribution/speed percentages.

A scored highest in this case. B lacks the required documentation and timed out during the ConPTY Ctrl+C check; Q/Escape worked. C lacks documentation and its cached interactive exports lag the current view. D retains three missing `.tmp` fixture errors under the frozen test command and a missing validation-document link. All four independently passed 16 geometry checks, including branch-skeleton rank three, variable W and exact hyperrotation/perspective. Native checks: A/D 57 passed; B 55 passed plus the Ctrl+C timeout diagnostic (two remaining assertions unassessed); C 46 passed/11 failed. D's generator failed on `upstream_open_error` without an HTTP response; its precise network cause is unknown and no retry was made.

Only A has complete all-phase usage: 1,415,382 input and 46,482 output tokens, including 267,776 cached input tokens. B/C/D aggregate totals stay null; known completed-request lower bounds are in JSON. Mercury reported zero cost for its two validated free calls; subscription money and quota delta remain unknown. These observations do not establish a performance gain.

All [127 published application files](source-publication.json) preserve evaluated bytes; five original self-report logs are omitted. The [full independent rubric review](blind-review.json) only redacts local paths; scores, gates and acceptance are unchanged. The original review remains immutable; a separate recorded metadata adapter maps numeric IDs to filename labels for packaging. The [owned-session audit](../../docs/evidence/case05-owned-session-audit.json) is scoped and does not establish physical read isolation or a hard depth guarantee.

![Actual accepted A CLI exports, typeset after evaluation](preview.png)

[Real XW rotation](rotation.gif) uses twelve post-evaluation CLI frames from unchanged A; [provenance](rotation.provenance.json). This is not a GUI screenshot or benchmark-latency measurement.

Executed raw fingerprints are retained. Publication equivalence is to the explicit commit after LF normalization, not raw-byte identity or automatically latest main. Later CLI security hardening is not retroactive. Shared native history/profile isolation remains degraded. ZIPs stay local; native request bodies/private instruction payloads, raw native/auth state, databases/journals, stderr and personal paths are unpublished; the common frozen brief is in the protocol.
