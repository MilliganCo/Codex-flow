# Cohesive CLI cohort: transport failure retained

[Русский](README.ru.md) · [Interruption record](evidence/cohort/interruption.json) · [Metadata provenance](metadata-publication.json)

**Both Ledger arms failed at native transport; both artifacts were rejected.
SafeZip was not run and remains in the fixed denominator of two.** No speed
ratio or working-CLI claim follows from the short failed runs.

| Fixed task | A seconds / status | B seconds / status | Attempts / completed A; B | Score A/B |
|---|---|---|---|---:|
| LedgerReconcile | 451.344 / failed | 63.860 / failed | 9/8; 2/1 | 0 / 40, both rejected |
| SafeZip | not run | not run | 0/0; 0/0 | not assessed |

The 40 points come from negative-input checks and do not establish a working CLI.
The [Ledger publication](ledgerreconcile-publication.json) preserves all eight
eligible files: A has seven files, B only `.gitignore`. There is no invented
SafeZip source. Canonical inputs for both tasks remain available under [canonical](canonical/).
The remaining scheduled pair was stopped after infrastructure failure; this is
an explicit protocol deviation and the primary criterion fails.

The [setup-attempt ledger](evidence/cohort/setup-attempts.json) separately retains
16 setup requests, 15 completed, with zero benchmark credit. Initial SDK admission
failed before evaluator execution; those [denial receipts](evidence/sdk-initial-denials/)
remain visible. A [fresh sibling evaluation](evidence/sdk-recovery/relocation-receipt.json)
then ran the unchanged canonical grader on the unchanged selected source.
Independent grades were sealed before identity disclosure. Grading completion
does not turn failed generators or rejected artifacts into successful tasks.
The fresh [provenance supplement](ledgerreconcile-provenance-supplement.json)
also binds source-hashes, verified-copy and the original immutable manifests.

[Frozen runtime](frozen-runtime/) contains the exact 16 source-`ae4ba13953ebe8ca997c7ae81c8e3ce3a9dfc811`
files. [Metadata publication](metadata-publication.json) adds 66 files: 16 exact
runtime files, six exact canonical inputs and 44 derived structured reports,
including failed/recovered setup and bounded synthetic proof outputs. The absent
proof03 result is not invented. Original report SHA256 and published path-redacted
SHA256 are recorded separately; embedded receipt hashes identify raw originals.

There is no accepted CLI demo in this cohort. Use the unchanged accepted
[final-cohort demos](../efficient-cli-suite-20261026-02/README.md#run-the-included-cli-demos).
Native auth/history remain shared and current-peer physical read isolation is
degraded. Raw native state/logs, maps, stdout/stderr and external controller code
are excluded. Unknown usage, actual API cost and subscription quota delta are not
filled with estimates. Later cohorts retain separate IDs and never replace this
failure.
