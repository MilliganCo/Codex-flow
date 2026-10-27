# Durable workflow recovery: real process and sandbox controls

[Русский](README.ru.md) · [Exact publication hashes](publication.json) · [Final proof](final/proof-result.json)

Both fixed controls passed using fixture generation and the official Windows
Codex command sandbox. No model generated code during this experiment. This
tests recovery and acceptance, not model speed, solve rate or subscription savings.

| Actual controller crash | Generation calls | SDK launches | Accepted checks | Reserved fixture requests |
|---|---:|---:|---:|---:|
| After committed generation | 1 | 1 | 8/8 | 1 before and after resume |
| After committed verification | 1 | 1 | 8/8 | 1 before and after resume |

The first control also injected one verifier infrastructure interruption before
the SDK launch. Only that stage was retried. The second resumed report creation
without another generator or checker invocation. Separate controller processes
actually exited with codes 71/72 at the checkpoint; these were not exception-only
simulations. Manual changes in the original Git project remained intact. The
accepted bundle contains the corrected fixture, independently checked in the SDK.

Each killed owner left a 30-second reservation. Recovery charged that reservation
conservatively instead of resetting it. The resulting charged active time is a
budget quantity, not a measurement of CPU time or paid model usage. Account quota
and actual money savings were not measured.

An earlier unchanged-checker control timed out at 30 seconds with a 260-character
checker path. Its outcome is retained under earlier-timeout/. Internal attempt
paths were shortened. The subsequent controls passed under the same checker
timeout; this does not independently establish the sole cause of the old timeout.

Reproduce with a fresh short output directory and an installed official CLI:

```powershell
python tools/check_workflow_recovery.py --output E:\flow-recovery-check --codex <absolute-codex-executable>
```

The tool explicitly forbids real model generation. It preserves every output and
refuses to overwrite an existing proof directory. Raw SQLite/native history,
authentication, stdout/stderr and local absolute-path controllers are excluded
from this publication. Raw runtime/checker/fixture bytes and metadata hashes
remain exact. Only selected checks and declared boundaries are attested.

Final source, including the final budget-settlement barrier, passed the same controls: [final proof](final/proof-result.json). The earlier successful control is preserved separately.
