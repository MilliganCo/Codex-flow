# Packaging provenance

This copy is case02 arm A, anonymous review ID `solution-2`. Application, test, tool and launcher code was copied byte-for-byte from the accepted snapshot. `provenance.json` records raw and normalized-LF SHA256 hashes. No code was executed or imported during packaging, and no test/CI result is claimed for this new copy.

The historical [case02 record](../../../benchmarks/case02/results.json) reports an accepted artifact scored 95/100, 35 submitted tests passed, 57 independent native checks with zero failures, 25/25 frozen headless points and passed independent geometry checks. The original execution status remains `timed_out`. These are historical evaluation results, not fresh packaging verification.

## Omitted generated artifacts

Original runtime exports, performance output, raw logs/terminal recordings, Git/native state, home/temp/cache and bytecode are not included. The original README's links to `TEST_REPORT.md` and `examples/benchmark.json` now point here, so historical statements are not mistaken for newly shipped raw reports. The original supporting statements are retained as snapshot documentation; current authoritative summarized evidence is the case02 JSON above.

Deterministic `examples/*.txt` and `examples/manifest.json` are included unchanged because the existing example tests require those exact fixtures. Tools that regenerate examples or create new exports remain available but were not run. Original snapshots were not modified.
