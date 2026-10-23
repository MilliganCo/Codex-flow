# Frozen case05 applications

[Русский](README.ru.md) · [Independent results](../README.md) · [Exact source hashes](../source-publication.json)

These are evaluated Windows benchmark snapshots, not repaired production examples. All 127 published files preserve the evaluated bytes. Five original self-report logs were omitted; native/Git/auth state, caches and QA scratch are excluded. Original ASCII samples are retained. Snapshot README links to omitted self-report logs can be unavailable; their failures and missing documents remain part of the recorded evaluation.

| Directory | Execution condition | Score /100 | Known limit |
|---|---|---:|---|
| `A` | Solo Sol XHigh | 97 | Dense crown; some 4D framing clips the top |
| `B` | Full configured Flow with native helper, Mercury and inspired probes | 89 | Required documentation missing; Ctrl+C timed out in the tested ConPTY environment |
| `C` | Flow without inspired probes | 89 | Required documentation missing; interactive exports lag the current view by one frame |
| `D` | Flow without Mercury | 94 | Frozen test invocation has three missing `.tmp` fixture errors; a documentation link is absent |

All passed the five critical geometry/runnable gates. Acceptance does not mean every check passed. Generator process statuses, transport failures and deadline limits are kept separately in the [report](../README.md). Cross-platform CI covers the maintained examples elsewhere; these unrepaired snapshots were independently executed on Windows.

From the repository root, run the solo snapshot without models or installation:

```powershell
Push-Location benchmarks/case05/solutions/A
python -m ascii_tree view --seed 42 --mode 4d
Pop-Location
```

Use directory `B`, `C` or `D` for another snapshot. `1`/`2`/`3` switch dimensions; `[`/`]` rotate in 4D; `Q` or Escape exits. Prefer those tested exit keys for snapshot B in the documented ConPTY environment. Each snapshot also supports `python -m ascii_tree --help` and `render`.

The original evaluator, rubric and task remain frozen. No score or original source was changed during publication. The separate packaged [case02 demos](../../../examples/ascii-tree/README.md) have Windows/Ubuntu CI and an explicitly labelled identity-portability patch.
