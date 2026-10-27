# Accepted fixture and reproducible recovery control

[Русский](README.ru.md)

The accepted/sum_cli.py file is byte-identical to the real sandbox-accepted
fixture in the [recovery controls](../../benchmarks/workflow-recovery-20261027/README.md).
It was produced by a labelled fixture generator, not by Sol or Luna.

Inspect its owner-selected checks without running code:

```powershell
python codex-flow.py --repo examples/workflow-recovery/accepted verify --acceptance-file examples/workflow-recovery/acceptance.json
```

Add the global `--codex <absolute-codex-executable>` option before `verify` and
`--execute` after the contract to run the eight checks inside the official Windows
sandbox. No model or subscription login is needed for verification.

To test the full process-crash/resume mechanism without a model, use
`tools/check_workflow_recovery.py` with a fresh short `--output` and installed
`--codex`. See [workflow commands](../../docs/workflows.md). Ordinary workflow
generation uses the real native backend and requires explicit enabling.
