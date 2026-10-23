# Historical verification — case02 arm B

**Packaging-only document, added after evaluation.** The accepted original snapshot linked to `VERIFICATION.md` but did not contain that file. This summary repairs that link; it does not change source code, benchmark score, process status or the original evaluation. No application, test, import or CI execution occurred while packaging this copy.

The sanitized [case02 results](../../../benchmarks/case02/results.json), arm B / anonymous ID `solution-1`, record:

| Historical evidence | Actual result |
|---|---|
| Submitted automated tests | 47 passed |
| Independent Windows native/ConPTY checks | 57 checks, zero failures |
| Frozen independent headless checks | 25/25 points |
| Independent geometry | Passed for seeds 42 and 137 |
| Artifact review | Accepted, 97/100; original process `timed_out` |

Geometry verification covered actual XYZW vertices with variable W, nonplanar XYZ, the XW rotation, an explicit 4D→3D→2D perspective pipeline, and unchanged geometry when changing view. Frame differences were not the sole proof of 4D. These statements describe the historical evaluated artifact, not an independently rerun result for this copied directory or a claim about a particular terminal font.

Case02 had zero successful Mercury calls, zero upstream Harness² calls, two Harness²-inspired planning probes in B, and unconfirmed native helper execution. This application result does not establish the causal benefit or speed of a fully active multi-agent integration.

Raw native logs/databases/journals and original terminal streams are excluded from the package. New offline/CI verification must be recorded with its own command, environment and timestamp. See [PACKAGING.md](PACKAGING.md) and `provenance.json` for the copy boundary and code hashes.
