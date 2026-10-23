# Troubleshooting

Start with `python codex-flow.py doctor`, then the relevant command's `--help`. Preserve failed-run metrics and events. Do not repeatedly rerun an unchanged failing command or weaken sandbox/auth restrictions to obtain a green status.

| Symptom | Cause or discriminating check | Safe next step |
|---|---|---|
| Runtime disabled | Default `enabled: false` | Review a dry run; opt in with `--enable` for an authorized execution |
| Codex unavailable | Missing PATH entry, invalid executable or incompatible CLI | Select the existing executable with `--codex`; inspect its version/help |
| Subscription login required | Native login is absent or not ChatGPT | Use the native login flow; do not copy tokens or enable API fallback |
| Sol XHigh absent in deep doctor | CLI model metadata lacks the exact profile | Record the unavailable profile; do not silently substitute another root model |
| Mercury degraded | External root absent, missing credentials, validation failure or subprocess error | Keep deterministic fallback; inspect sanitized reason and existing external adapter |
| Timeout/cancel | Wrapper deadline or cancellation request | Confirm process ended and inspect artifacts before deciding whether a new run is appropriate |
| Completed but no accepted app | Native completion is not acceptance | Run the independent evaluator and relevant project checks |
| Empty/unknown usage | Native root stream or gateway completion/usage is missing/incomplete | Keep `null`; inspect separate root and all-request evidence |
| Budget exhausted | Shared inference-request cap includes probes/root/gateway-routed helpers | Preserve partial artifacts; do not silently raise the frozen limit |

## Mercury: Windows Node shutdown and proxy diagnosis

The initial Windows Node process crashed before a successful decision response. A natural-exit wrapper fixed that shutdown path without modifying the trusted external installation. A subsequent free-only smoke returned HTTP 403. The corrected current bridge forwards the user's existing Windows system proxy to Node using `--use-env-proxy`, without logging values or editing global settings. A real typed smoke then returned `OBSERVED`, one successful call, one inference attempt and verified usage cost zero.

This does not rewrite old run evidence: the earlier frozen benchmark still has zero successful Mercury calls and remains degraded for that component. For a new failure, inspect the actual per-run result and existing proxy configuration privately; do not dump environment/proxy values or create a new global proxy. HTTP 403 does not authorize paid fallback or token copying. A corrected adapter needs a new frozen experiment before it can be compared fairly.

An explicit `doctor --mercury-root <trusted-root> --live-mercury` can recheck the integration once its environment has materially changed. It is a real provider request and must retain free-only policy. Ordinary `doctor` is model-free.

## Installer refuses an update

The offline installer protects edited managed files, unknown global-block changes, manifest ownership and link/junction boundaries. Save local edits, compare the package and reconcile the managed region. `--replace-edited`, uninstalling or deleting the manifest is not a routine conflict-resolution strategy. Existing customized browser routing should be preserved deliberately.

## Run inspection

```powershell
python codex-flow.py --repo <project> runs list
python codex-flow.py --repo <project> runs show <run-id>
python codex-flow.py --repo <project> runs replay <run-id>
```

Replay reads saved JSONL and reports event/error counts and available root usage. It does not replay task execution. Redacted diagnostics may omit the raw cause; collect only the minimum permitted local evidence without exporting credentials or authenticated payloads.

## Windows deny-path and native worker failures

Protected paths must already exist. Case03 was aborted when Windows SDK created directories for future deny targets; keep that record immutable. Reciprocal per-arm deny policies also interfered through shared `CodexSandboxUsers` ACLs. The benchmark therefore uses one identical existing-target denylist for every arm, protecting the evaluator and prior solutions while explicitly leaving current-peer read isolation soft/degraded. Do not repair an active frozen run with new ACL rules.

Parallel parents cannot use the current single-agent ephemeral setting because native workers need a persisted parent rollout. SQLite/log paths are physically project-local, but the native CLI can rehydrate historical thread metadata from the shared `CODEX_HOME` rollout container into the local database. Unrelated historical working-directory metadata was observed. Separate paths are not proof of isolated native contexts/log contents; this is a platform blocker for strict independent profiles.

Do not repeat broad database queries, enumerate historical working directories or open unrelated rollouts to diagnose it. Never publish native databases, journals/WAL files or raw native logs. An audit limited to each execution's own native sessions is pending after A/B terminates; there is no established evidence of actual cross-arm solution reading. The frozen runtime remains unchanged. A generated role file or failed spawn is likewise not proof of helper execution; retain the failure and report degraded multi-agent evidence.

The local subscription gateway accepts only a fresh per-run nonce and fixed subscription routes. If transport rejects a call, inspect its fixed metadata reason without logging authorization headers, nonce or raw request/response bodies. A different request model/effort is observable transport evidence, not an independent agent identity.
