# External acceptance example

[Русский](README.ru.md)

This owner-selected checker exercises eight real JSON CLI cases. It verifies
integer sums, arbitrary-precision output and invalid input. All app/checker code
runs inside the official Windows Codex sandbox, without a model or login.

From the Codex Flow repository root, first inspect the frozen input contract:

```powershell
python codex-flow.py --repo examples/acceptance-gate verify --acceptance-file examples/acceptance-gate/contract.json
```

Execute it with an installed official Codex CLI:

```powershell
python codex-flow.py --repo examples/acceptance-gate --codex <absolute-codex-executable> verify --acceptance-file examples/acceptance-gate/contract.json --execute
```

Exit 0 with `accepted: true` requires all eight cases to pass, unchanged declared
source/checker hashes and complete sandbox evidence. A missing/empty/stale report,
failed case, timeout or changed source is rejected. Detailed receipts are written
under this example's ignored `.codex-flow/runs/` directory.

[Full contract and limits](../../docs/acceptance-gate.md). This is an acceptance
mechanism example, not a new model benchmark or proof of overall code quality.
