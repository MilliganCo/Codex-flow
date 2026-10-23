# ADR 0001: preserve the skill and add an opt-in runtime

Status: accepted for this development iteration; distribution license pending.

## Context

Codex Flow 1.2.0 already provides conditional workflow routes, a standard-library offline installer, safe managed instruction updates and project scaffolding. Replacing it would discard useful compatibility and local customizations. Multi-agent orchestration and measured experiments need executable state, deadlines and traceable events beyond a prompt-only workflow.

The existing host has protected configuration and subscription authentication. Upstream research executors and external decision adapters have independent permission and licensing boundaries.

## Decision

Retain `payload/codex-flow/` and its CLI unchanged. Add `codex-flow.py` and `runtime/codex_flow/` as an opt-in project-local layer. Use the native CLI's subscription transport with root Sol XHigh. Keep optional integrations disabled by default, reject paid-API configuration and preserve host files. External Mercury code remains outside the repository. Implement bounded measured local proposals rather than launching the upstream Harness² executor.

Separate configuration from validation. Store real events and available root usage; leave unavailable metrics null. Preserve failed artifacts. Distinguish native turn completion from independent application acceptance.

## Consequences

The installation can be reviewed or rolled back without migrating global model/provider settings. Users must understand two interfaces: conversational skill routes and runtime CLI commands. Process-local sandbox/approval choices still require explicit review.

Current workspace-based permissions do not fully prevent sibling reads, and native auth/rollout storage is shared. Single-agent parents are ephemeral, while parallel parents persist for worker rollouts with project-local SQLite/logs. Custom roles inherit parent permissions; read-only/depth guidance is not a hard per-role sandbox. Reciprocal Windows ACL interference requires identical existing-target denials and explicit degraded peer isolation.

A nonce-protected loopback gateway with fixed official subscription upstream now enforces a shared request budget and records request model/effort plus response model/usage. Request metadata is not agent identity or independent response confirmation of effort. A local planning-probe result cannot be presented as upstream Harness² or a general quality improvement. No automatic retry loop or runtime TUI is implied by this decision.
