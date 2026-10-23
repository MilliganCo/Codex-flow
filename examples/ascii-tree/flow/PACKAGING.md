# Packaging provenance

This copy is case02 arm B, anonymous review ID `solution-1`. Application, test, script and launcher code was copied byte-for-byte from the accepted snapshot. `provenance.json` records raw and normalized-LF SHA256 hashes. No code was executed or imported during packaging, and no test/CI result is claimed for this new copy.

## Omitted generated artifacts

Original runtime exports, raw test/performance logs, terminal recordings, Git/native state, home/temp/cache and bytecode are excluded. The original README's links to `artifacts/verified-terminal/report.json` and `artifacts/verified-terminal/session.ansi` now point here. Those historical files are not shipped or represented as fresh verification. [VERIFICATION.md](VERIFICATION.md) supplies a clearly labeled historical evaluation summary and repairs the README's previously missing verification link.

Deterministic `examples/*.txt` and `examples/manifest.json` are included unchanged because existing tests require those exact fixtures. `docs/DEMO.md` remains the original manual demonstration script; it was not performed during packaging. Original snapshots and benchmark scores were not modified.
