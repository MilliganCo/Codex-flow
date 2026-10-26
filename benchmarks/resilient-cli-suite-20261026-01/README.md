# Resilient CLI cohort: primary criterion failed

[Русский](README.ru.md) · [Summary](evidence/cohort/series-result.json) · [Metadata provenance](metadata-publication.json)

**Ledger completed with 100/100 in both arms. SafeZip B failed on its first
HTTP 429 request, so this cohort did not establish acceleration without quality loss.**
Both fixed tasks remain in the denominator; no failed branch is a speed winner.

| Task | A seconds / status | B seconds / status | Physical / completed A; B | Score A/B |
|---|---|---|---|---:|
| LedgerReconcile | 647.438 / completed | 631.282 / completed | 14/14; 14/14 | 100 / 100 |
| SafeZip | 997.438 / completed | 37.391 / failed HTTP 429 | 12/12; 1/0 | 100 / 40 rejected |

The 16.156-second Ledger difference is about 2.5% of Solo time, below the required
`A/B >= 1.10` threshold. SafeZip has no eligible time ratio. There were 41 physical
attempts and 40 completed attempts. Partial invalid-input points do not make the
failed SafeZip B artifact a working CLI. Independent SDK evaluations and seals
retain source/checker bytes, including that negative result.

The exact source-`4f794d7c9dabaecc1a1332295babf6e63c555cd0` 16-file runtime is in
[frozen-runtime](frozen-runtime/). The [real prerequisite](evidence/prerequisites/resilient-prerequisite-20261026-01/prerequisite-result.json)
passed 23 checks with nine native requests; the [synthetic HTTP recovery proof](evidence/proofs/native-http-recovery-proof-20261026-04/proof-result.json)
passed five cases. Neither has benchmark credit, and neither repairs the failed
cohort. The [later final cohort](../efficient-cli-suite-20261026-02/README.md)
completed both tasks but remained slower.

## Included CLI demonstrations

The accepted A artifacts include their original examples and README commands.
The SDK evaluation checked their real CLI behavior. Publication did not rerun apps.
From the repository root with Python 3.12 and fresh output paths:

```powershell
Push-Location benchmarks/resilient-cli-suite-20261026-01/solutions/ledgerreconcile/A
python -m ledgerreconcile --orders examples/orders.csv --payments examples/payments.csv --output demo-report.json
Pop-Location
Push-Location benchmarks/resilient-cli-suite-20261026-01/solutions/safezip/A
python -m safezip inspect examples/sample.zip
Pop-Location
```

SafeZip B has only `.gitignore`; no working demo is claimed. The application
snapshots contain 25 files total. [Ledger](ledgerreconcile-publication.json) and
[SafeZip](safezip-publication.json) manifests bind byte-identical apps/verifiers
and seven derived reports per task. [Metadata publication](metadata-publication.json)
adds 67 files: 16 exact runtime files, six exact canonical inputs and 45 derived
reports. Original and published report SHA256 values are separate.

Native auth/history are shared and current-peer physical read isolation is
degraded. Native state/logs, maps and stdout/stderr remain private. Official CLI
0.164.0-alpha.11.1 differs from older 0.163 cohorts, preventing causal pooling.
Unknown usage totals, API cost and quota delta remain null. Summary integrity
checks pass for both tasks; Ledger has an eligible ratio, while failed SafeZip
does not. No geometric mean is computed across the incomplete cohort, and
observed wall times do not establish a general performance or quota advantage.
