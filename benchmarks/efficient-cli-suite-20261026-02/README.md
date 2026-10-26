# Final two-task CLI cohort

[Русский](README.ru.md) · [Exact evidence inventory](metadata-publication.json) · [Series summary](evidence/cohort/series-result.json)

**Both Solo (A) and Flow (B) completed both tasks, and all four unchanged
applications scored 100/100. The requested acceleration without quality loss
was not achieved.** Flow's observed elapsed time was about 20.0% longer for Ledger
and 30.5% longer for SafeZip.

| Fixed task | A seconds | B seconds | Physical requests A/B | Completed requests A/B | Independent score A/B |
|---|---:|---:|---:|---:|---:|
| LedgerReconcile | 599.609 | 719.281 | 13 / 23 | 13 / 22 | 100 / 100 |
| SafeZip | 925.687 | 1207.984 | 15 / 23 | 15 / 23 | 100 / 100 |

Both native arms exited successfully inside each task's fixed 1500-second,
80-physical-request limits. Ledger B had one recovered connection reset; its
failed attempt is retained, with unknown usage. There were 74 physical attempts
and 73 completed attempts across this cohort. Eight controller integrity checks
passed for each pair, and both controller policy-violation lists are empty.
Independent SDK grades were sealed before the identity map was read; the
publication then verified both execution receipts and full selected inventories.

The preregistered primary criterion requires `A seconds / B seconds >= 1.10`
for **each** fixed task, strict 100/100 acceptance in both arms, and every integrity
and policy condition. It failed: valid A/B time ratios are **0.833623** and
**0.766307**, geometric mean **0.799257**. The additive
[schema-compatible binding report](evidence/cohort/series-result-schema-addendum.json)
passed 254 guards across 142 raw input hashes. It binds the actual independent
seal layouts, complete source inventories and SDK receipts. The preliminary
summary expected optional fields absent from those seal layouts; that reporting
schema mismatch was not an experiment-integrity failure. The preliminary summary
remains unchanged, including its conservative null ratios. No task, criterion,
score, source or outcome was changed by the addendum.

## Candidate and current default

This cohort executed the exact 16 files in [frozen-runtime](frozen-runtime/),
source `f35d342ea0283d88a0befe10c3f1a4e7266e0a31`. The snapshot includes a test-proposal
helper policy. It is preserved as a rejected candidate. Current source restores
the balanced context-only `reviewer/high` risk review; the chief writes and
integrates application files, and the reviewer shell tool is disabled.

[Ledger's bounded overhead audit](evidence/ledger04-overhead-audit.json) observed
B's 20 completed XHigh and two completed High requests, plus one High reset.
Two helper test proposals (11 then 10 test IDs) were integrated twice. The chief
issued 16 commands, including two early read failures and a public-test failure
followed by repair. No exact duplicate commands or request payloads were found.
These observations identify overhead in this run; they do not prove a universal
cause. Root-native usage and provider request usage have different boundaries and
are not summed. Two provider XHigh records lack a native-agent binding.

The nine synthetic [rate/recovery cases](evidence/proofs/native-rate-limit-proof-20261026-05/proof-result.json)
and separate [real native prerequisite](evidence/prerequisites/efficient-prerequisite-20261026-02/prerequisite-result.json)
passed 24 checks with eight real Sol requests, an observed High child and public
CLI/SDK checks. They establish bounded recovery/integration evidence and carry
zero benchmark credit. Recovery stays opt-in; it reserves each physical attempt
against the same hard request/deadline budget. There is no gateway replay or
backend exactly-once guarantee.

## Run the included CLI demos

The independent SDK evaluations exercised the included README demo commands;
publication did not rerun or repair the applications. From the repository root,
use Python 3.12 and fresh output paths. No model account or package installation
is needed. Replace `B` with `A` to inspect the other accepted application.

```powershell
Push-Location benchmarks/efficient-cli-suite-20261026-02/solutions/ledgerreconcile/B
python -m ledgerreconcile --orders examples/orders.csv --payments examples/payments.csv --output example-report.json
Pop-Location
Push-Location benchmarks/efficient-cli-suite-20261026-02/solutions/safezip/B
python -m safezip inspect examples/sample.zip
python -m safezip extract examples/sample.zip --dest sample-output
Pop-Location
```

Choose a new absent output file or extraction directory for another run. These
commands write only inside the selected demo directory. See each unchanged
application README for platform/filesystem requirements.

## Evidence and limits

[Ledger publication](ledgerreconcile-publication.json) contains 17 application
files, three exact verifier files and seven derived reports. [SafeZip publication](safezip-publication.json)
contains 16 application files, three exact verifier files and seven derived
reports. [Metadata publication](metadata-publication.json) adds 16 exact frozen
runtime files, six exact canonical inputs and 46 derived structured reports.
The separate [addendum publication](series-addendum-publication.json) binds one
additional derived metadata report.
Manifests separately record original raw and published SHA256 values; embedded
receipt hashes refer to the original reports. No source/checker bytes were fixed.

The official CLI was `0.164.0-alpha.11.1`, SHA256
`1103e9e09c71fa2cd0afd6d8f3b9a2d63174fe8efd7cb5bd09f1cb14ef58a098`.
Historical CLI 0.163 runs are separate cohorts, not causal comparisons. Auth,
rollout history and native state remain shared; current-peer physical read
isolation is degraded. Native databases/logs, stdout/stderr, maps and external
controller/proof scripts are excluded. Metadata paths are redacted, with original
hashes retained. Unknown aggregate usage, actual API cost and subscription quota
delta remain null; known completed-request lower bounds are separately labelled.
HTTP uses identity encoding; generic gzip does not establish token/quota savings.

Earlier [cohesive02](../cohesive-suite-20261024-02/README.md),
[resilient03](../resilient-cli-suite-20261026-01/README.md) and
[three-task stream cohort](../stream-suite-20261024-01/README.md) remain separate.
[Rollback](../../docs/rollback.md#before-the-cli-recovery-changes) uses a new checkout
at the previous reviewed private release and preserves current work.
