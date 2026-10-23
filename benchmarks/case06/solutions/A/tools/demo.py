"""Record the production event loop using deterministic input and a fake clock.

This is a scripted UI replay, not a capture of a real Windows Terminal session.
The actual console is checked separately; see TEST_REPORT.md.
"""

from pathlib import Path

from ascii_tree.app import run_view
from ascii_tree.state import ExplorerState
from tests.support import FakeClock, FakeTerminal


def main() -> None:
    terminal = FakeTerminal(
        events=(["1"], ["2", "right", "up"], ["3"], ["]"] * 6,
                ["h"], ["h", " "], [], [" "], ["r"], ["g"], ["q"]),
        sizes=((100, 40),),
    )
    state = ExplorerState()
    run_view(state, terminal=terminal, clock=FakeClock())
    text = "ASCII TREE EXPLORER - DETERMINISTIC UI REPLAY\n"
    text += "Production event loop; simulated terminal/clock (not a live screen recording).\n"
    text += "Input: 1; 2 Right Up; 3; ] x6; H; H Space; wait; Space; R; G; Q\n\n"
    for index, frame in enumerate(terminal.frames, 1):
        text += f"FRAME {index:02d}\n" + "=" * 100 + "\n" + frame + "\n"
    directory = Path(__file__).resolve().parents[1] / "examples"
    directory.mkdir(exist_ok=True)
    output = directory / "interactive_demo.txt"
    output.write_bytes(text.encode("ascii"))
    print(f"Saved {len(terminal.frames)} UI frames to {output.relative_to(directory.parent)}")


if __name__ == "__main__":
    main()
