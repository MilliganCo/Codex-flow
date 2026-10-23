"""13-second native-console tour with a reviewable local evidence file.

Run explicitly in Windows Terminal or a POSIX TTY, never from a pipeline.
The normal decoder polls the real keyboard; the tour injects regular app keys.
"""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.state import Explorer
from ascii_tree.terminal import NativeTerminal, run_view


class RecordedTerminal(NativeTerminal):
    def __init__(self):
        super().__init__()
        self.frames = []
        self.entered = self.restored = False

    def __enter__(self):
        super().__enter__()
        self.entered = True
        return self

    def draw(self, rows):
        super().draw(rows)
        self.frames.append({"status": rows[0].rstrip(), "width": len(rows[0]), "height": len(rows)})

    def __exit__(self, *args):
        super().__exit__(*args)
        self.restored = True


def main():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("Requires a real TTY. Use python tools/smoke.py for the headless check.", file=sys.stderr)
        return 2
    terminal = RecordedTerminal()
    state = Explorer()
    result = run_view(state, terminal, fps=8, demo=True)
    evidence = {"exit_code": result, "entered": terminal.entered,
                "restored": terminal.restored, "frames": terminal.frames,
                "note": "Native console output + timed app keys; not a physical keyboard/resize test."}
    directory = ROOT / ".tmp"
    directory.mkdir(exist_ok=True)
    path = directory / "terminal-tour.json"
    path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    statuses = [frame["status"] for frame in terminal.frames]
    passed = (result == 0 and terminal.entered and terminal.restored
              and all(any(f"| {mode} |" in status for status in statuses)
                      for mode in ("2D", "3D", "4D"))
              and state.seed == 43 and state.angle4d > 15)
    print(f"{'PASS' if passed else 'FAIL'}: native terminal tour; evidence: {path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
