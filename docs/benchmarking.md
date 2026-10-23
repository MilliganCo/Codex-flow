# Benchmarking

The benchmark is a reproducible case study, not a promise of speed. Use the same frozen task, scaffold commit, root model/effort, dependencies, budgets and independent evaluator across groups. Freeze hashes **before** executors begin and preserve every condition change under a new experiment ID.

| Group | Native helpers | Mercury | Optimization |
|---|---|---|---|
| A | Disabled | Disabled | Disabled |
| B | Enabled when routing permits | External free-only adapter | Local measured Harness²-inspired probes |
| C | Enabled when routing permits | External free-only adapter | Disabled |
| D | Enabled when routing permits | Disabled | Local measured Harness²-inspired probes |

The root model/effort stays Sol 6.1 XHigh. Optional helper defaults differ and must be reported from actual evidence. If Mercury has no successful calls, B is degraded and the B/D contrast does not measure Mercury's value. Local plan probes are not upstream Harness² execution.

## Runner commands

Prepare a frozen external evaluator and task first. Outputs must use a new experiment root:

```powershell
python codex-flow.py benchmark tree --task-file <task.md> --root <new-experiment-root> --evaluator <frozen-evaluator.py>
python codex-flow.py benchmark tree --task-file <task.md> --root <new-experiment-root> --evaluator <frozen-evaluator.py> --execute
python codex-flow.py benchmark report --root <experiment-root>
```

Without `--execute`, the command returns its plan and performs native CLI/login preflight without model generation. With `--execute`, it creates one scaffold commit and detached worktrees, launches A/B concurrently, then C/D concurrently. The budget includes each arm's optional planning probes. The runner records task/evaluator/rubric/runtime hashes, CLI version and execution metrics.

`--evaluator` identifies the frozen evaluator for hash recording. **The current runner does not invoke it automatically.** Run that same evaluator on anonymized, completed solutions after both arms finish, then perform the required blind source/visual/interactive review. `benchmark report` reads JSON; it does not compute independent acceptance or render a dashboard.

## Quality and acceptance

The nine protocol category maxima are 12/13/20/12/12/10/9/7/5, totaling 100. Acceptance requires at least 80 plus real XYZW geometry, variable W, a true XW/YW/ZW rotation, 4D→3D→2D projection and a runnable application. Missing evidence is `not-assessed`, not an invented failing score or an automatic pass. ASCII frame differences alone do not prove correct 4D mathematics.

Use identical headless tests for seeds, dimensions, repeat byte determinism, ASCII/no ANSI, small terminals and angular changes. Review geometry, occlusion, controls, aesthetics and maintainability independently. Do not rely only on self-authored tests.

## Metrics and limitations

Store PID/start/end/exit status, full arm duration, optional probe overhead, actual component calls and known token usage. Native root usage is retained. Aggregate helper usage, quota deltas, first-working-demo time and actual API cost stay `null` when unavailable; never replace missing observations with zero. Subscription use is not actual API billing.

The current manifest records shared credential home, separate workspace home/temp/cache and degraded read isolation. A sibling-read probe succeeded. The task forbids cross-arm reading, but OS isolation does not enforce that prohibition. Parallel timing also shares CPU/network/subscription rate limits. One case study cannot establish a stable latency or quota advantage. Repeat with controlled order and sufficient quota before generalizing. No cross-arm code merging is allowed during the experiment.

An initial development launch was invalidated when runtime source changed during hashing. Preserve that excluded record for audit, but omit it from accepted timing comparisons. The restarted experiment must execute an immutable copied runtime whose recorded hash matches the code actually used. A source-race recovery is a new experiment condition, not a reason to rewrite the original manifest.
