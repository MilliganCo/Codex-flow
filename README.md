# Codex Flow

[Русский](README.ru.md) · [Getting started](docs/getting-started.md) · [Architecture](docs/architecture.md) · [Safety](docs/safety-and-permissions.md)

Codex Flow evolves the existing 1.2.0 workflow skill with an **opt-in, project-local execution runtime**. The original skill, offline installer, bounded doctor and project scaffolding remain available. The new runtime coordinates the native Codex CLI, records execution evidence and supports controlled A/B experiments.

The coordinator profile is `gpt-6.1-sol` with `xhigh` reasoning. Native helpers are used only for independent work; the coordinator integrates their results. Mercury and Harness-inspired probes are optional and disabled by default.

**Status:** private development. No project license has been selected. There is no validated universal speedup or quota-saving claim. Runtime completion is distinct from independent acceptance.

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
| Native Codex | Subscription transport, root Sol XHigh, `workspace-write`, no sandbox bypass |
| Mercury | External, explicitly trusted free-only adapter; no provider code or credentials bundled |
| Harness-inspired probes | Local measured plan comparison and guarded adoption; upstream Harness² executor is not used |
| Telemetry | Sanitized events and root usage; aggregate helper usage remains unknown when unavailable |

The initial Windows Node shutdown issue was fixed by a natural-exit wrapper. A subsequent free-only smoke was rejected with HTTP 403, zero inference attempts and zero successful calls. Treat Mercury as unavailable until an explicit live check records a valid response and verified zero cost. The adapter falls back to deterministic routing. This is a local integration observation, not a provider-wide outage claim.

When explicitly configured, both normal execution and the benchmark can run a pair of measured planning probes. The Harness-inspired result remains degraded because plan coverage does not demonstrate an improvement in application quality. These probes consume additional subscription time/quota. See [integrations](docs/integrations.md).

## Safety and evidence

The runtime is off until `--enable` or project configuration opts in. Host configuration files are not rewritten. Execution uses process-local CLI overrides, an ephemeral session and separate workspace home/temp directories. The existing `CODEX_HOME` is shared for native credential reuse; tokens are not copied into projects. `workspace-write` restricts writes but **does not establish isolation from sibling reads**. This limits benchmark independence and is recorded as degraded isolation.

Unknown metrics use `null`, including aggregate helper tokens, quota deltas and actual API cost when not measured. Root usage remains available separately. `max_attempts` is a bounded configuration field; the current wrapper makes one attempt with automatic transport retries disabled.

## Existing installation and checks

The offline installer remains separate:

```powershell
python payload/codex-flow/scripts/flowctl.py doctor
python payload/codex-flow/scripts/flowctl.py install --dry-run
python -m unittest discover -s tests -v
```

Inspect dry-run output and preserve local skill edits before applying any installation. Existing Obscura/Chromium routing customizations require reconciliation. The installer protects managed global blocks and keeps backups. See [rollback](docs/rollback.md).

Documentation: [configuration](docs/configuration.md), [benchmarking](docs/benchmarking.md), [troubleshooting](docs/troubleshooting.md), [limitations](docs/limitations.md), [FAQ](docs/faq.md), [contributing](CONTRIBUTING.md), [security](SECURITY.md), [license options](docs/license-options.md), [provenance](THIRD_PARTY_NOTICES.md).

Upstream references: [Codex CLI](https://github.com/openai/codex), [Harness²](https://github.com/google-research/harness2), [Mercury Decide free route](https://openrouter.ai/inception/mercury-decide:free). These projects and services are independently maintained; their presence does not establish a working integration in this checkout.
