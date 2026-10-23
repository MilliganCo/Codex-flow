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

Without `--execute`, the command returns its plan and performs native CLI/login preflight without model generation. With `--execute`, it creates one scaffold commit and detached worktrees, launches A/B concurrently, then C/D concurrently. Each arm shares a hard budget of at most 80 inference requests across its planning probes, root and gateway-routed helpers, plus its wall-clock deadline. The runner records task/evaluator/rubric/runtime hashes, CLI version and execution metrics.

Use repeatable `--protect-path <existing-path>` only for reviewed targets that already exist. The runner adds existing prior experiment roots and the hidden evaluator directory to one identical deny policy supplied to every arm. Do not supply future output paths, reciprocal current-peer targets or blanket parent directories.

`--evaluator` identifies the frozen evaluator for hash recording. **The current runner does not invoke it automatically.** Run that same evaluator on anonymized, completed solutions after both arms finish, then perform the required blind source/visual/interactive review. `benchmark report` reads JSON; it does not compute independent acceptance or render a dashboard.

## Quality and acceptance

The nine protocol category maxima are 12/13/20/12/12/10/9/7/5, totaling 100. Acceptance requires at least 80 plus real XYZW geometry, variable W, a true XW/YW/ZW rotation, 4D→3D→2D projection and a runnable application. Missing evidence is `not-assessed`, not an invented failing score or an automatic pass. ASCII frame differences alone do not prove correct 4D mathematics.

Use identical headless tests for seeds, dimensions, repeat byte determinism, ASCII/no ANSI, small terminals and angular changes. Review geometry, occlusion, controls, aesthetics and maintainability independently. Do not rely only on self-authored tests.

## Metrics and limitations

Store PID/start/end/exit status, full arm duration, optional probe overhead, actual component calls and known token usage. Native root usage is retained separately. The loopback gateway records requested model/effort, actual response model, request status and usage. It computes all-request totals only when every observed request completes with complete usage; the benchmark sums phase totals only when all phases qualify. Unknown totals, quota deltas, first-working-demo time and actual API cost stay `null`. Subscription usage is not actual API billing. Requests and different model/effort profiles alone do not prove distinct helper identities.

The current manifest records separate workspaces with their own home, temp and cache directories plus physical project-local SQLite/log paths, but shared native authentication/rollout storage. The CLI can rehydrate unrelated historical thread metadata from shared rollouts into the project-local database. Separate paths therefore do not establish isolated native contexts or log contents: strict independent profiles are blocked by this platform behavior. Single-agent parents are ephemeral; parallel parents persist for native worker rollouts. Custom roles inherit parent permissions; read-only ownership and depth are instructions.

This observation degrades shared-state independence in addition to peer-read isolation. It is not evidence of actual cross-arm solution reading. An audit restricted to each run's own native sessions remains pending after A/B reaches a terminal state; do not query broad shared history. Native databases, journals/WAL files and raw native logs must not be published as experiment artifacts. Frozen code and inputs remain unchanged; any audit conclusion must preserve this distinction.

Reciprocal per-arm Windows deny profiles interfered through shared `CodexSandboxUsers` ACLs. All arms therefore receive the same existing-target policy protecting the hidden evaluator and previous solutions. Current-peer reading remains prohibited by instructions with **degraded physical isolation**. Parallel timing also shares CPU/network/subscription rate limits. One case study cannot establish a stable latency or quota advantage. Repeat with controlled order and sufficient quota before generalizing. No cross-arm code merging is allowed during the experiment.

An initial development launch was invalidated when runtime source changed during hashing. Preserve that excluded record for audit, but omit it from accepted timing comparisons. The restarted experiment must execute an immutable copied runtime whose recorded hash matches the code actually used. A source-race recovery is a new experiment condition, not a reason to rewrite the original manifest.

## Development experiment records

The frozen `case02` runtime predates the corrected Mercury transport and current subscription gateway. Mercury recorded zero successful calls; native helper execution was unconfirmed. A later current-source smoke returned one verified zero-cost typed Mercury decision. It belongs to integration validation, not to the frozen arms.

Both primary A/B executions reached the fixed 1,200-second deadline while preserving runnable applications. The headless evaluator passed 25/25 checks for each, and a separate geometry script passed actual XYZW, nonplanar XYZ rank-3 and perspective checks. Subsequent artifact review assigned these scores:

| Frozen case02 group | Artifact score /100 | Integration evidence |
|---|---:|---|
| A | 95 | Solo baseline |
| B | 97 | Mercury successful calls 0; helpers unconfirmed; Harness²-inspired probes |
| C | 95 | Mercury successful calls 0; helpers unconfirmed |
| D | 96 | Helpers unconfirmed; Harness²-inspired probes |

These artifact scores do not establish successful completion within the deadline, a full-component benchmark or a speed winner. In particular, the Mercury ablation does not measure Mercury's contribution when it had zero successful calls. Retain the original execution statuses alongside the reviewed artifacts.

`case03` was **ABORTED** after Windows SDK created directories for future deny targets. Its frozen inputs and failure record remain immutable; it is excluded from performance conclusions. The current code rejects missing protected targets and uses one shared existing-target policy.

`case04` started at **2026-10-23 14:00:48 UTC**, with A/B running against `frozen-runtime-20261023-04` in this documentation snapshot. No final score, full-integration result or speed winner is assigned. Independent review found that the frozen `multi_agent_verified` heuristic based on requested model/effort is insufficient proof of worker execution. Require native collaboration evidence together with completed-request evidence; retain the heuristic's original value only as historical raw data. A separate stdin-write cleanup issue is being corrected in development source. Such corrections do not modify frozen case04. Any later run needs its own frozen version, hashes and independent evidence; do not rewrite earlier experiments to reflect new code.
