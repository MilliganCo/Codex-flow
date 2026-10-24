# Independent native interaction protocol

Prepared for case10 on 2026-10-24. Evaluation root: `evaluation-case10-20261024`; read-only verifier root: `verification-runtime-20261024-10`. The unchanged rubric retains 26 criteria and five critical gates.

This protocol freezes the existing 57-check neutral Windows ConPTY sequence for
the two anonymous submissions. It is preparation, not an execution result. The
checker receives no author, model, strategy, prior score, or identity mapping.
Neither submission nor its frozen evaluator results may be repaired.

## Execution boundary

Run only after both generators have stopped and the unchanged frozen evaluator
has produced `frozen-N/evaluation.json`. Use the reviewed launcher with N=23 or 24
and an explicit new checker in the new read-only verification directory. The
evaluation directory is writable; the verification directory is read-only;
user `.codex` and `.agents` directories are denied. Network is disabled. The
existing official CLI owns its setup; no auth files are read/copied by the
controller. Use the absolute current Python executable. The outer SDK command
has a 600-second bound and never retries or overwrites an existing attempt.

Retain raw stdout, transcripts, exports, checker/support hashes, source hashes,
return codes, durations, and any timeout or incomplete status. Raw records remain
local. This is a real console/input check, not a visible-font or GUI screenshot
assessment. Original console input-mode flags cannot be queried after exit.

## Permitted API adaptation

After disclosure of anonymous source only, inspect each application's own README,
CLI help/source contract and public input state. Record its documented Python
module, `view`/`render` spelling and flags, initial yaw/pitch/XW angle, rotation
increments, zoom factor, next-seed rule, export directory/name convention,
startup/help markers, and image viewport after UI chrome. Use the same numerical
documented state in the headless oracle and interactive session. These are API
adapters, not application behavior changes. Never import an app on the host.

Where the sequence uses the label XW, use the application's documented supported
space/W plane and record its actual name. The task permits XW, YW or ZW; this API
adaptation must not add a requirement to implement all three planes.

The optional `conpty_case10_neutral.py` contains only reviewed low-level plumbing
and generic module bootstrap. Copy it byte-identically into the read-only verifier
directory when used. Its only functional adaptation is validating a dotted Python
module name instead of hardcoding one package. The bootstrap rebinds standard
handles to the attached console. It does **not** call `SetConsoleCtrlHandler`,
`SetConsoleMode`, set input/processed-control flags, reset signal inheritance,
inject Python exceptions, monkeypatch application input, or repair control handling.

If a documented equivalent API cannot be established, record `not_assessed` with
the exact missing evidence; do not invent an adapter or score. A confirmed missing
required capability is a failure, not `not_assessed`. Any such limitation prevents
a claim of a complete 57-pass protocol. Native failure never repairs or replaces
the unchanged frozen evaluator result.

## Fixed sequence and check accounting

Start at seed 42, 2D, terminal 100×40. Use the application's documented initial view
and actual image viewport. Every ordinary export contributes two top-level checks:
exact expected dimensions, then rectangular printable ASCII with LF only. Each
oracle comparison contributes one additional top-level check. The headless oracle
uses the same tree seed/state, actual image dimensions and documented CLI.

| Check numbers | Action and required result |
|---|---|
| 1 | Start the documented module viewer; observe its actual startup marker. |
| 2–4 | Select 2D, export; dimensions, ASCII/LF, exact headless oracle. |
| 5–7 | Select 3D, export; dimensions, ASCII/LF, exact oracle. Within check 7 also send Right+Up, export and compare with one yaw/pitch increment, then Left+Down and export: changed view, correct oracle, reverse restores. These two additional exports must remain bounded ASCII but add no top-level checks. |
| 8–10 | Select 4D, export; dimensions, ASCII/LF, exact oracle. |
| 11 | The collected 2D/3D/4D projections are three distinct frames of the same seed. |
| 12–14 | Send literal `]`, export; dimensions, ASCII/LF, exact one-step XW oracle. |
| 15–17 | Send literal `[`, export; dimensions, ASCII/LF, reverse XW to initial oracle. |
| 18–20 | Send Right+Up, export; dimensions, ASCII/LF, one-step yaw/pitch oracle. |
| 21–23 | Send `+`, export; dimensions, ASCII/LF, documented zoom-factor oracle. |
| 24–26 | Send `-`, export; dimensions, ASCII/LF, reverse-zoom oracle. |
| 27 | Send `h`; observe the help marker in new console output. |
| 28–30 | Send `?` to close help, export; dimensions, ASCII/LF, unchanged view oracle. |
| 31–33 | Send Space, wait 0.45 s, send Space and export; dimensions, ASCII/LF, animation changed the prior rotated frame. |
| 34–36 | Wait 0.15 s, export; dimensions, ASCII/LF, paused frame is byte-identical. |
| 37–39 | Send `r`, export; dimensions, ASCII/LF, reset orientation/scale/time oracle. |
| 40–42 | Send `g`, export; dimensions, ASCII/LF, documented new-seed oracle. |
| 43–45 | Resize actual ConPTY to 30×12, wait 0.3 s, export; documented image dimensions, ASCII/LF, same new-seed/state oracle. |
| 46–48 | Resize to 1×1, wait 0.3 s, export; dimensions 1×1, ASCII/LF, matching oracle. |
| 49–51 | Resize back to 100×40, wait 0.3 s, export; restored image dimensions, ASCII/LF, matching oracle. |
| 52–53 | Send `q`; actual exit code 0, cursor-show and alternate-screen-leave sequences in transcript. |
| 54–55 | Fresh identical viewer session; send literal Esc byte 0x1B; actual exit code 0 and both restoration sequences. |
| 56–57 | Fresh identical viewer session; send literal Ctrl+C byte 0x03 through ConPTY; actual exit code 0 or 130 and both restoration sequences. |

The default native condition/export/exit wait is 5 seconds; the headless oracle
timeout is 15 seconds. Preserve this ordering, physical resize calls, input bytes,
timings, accepted exit codes, and the embedded 3D round trip. Restoration requires
both `ESC[?25h` and `ESC[?1049l` in the real transcript. Do not substitute a direct
application key handler, fake terminal, timed in-app tour, explicit signal repair,
or `KeyboardInterrupt` mock for native input.

At the first execution exception, retain the original error and partial evidence;
record `smoke completion: fail` and mark the protocol incomplete. Do not fill
unexecuted checks with passes or normalize a shorter run to 57. A clean report
requires exactly 57 checks, all passed, all source hashes unchanged, and no runtime
repairs. Report substantive geometry, morphology and aesthetics separately under
the unchanged rubric; this protocol neither awards nor revises those scores.
