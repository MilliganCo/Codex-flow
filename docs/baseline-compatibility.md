# Baseline audit and compatibility

Audit date: 2026-10-23. This extends the existing Codex Flow 1.2.0 distribution; it does not replace the installed workflow or its managed global blocks.

| Inspected component | Recorded result | Treatment |
|---|---|---|
| Original 1.2.0 distribution | 29/29 package checksums matched | Preserved as the source baseline |
| Installed skill | 12/13 files matched the distribution; the browser reference had a local customization | All 13 installed files preserved; no forced reinstall |
| Legacy helper | Existing install/uninstall/doctor/init/new-task contracts and 56 tests | Retained in `payload/codex-flow/`; included in the current offline suite |
| New execution layer | Separate `codex-flow.py` and `runtime/codex_flow/` | Explicitly enabled project runtime; Mercury and optimizer default off |
| Existing Mercury adapter | External free-only Decisions adapter with catalog/build/provider/cost checks | Referenced without copying provider code or credentials |
| Existing Harness² overlay | Restricted, sealed lab; its model/effort policy does not admit the requested XHigh profile | Not resealed, restarted or repurposed; bounded inspired probes are a separate implementation |

The pre-change backup contains the installed skill, installation manifest, global instruction file and configuration, with checksums. It stays local because it contains private configuration. Use [rollback](rollback.md) to compare selected files without overwriting concurrent user changes.

## Environment actually inspected

Windows Python 3.12.10, Node 24.15.0, Git 2.54.0, PowerShell 7 and the Desktop-bundled native CLI `0.163.0-alpha.11.1` were observed. The npm CLI shim failed its version preflight; it was not reinstalled. Native subscription login/model metadata and real generation were verified separately. A newer installed CLI was inspected only for help/version; no upgrade was performed.

The original lab's 25 Python and 12 Node checks and its model-free sandbox preflight passed during the initial audit. Its existing Windows seal check reported four drift paths and failed; that failure was retained, not resealed into a passing baseline. No scheduled generation job was replayed to test health. These are initial audit records, not a promise that a live external service remains available.

## Preservation boundary

No deliberate global configuration, skill, plugin, browser, environment or scheduler patch was applied. All runtime overrides are process-local. Native authentication is owned by the official CLI; the implementation does not open or copy its token file. Native login can refresh its own session state, so “no credential copy” is not a claim that every native-owned state byte is frozen.

Final checksum comparison preserved all 13 installed skill files, the global instruction file and installation manifest (15 unchanged files). `config.toml` differed only in project-registration semantics; all non-project configuration, including model and safety settings, matched the backup. The registration change was not attributed to a specific concurrent actor, and no blind restore was performed.

The source checkout preserves the original distribution notes locally. Superseded notes containing personal paths are excluded from publication. The private publication checkout is a reviewed file allowlist with separate curated history; the original source history is not pushed. A targeted working-tree and full-history secret/path scan is supplemented by provenance review and excludes backups, native databases, raw journals and private instructions.

Current test, experiment and CI status is recorded in [acceptance status](acceptance-status.md). Historical 1.2.0 reports do not validate new runtime code. Separate capability proofs do not retroactively change frozen benchmark outcomes.
