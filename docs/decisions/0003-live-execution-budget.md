# Share a live execution budget with Flow

Status: MCP native compatibility verified; independent case08 A/B in progress.

Case06's Flow preparation was already1.266 seconds. Its helper used four medium
requests,29.640 summed seconds, with25.891 overlapping root inference. Removing
the helper or shaving routing cannot explain a substantial further improvement.
The useful target is the late448.813-second tail after the reported native Ctrl+C
fix: eight model requests,649270 input and16155 output tokens. This tail included
required documentation/artifacts and a late framing change; verification is not
automatically waste. The sanitized stream does not prove duplicate commands.

## Decision

One `ExecutionBudget` starts before per-arm preparation and is shared with native
execution and the subscription gateway. Existing `RequestBudget` alone reserves
attempts; concurrent pending requests count immediately. The budget observes
monotonic time and used-attempt high-water marks. Phase is the larger of consumed
time fraction and attempt fraction: build below50%, stabilize at50%, finalize at75%.

Parallel Flow receives a process-local `flow_budget.status` MCP tool. A controller
thread atomically publishes the shared time/attempt snapshot once per second.
The stdlib-only server reads one fixed owned file, rejects stale or invalid data,
accepts no tool arguments, executes no commands and has no network/provider code.
It appends only timestamp, result, phase and attempt count to a unique audit file.
Calls are requested at major stage boundaries, not on every inference round.
Single mode has no budget MCP server. Config overrides apply to this invocation;
global MCP configuration is not edited. Tool annotations describe its behavior;
fixed paths, validation and a bounded protocol enforce the server's own boundary.

Gateway developer-message injection is disabled by default for both modes. Three
native prerequisites exposed opaque async history boundaries, so a fourth type
filter patch was rejected. Case07 was cancelled before grading at about508 seconds,
with both partial applications and all traces preserved; it has no quality score.
The explicit experimental library switch remains for diagnostics, with unchanged
bytes fallback. It is not the active native budget channel or a proven optimization.

The note preserves ownership: readonly helpers return evidence, never write or
delegate; the approved initial helper remains permitted. Stabilization defers
optional rewrites/polish while preserving required fixes, tests and artifacts.
Phase guidance is not an enforced application acceptance gate or phase timer.
Completion still requires actual task acceptance or a concrete blocker.

The gateway refuses expired/cancelled/exhausted calls with fixed408/503/429 control
reasons, checks again before upstream open and after the body, clamps header-open
timeout to remaining seconds, and aborts registered readers before native stop.
An initial HTTP-header open has no registered response handle yet; cancellation
there remains bounded by timeout, not instant. Native cancellation now reports
`cancelled`, distinct from `timed_out`; old records are not rewritten.

New diagnostics separate upstream header-open and buffered body-read duration.
These are not pure network/inference or TTFT measurements. Native operation start,
finish and duration carry per-run HMAC fingerprints without command contents or
persisted HMAC keys. Equal fingerprints establish identical operation text within
one run; they do not prove a repeat was unnecessary after code changed.

## Compatibility evidence

The [official MCP guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
documents local stdio servers and tool approvals. The pinned CLI recognized the
selected command, arguments, timeouts, allowlist and approval modes in a zero-model
config check; typed invalid variants were rejected. [Subagent configuration](https://learn.chatgpt.com/docs/agent-configuration/subagents)
documents inherited MCP configuration. Neither check proves actual initialization
or child use. The subsequent bounded root/worker prerequisite completed all11
actual Sol requests and four status calls, with one parent-linked used medium
worker and both marker artifacts correct. All19 prerequisite checks passed.
Aggregate MCP audits do not independently identify the worker's call.
No Platform key or paid API is introduced; the root remains requested Sol6.1XHigh.

Offline: WSL250/250 passed; Windows229 passed with21 symlink skips. Ruff and mypy
passed15 runtime modules; zipapp build and packaged stdio initialize/list/status/EOF
smoke passed with zero models. New tests cover phase bounds,
clock rollback, stale/concurrent counters, unchanged payload fallback, role scope,
expiry/cancel/admission, timeout clamping, HMAC privacy, MCP parsing, fixed paths,
stale data, hardlinks/symlinks, controller lifecycle and workspace/PYTHONPATH import
shadowing. The isolated `-I` bootstrap closes the P1 found during independent review.

## Self-hosting hardening after the case08 freeze

A second review identified a separate source trust boundary: if the assigned task
contains the live Codex Flow package or zipapp, model tools can edit that original
source. `-I` alone does not authenticate an explicitly inserted package. Current
source snapshots exactly four trusted modules before native launch into the
model-read-only `.codex-flow` tree and bootstraps MCP only from that copy. Snapshot
failure aborts setup; it never falls back to editable source. Folder and zipapp
resources and post-snapshot source mutation are covered by model-free checks.

This hardening is after the case08 runtime freeze and is not silently included in
its timings. That frozen runtime was already external to and explicitly denied
from both assigned workspaces, so this trigger does not affect that experiment.
Its exact16 files match explicit curated commit `f52b7e45f7beddf0d3ef9a7c64bb66da91f51d18`
after LF normalization. Latest-source verification is separate: WSL252 passed;
Windows231 passed with21 symlink skips; Ruff/mypy15 modules/build passed.
