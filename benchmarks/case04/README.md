# Case04: observed results, incomplete full-flow comparison

[Русский](README.ru.md) · [Sanitized metrics](results.json) · [Evidence hashes](evidence-hashes.json) · [Frozen protocol](../protocol/) · [Working older demos](../../examples/ascii-tree/README.md)

Requested model: Sol 6.1 XHigh. A/B then C/D ran concurrently from one scaffold, 1,500 seconds/arm. Blind review assessed 26 criteria: four artifacts accepted, process statuses unchanged:

| Arm | Artifact /100 | Total arm seconds | Original execution | Native requests, including probes |
|---|---:|---:|---|---:|
| A | 89 | 1501.000 | `timed_out` | 24 |
| B | 83 | 1501.375 | `timed_out` | 39 |
| C | 96 | 1475.578 | `completed_unverified` | 24 |
| D | 90 | 1501.344 | `timed_out` | 42 |

Blinding has a metadata-access limitation; details remain in results.json.

**Full-flow A/B is BLOCKED:** no helpers observed in B/C/D; strict profiles/shared-state/depth unverified. Mercury succeeded once in B/C; B/D each ran two Harness²-inspired probes. Upstream executor excluded. No causal contribution or acceleration is established.

All four passed independent 4D and supplemental 20-frame CLI checks. Frozen B/D discovery stays not-assessed: CLI docs missing, points never normalized. Original tests: A33 passed, B25 run/two fixture errors, C35/D43 passed. Native A/B: 55 passed plus Ctrl+C timeout; C/D: 57 passed. Supplemental success does not replace frozen failures.

Only C has complete usage: 1,183,819 input, 44,500 output, 109,696 cached tokens. A/B/D each have one censored request: aggregate null, completed-request lower bounds across all phases separate. Cumulative budget counters are not summed. Money/quota unknown. Resources cover sampled root PIDs, excluding descendants/remote models.

Deadline censoring is not completion latency. Do not pool this changed-runtime case with case02. ZIPs stay local; prompts, native databases/journals, auth, stderr and personal paths are unpublished.
