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

This observation degrades shared-state independence in addition to peer-read isolation. The completed audit of B/C/D's exact owned journals found no native spawn calls or literal current-peer/private-state read indicators. This is a bounded observation, not proof of absence of all such reading. A was ephemeral and lacks an equivalent retained journal. Never query broad shared history or publish native databases, journals/WAL files or raw native logs. Frozen code and inputs remain unchanged.

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

`case04` is complete: [English report](../benchmarks/case04/README.md), [Russian report](../benchmarks/case04/README.ru.md), [sanitized metrics](../benchmarks/case04/results.json). Artifact scores A/B/C/D are **89/83/96/90**, all accepted under the frozen formula and critical 4D gates. A/B/D reached the 1,500-second deadline; C completed in 1,475.578 seconds. B/C each made one successful Mercury call, B/D each ran two local probes, and no arm verified a helper. The reports preserve B's two failing self-tests/missing README, D's missing README, and A/B Ctrl+C terminal-check timeouts. Acceptance is not a claim that every criterion passed.

The original requested-profile `multi_agent_verified` heuristic is insufficient proof and remains historical raw data. Current source accepts completed native spawn evidence or exact owned parent-linked child metadata with positive usage. Controller changes and later capability proofs do not rewrite case04 or establish a full multi-agent benchmark. Timing is deadline-censored, so there is no speed winner. The [frozen task, protocol, rubric and evaluator](../benchmarks/protocol/frozen-inputs.json) are published with hashes. [Blinding audit](evidence/blinding-audit-case04.json) records the original visible `.git` filename/size, reviewer attestation and corrected source archives without worktree pointers.

## Final case05

[Report](../benchmarks/case05/README.md), [Russian report](../benchmarks/case05/README.ru.md), [metrics](../benchmarks/case05/results.json) and [unchanged generated applications](../benchmarks/case05/solutions/README.md) describe a separately frozen runtime, after a real ordinary-controller/helper prerequisite and concurrent zero-model permission proof. The exact task/evaluator/rubric hashes were retained. A/B ran concurrently, then C/D.

Artifact scores A/B/C/D are **97/89/89/94**, all accepted. Actual direct helpers were 1/2/1 in B/C/D; successful Mercury calls were one each in B/C; inspired probes were two each in B/D. A finished in 1,463.437 seconds; B/C reached 1,500-second deadlines and D failed at 1,334.063 seconds on `upstream_open_error` without an HTTP response or retry. Solo scored highest in this case; this does not establish a general speed or quota advantage.

All four passed independent true-4D geometry checks. Frozen machine points were 25/25 for A/B/C and 22/25 for D, whose test command encountered three absent `.tmp` fixtures. Native checks passed 57/57 for A/D; B passed 55 before Ctrl+C timeout (two assertions unassessed), and C passed 46/57 with stale cached-export comparisons. No fixtures, controls or scores were repaired. The blind review was completed before identity mapping; a documented adapter changed numeric IDs to filename labels only.

Current CLI record-access hardening follows the frozen benchmark. [Runtime equivalence](../benchmarks/case05/results.json) binds the executed raw hashes to a specific earlier publication commit after LF normalization; it does not claim raw-byte equality with latest main. [Owned-session audit](evidence/case05-owned-session-audit.json) covers only exact B/C/D cwd rows/journals. Observed depth was one; extra contexts outside those cwd values and A's ephemeral journal were not audited. Marker absence and metadata import do not establish read confidentiality. Strict native-history/profile and current-peer isolation remain degraded.
