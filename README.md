# Codex Flow

[Русский](README.ru.md) · [Getting started](docs/getting-started.md) · [Architecture](docs/architecture.md) · [Safety](docs/safety-and-permissions.md)

Codex Flow evolves the existing 1.2.0 workflow skill with an **opt-in, project-local execution runtime**. The original skill, offline installer, bounded doctor and project scaffolding remain available. The new runtime coordinates the native Codex CLI, records execution evidence and supports controlled A/B experiments.

The coordinator profile is `gpt-6.1-sol` with `xhigh` reasoning. The first independent
helper is a `reviewer/high` acceptance-risk pass; the chief owns critical
implementation and verification. Medium code proposals are limited to low-risk
modules. Mercury and Harness-inspired probes are optional and disabled by default.

**Status:** private development. No project license has been selected. There is no validated universal speedup or quota-saving claim. Runtime completion is distinct from independent acceptance.

[Durable workflows](docs/workflows.md) add project-local SQLite state for
**prepare → generate → verify → report**. Each attempt uses a separate snapshot;
resume reuses hash-checked stages without resetting requests or charged active
time. The original project is never automatically updated. Commands are
`workflow start`, `status`, `pause`, `resume`, and `cancel`.
[Real crash/recovery controls](benchmarks/workflow-recovery-20261027/README.md)
passed with fixture generation and the official Windows sandbox: one generator
call and eight checks per workflow, including report-only recovery. No model
was invoked for these controls. [Accepted fixture demo](examples/workflow-recovery/README.md).

For an existing Python unittest project, `workflow init` now creates a versioned
acceptance checker without executing project code. Then `workflow start "Task"
--dry-run` uses that explicitly initialized checker. Existing test bytes are
frozen; zero tests cannot pass. `workflow status ID --human --lang en` summarizes
stages and remaining budget; the default JSON interface is unchanged.
[Model roles](docs/model-roles.md) includes GPT-6.1 Terra as a documented candidate
with dispatch disabled. Live model experiments remain paused; Sol XHigh stays
the default. See the [workflow guide](docs/workflows.md) for exact commands.
[Fourteen real sandbox controls and a complete fixture workflow](benchmarks/workflow-setup-20261027/README.md)
validate the setup without model calls.

An optional [external acceptance gate](docs/acceptance-gate.md) now connects that
distinction to ordinary `run`: supply an owner-reviewed `--acceptance-file` to
require sandboxed checks before `completed_verified` / `accepted: true`. Without
one, completion stays unverified. The separate `verify` command runs no model.
[Working JSON CLI example](examples/acceptance-gate/README.md) and
[seven real sandbox controls](docs/evidence/acceptance-gate-sdk-20261026.json)
cover correct output, deliberate defects, empty/stale/missing reports, timeout,
and observed read/write restrictions. This verifies the gate, not a model speedup.

The final [two-task CLI cohort](benchmarks/efficient-cli-suite-20261026-02/README.md)
finished both Solo and Flow arms within 1,500 seconds and 80 physical requests.
All four unchanged applications scored **100/100** in independent SDK grading.
Flow took **719.281 vs 599.609 seconds** on Ledger and **1,207.984 vs 925.687 seconds**
on SafeZip: about **20.0% and 30.5% longer**. The required acceleration without
quality loss was **not achieved**. The slower test-proposal policy is retained as
an exact frozen candidate and was not promoted; the current default keeps the
balanced, context-only `reviewer/high` risk pass with its shell tool disabled.
Earlier [transport-failed](benchmarks/cohesive-suite-20261024-02/README.md) and
[partial-completion](benchmarks/resilient-cli-suite-20261026-01/README.md) cohorts
remain visible. [Offline demos](benchmarks/efficient-cli-suite-20261026-02/README.md#run-the-included-cli-demos)
and a [separate-checkout rollback](docs/rollback.md#before-the-cli-recovery-changes)
are included.

The complete [fixed three-task series](benchmarks/stream-suite-20261024-01/README.md)
completed **all six branches and all 147 native requests without transport errors**.
Scores A/B: Tree **98/96**, Ledger **100/100**, SafeZip **100/100**. Flow was 3.419%
faster on Tree but slower on both other tasks; acceleration without quality loss
was **not established**. All 130 submitted files and actual demonstrations are
retained unchanged. The stream fix passed 279 offline checks on Linux; Windows
passed 258 with 21 platform skips. [Case08](benchmarks/case08/README.md) and every
earlier negative result remain available. [Rollback](docs/rollback.md) preserves
the current checkout and host settings.

The separate [changed-policy confirmation](benchmarks/tree-confirmation-20261024-10/README.md)
scored **Solo 88 / Flow 94**. Flow completed in 1344.609 seconds and passed native
57/57; Solo reached its 1500-second limit and its Ctrl+C check did not finish.
The strict speed comparison therefore failed. Both negative admissions remain
visible; working demonstrations, untouched source and exact runtime snapshots
are included.

## Start with a dry run

Use Python 3.11+ and an existing Codex CLI. Python 3.12 is the benchmark preference. The runtime uses the standard library; it does not install dependencies or provision model accounts.

```powershell
python codex-flow.py --help
python codex-flow.py doctor
python codex-flow.py run "Describe a bounded change" --dry-run
```

`doctor` checks the local CLI and subscription login without generating a model response. `doctor --deep` additionally asks the CLI for account class and model metadata. Metadata availability does not prove generation works.

After reviewing the plan, explicitly enable an execution:

```powershell
python codex-flow.py --repo <project> run "Implement the agreed change" --enable --single-agent
```

Replace angle-bracket placeholders with actual paths. Global options such as `--repo`, `--codex` and `--config` precede the subcommand. A run uses the existing ChatGPT subscription login; the adapter rejects API-key fallback. It does consume subscription quota.

## Implemented commands

| Command | Actual behavior |
|---|---|
| `doctor [--deep]` | CLI/login preflight; optional model/account metadata |
| `integrations status` | Configured integration flags; no claim of live validation |
| `run ... [--dry-run] [--enable]` | Route one task and optionally execute the native CLI |
| `runs list/show/cancel/replay` | Inspect stored metrics, request cancellation or summarize JSONL events |
| `benchmark tree/report` | Prepare/execute A/B plus ablations, or read their manifest and metrics |

There is no runtime TUI, live dashboard, runtime `resume`, or general automatic repair loop. `runs replay` summarizes stored events; it does not repeat inference. The existing skill still has conversational review/resume/checkpoint routes.

## Coordination and integrations

Routing uses explicit independent-step counts and ownership conflicts, with deterministic fallback. A valid Mercury recommendation can prefer parallel or single execution. `--single-agent` or `--strategy single` forces the single route; `--strategy parallel` still follows the independence gate. `--max-agents` is bounded to a native concurrent-helper cap of 1–3. Total helper count and maximum delegation depth are instruction-only limits, not verified hard runtime limits.

| Component | Boundary and current limitation |
|---|---|
| Native Codex | Root Sol XHigh through a nonce-protected loopback subscription gateway; no sandbox bypass |
| Mercury | External, explicitly trusted free-only adapter; no provider code or credentials bundled |
| Harness-inspired guard | Defers uncalibrated optimization; explicit plan diagnostics cannot adopt; upstream executor is not used |
| Telemetry | Request model/effort, actual response model and usage; unknown or incomplete totals remain null |

The current Mercury bridge has completed a real free-only typed smoke after forwarding the user's existing Windows system proxy to the Node child with `--use-env-proxy`. Model/build/provider checks passed; reported usage cost was zero. Proxy values were not logged and global settings were not edited. Mercury remains disabled by default. The earlier frozen benchmark used a prior bridge with zero successful Mercury calls; this later smoke does not retroactively activate Mercury in that experiment.

When enabled, the Harness-inspired runtime guard reports deferred calibration with zero automatic online probes. Plan coverage did not establish application-quality gains, so old coverage-only overlays are no longer applied. Explicit library diagnostics cannot adopt instructions. Historical benchmark records retain their original behavior. See [integrations](docs/integrations.md).

## Safety and evidence

The runtime is off until `--enable` or project configuration opts in. A loopback gateway forwards only to the fixed official subscription upstream, requires a fresh per-run nonce, and enforces a shared inference-request budget of at most 80 including probes. Native authentication is forwarded in memory; tokens are not copied into projects and host configuration files are not rewritten.

Single-agent execution is ephemeral. Parallel parents persist because native workers require a parent rollout. SQLite/log paths and workspace home/temp/cache are project-local, while the native auth/rollout container remains shared. **Separate paths do not establish separate native context:** the CLI can rehydrate unrelated historical thread metadata from shared rollouts into a project-local database. Strict independent profiles are therefore blocked by this platform behavior. Never publish native databases, journals or raw native logs. Custom helper roles inherit parent permissions; their read-only ownership and depth restrictions are instructions, not separate hard sandboxes.

On this Windows sandbox, reciprocal per-arm deny rules interfered through shared `CodexSandboxUsers` ACLs. The benchmark gives every arm the same deny policy for existing evaluator/prior-solution targets. Current peer reads remain a soft prohibition: **physical read and shared-state isolation are degraded**. The completed audit of B/C/D's own journals found no native spawn calls or literal peer/state-read indicators; this limited observation does not prove absence of all cross-arm reads. A was ephemeral and has no equivalent retained journal. See [safety](docs/safety-and-permissions.md).

Gateway totals are available only when every observed request completes with usable usage. Request counts do not identify agents; top-level unknown totals, quota deltas and actual API cost remain `null`. Root CLI usage is retained separately. `max_attempts` is a bounded configuration field; the wrapper makes one task attempt. The optional project setting `native_request_retries: 1` enables one native HTTP retry and bounded stateless recovery within the same deadline/request budget. Its default is `0`; stream retries and gateway replays remain disabled. See [configuration](docs/configuration.md#bounded-http-recovery).

The frozen case02 applications scored A=95, B=97, C=95 and D=96, with zero successful Mercury calls and unconfirmed helpers. The later [case04](benchmarks/case04/README.md) scored A=89, B=83, C=96 and D=90; all four artifacts met the frozen acceptance rule. B/C each made one real Mercury call and B/D each ran two inspired probes, but helpers remained unverified. A/B/D hit their deadlines. These are artifact-quality results, without a full multi-agent or speedup conclusion. Case01 is invalidated and case03 aborted; both remain immutable. See [benchmark evidence](docs/benchmarking.md).

The frozen [case05](benchmarks/case05/README.md) observed real parent-linked helpers in B/C/D (1/2/1), one Mercury call in B/C and two inspired probes in B/D. Artifact scores were **A=97, B=89, C=89, D=94**, all accepted. A completed in 1,463.437 seconds; B/C reached their deadlines and D stopped on an upstream connection-open error. The solo artifact scored highest in this case. No general speed, quota or causal contribution claim follows. [Unchanged evaluated sources](benchmarks/case05/solutions/README.md) and exact evidence are preserved; later changes do not rewrite its frozen runtime.

The independent [case06 repeat](benchmarks/case06/README.md) kept the literal task, evaluator, rubric, Sol XHigh and 1500-second/80-request limits. After removing the unvalidated 125.328-second calibration prefix and requesting earlier runnable/docs/verification artifacts, **solo scored 97 and updated Flow 98**. Both completed and passed 57/57 native interaction checks. Their only score difference is one aesthetic point. Process durations were 1444.484/1414.000 seconds and native request counts 43/36. Flow used one verified helper, one free Mercury call and a deferred Harness-inspired guard with zero online probes. This is one case, not proof of general speedup, active optimizer benefit or subscription-quota savings. The [diagnosis](docs/decisions/0002-remove-proxy-calibration-prefix.md) and [unchanged new sources](benchmarks/case06/solutions/README.md) are retained.

## Run the accepted examples

![Actual case06 solo and Flow exports in 2D, 3D and 4D](benchmarks/case06/comparison.png)

These are six actual frozen headless exports from accepted case06 A/B, typeset without rerunning or repairing the apps. They are not interactive screenshots. The earlier four [case05 applications](benchmarks/case05/solutions/README.md) remain unchanged with recorded defects. Separately maintained [case02 demos](examples/ascii-tree/README.md) have Windows/Ubuntu CI.

[Watch the actual 4D XW-rotation frames](benchmarks/case05/rotation.gif), generated after evaluation from unchanged case05 A.

```powershell
Push-Location benchmarks/case06/solutions/B
python -m ascii_tree view --seed 42 --mode 4d
Pop-Location
```

Use `1`, `2`, `3` to switch dimensions, `[` / `]` for 4D rotation, and `Q` to quit. No model account or package installation is needed to run the examples.

## Existing installation and checks

The offline installer remains separate:

```powershell
python payload/codex-flow/scripts/flowctl.py doctor
python payload/codex-flow/scripts/flowctl.py install --dry-run
python -m unittest discover -s tests -v
```

Inspect dry-run output and preserve local skill edits before applying any installation. Existing Obscura/Chromium routing customizations require reconciliation. The installer protects managed global blocks and keeps backups. See [rollback](docs/rollback.md).

Documentation: [baseline audit](docs/baseline-compatibility.md), [configuration](docs/configuration.md), [benchmarking](docs/benchmarking.md), [troubleshooting](docs/troubleshooting.md), [limitations](docs/limitations.md), [FAQ](docs/faq.md), [contributing](CONTRIBUTING.md), [security](SECURITY.md), [license options](docs/license-options.md), [provenance](THIRD_PARTY_NOTICES.md).

Upstream references: [Codex CLI](https://github.com/openai/codex), [Harness²](https://github.com/google-research/harness2), [Mercury Decide free route](https://openrouter.ai/inception/mercury-decide:free). These projects and services are independently maintained; their presence does not establish a working integration in this checkout.
