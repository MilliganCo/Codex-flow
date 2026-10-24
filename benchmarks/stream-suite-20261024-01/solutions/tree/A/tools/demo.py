"""Record a repeatable UI scenario using the application's real key handlers.

This is an offline screen storyboard, not a recording of an OS terminal.
The real interactive command is `python -m ascii_tree view`.
"""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.app import Explorer
from ascii_tree.model import generate_tree


def main():
    destination = ROOT / "artifacts" / "demo"
    destination.mkdir(parents=True, exist_ok=True)
    app = Explorer(generate_tree(42))
    events = []
    original = app.tree

    def snapshot(name, keys, columns=100, rows=40):
        for key in keys:
            app.handle_key(key)
        path = destination / f"{len(events):02d}-{name}.txt"
        path.write_bytes((app.screen(columns, rows) + "\n").encode("ascii"))
        events.append(dict(screen=path.name, keys=keys, seed=app.tree.seed,
                           mode=app.settings.mode, angle4d=app.settings.angle4d,
                           width=columns, height=rows))

    snapshot("start-3d", [])
    snapshot("same-tree-2d", ["1"])
    snapshot("same-tree-4d", ["3"])
    snapshot("xw-45", ["]"] * 6)
    snapshot("orbit-zoom", ["right", "right", "up", "+"])
    snapshot("help", ["h"])
    assert app.tree is original
    snapshot("resize-narrow", ["h"], 24, 10)
    snapshot("reset", ["r"])
    snapshot("new-seed43", ["g"])
    app.handle_key("q")
    assert app.quitting
    (destination / "events.json").write_text(json.dumps(events, indent=2) + "\n", encoding="ascii")
    print(f"PASS: {len(events)} UI screens in artifacts/demo; same object through mode/angle changes")


if __name__ == "__main__":
    main()
