# Packaging provenance and post-benchmark portability patch

This copy originated from case02 arm A, anonymous review ID `solution-2`. It was initially copied byte-for-byte. **The packaged demo now contains the post-benchmark portability correction below and is no longer byte-identical to the evaluated source.** `original_code_files` in provenance retain the accepted snapshot hashes; current `code_files` identify the packaged derivative. The initial packaging operation executed no application or tests.

The historical [case02 record](../../../benchmarks/case02/results.json) reports an accepted artifact scored 95/100, 35 submitted tests passed, 57 independent native checks with zero failures, 25/25 frozen headless points and passed geometry checks. Its execution status remains `timed_out`. The patch does not change that evaluation, frozen runtime, original source or preserved archives.

## Post-benchmark fingerprint portability correction

The original `sha256(repr(tree))` fingerprint included platform-dependent last bits from floating-point math. Ubuntu reproduced five fixture fingerprint failures while the ASCII frame bytes still matched. The corrected 16-character fingerprint hashes versioned canonical JSON containing the full seed, ordered XYZW vertices, segment topology/radii and leaf XYZW/size/attachment/tone. Floating fields use nine fixed decimal places with negative zero normalized. This is an identity precision policy; the geometry passed to generation/projection/rendering is not rounded or changed.

Manifest `tree_fingerprint` values are pinned measurements from the isolated Linux run, not recalculated expected values inside tests. `original_tree_fingerprint` preserves the historical Windows values. Every ASCII fixture and its frame SHA256 remains unchanged. The regression test checks one-ULP stability, signed zero and meaningful geometry/W/topology/thickness/foliage/seed changes.

Verification used a fresh standalone bubblewrap namespace with no network, host home, auth or other repository binds. Ubuntu Python 3.14.4 ran 36 tests: 35 passed; one Windows-only console-flags test skipped. The exact packaged `tools/check_examples.py` then succeeded with 36 solo tests, 47 flow tests and 18 real module render calls checking all modes, ASCII/dimensions/repeat/seed. Inputs were read-only; the combined checker used RAM-only scratch copies because flow tests write temporary files in their cwd. No host application, Windows SDK, protected Harness runtime or model was invoked. Updated Windows/remote CI results remain pending.

Patch identity SHA256: `e4dbf4b4b944b557a74c9e3b244c43c50fc1d1b0fed94ae3bf2d0422dc2dbe38`. This hashes the canonical mapping of original/current changed-code hashes plus the current fixture-manifest hash; docs/provenance are excluded to avoid self-reference. Exact per-file hashes and test boundaries are in `provenance.json`.

## Omitted generated artifacts

Runtime exports, performance output, raw logs/terminal recordings, Git/native state, home/temp/cache and bytecode are excluded. Original README links to `TEST_REPORT.md` and `examples/benchmark.json` point here rather than suggesting raw historical reports are shipped. Tools that regenerate examples or create new exports remain available but were not run. Only fingerprint metadata in the fixture manifest changed; original snapshots were not modified.
