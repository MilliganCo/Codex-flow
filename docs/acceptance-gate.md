# External acceptance gate

[Русский](acceptance-gate.ru.md)

An owner-supplied contract can make declared checks a condition of runtime success.
The gate runs after generation through the official Windows Codex sandbox. It
does not call a model, log in, use the subscription gateway or repair a failure.
No checker is discovered or trusted automatically.

## 1. Declare the trusted checks

Review the contract and its single self-contained Python checker before use.
The checker must sit alongside the contract; its name is a relative `.py` path.
The contract has exactly these fields:

```json
{
  "schema": 1,
  "checker": "verifier.py",
  "inputs": ["sum_cli.py"],
  "min_checks": 3,
  "timeout_s": 30
}
```

`inputs` is a nonempty list of project-relative files or directories whose
contents are bound to the check. Project root, `.git`, `.codex-flow`, `.tmp` and
`.home` are excluded. Use explicit, bounded source inputs. `min_checks` is an
integer from 1 to 1000; `timeout_s` is an integer from 1 to 300. Booleans are not
integers in this contract.
Use `/` separators in contract paths, including on Windows; absolute paths,
parent traversal, duplicate inputs, links and reparse points are refused.

The runtime loads and freezes the contract and checker before generation in a
protected `.codex-flow` snapshot. Contract/checker drift is rejected. Source
inputs are hashed before and after verification; changes invalidate acceptance.
The separate `acceptance-inputs.json` stores both inventories; the acceptance
receipt binds that file through `input_inventory_sha256`.
The host reads metadata and hashes; it never imports or executes the checker or
the generated application.

## 2. Inspect, then execute

From the Codex Flow checkout, inspect the included example without executing it:

```powershell
python codex-flow.py --repo examples/acceptance-gate verify --acceptance-file examples/acceptance-gate/contract.json
```

`verify` defaults to a metadata dry run. Add `--execute` to run its declared
checker in the official sandbox, without generation or a subscription login:

```powershell
python codex-flow.py --repo examples/acceptance-gate verify --acceptance-file examples/acceptance-gate/contract.json --execute --timeout 30
```

For a project run, pass its owner-reviewed contract explicitly:

```powershell
python codex-flow.py --repo C:\work\project run "Implement the agreed change" --enable --acceptance-file C:\checks\project\contract.json --timeout 180
```

Global options such as `--repo` and `--codex` precede the subcommand. Both `run`
and `verify` accept repeatable `--protect-path C:\existing\private` arguments;
each target must already exist. These paths are added to sandbox read-denials.
The project configuration schema is unchanged.

The `run --timeout` budget covers generation and the gate together. The contract
timeout is an additional cap, bounded by the remaining task deadline. Verification
receives no new independent deadline. Cancellation or exhausted time fails closed.

## 3. Implement the checker interface

The sandbox invokes the frozen checker using an absolute Python executable:

```text
python -I -B SNAPSHOT/checker.py --workspace WORKSPACE --report SCRATCH/report.json --nonce RUNNONCE
```

The current directory is fresh scratch space. Workspace and checker snapshot
are read-only; scratch is writable. Use scratch for temporary files and output.
The checker must write a new UTF-8 JSON report with exactly this shape:

```json
{
  "schema": 1,
  "nonce": "the supplied --nonce value",
  "checks": [
    {"id": "cli.sum", "status": "passed"},
    {"id": "cli.negative", "status": "passed"},
    {"id": "cli.invalid", "status": "passed"}
  ]
}
```

Check IDs must be unique. Status is `passed`, `failed` or `skipped`. Acceptance
requires exit zero, at least `min_checks` checks and every check `passed`. Empty
reports, skips, nonzero exits, missing/stale/malformed/oversized reports, nonce or
hash drift, timeout, cancellation and incomplete output capture reject acceptance.
Stdout prose, a model's completion claim and exit zero alone cannot pass the gate.

Each check must represent an actual declared assertion. If a checker runs
unittest, inspect its machine-readable result and positive `testsRun` count;
reject zero collected tests. Merely launching unittest successfully is insufficient.

## 4. Read the result within its scope

Without `--acceptance-file`, a completed generation remains
`completed_unverified` with `accepted: false`. All configured checks passing can
promote it to `completed_verified` with `accepted: true`. Configured acceptance
rejection returns exit code `3`. There are no automatic repairs or checker retries.

The result establishes only the trusted checks declared by the owner. It does
not establish comprehensive coverage, a 100/100 quality score, or that arbitrary
checker logic is correct. A dishonest checker can report fabricated checks;
review its logic and provenance before trusting its verdict.

Network access is disabled. Real `.codex` and `.agents` directories, the existing
workspace `.codex-flow/native-state` tree and explicit protected paths are denied.
Credential-bearing environment variables are stripped
and HOME/TMP are owned scratch locations. These controls do not establish complete
host-read isolation: named workspace profiles and shared Windows sandbox state
retain platform limitations. Timeout cleanup uses best-effort process-tree
termination; independent termination of every descendant is not proved.

The gate does not prove a swarm advantage. The current `reviewer/high` role is an
independent acceptance-risk review; prior evidence does not establish that a team
of smaller coding models accelerates development without reducing quality.
