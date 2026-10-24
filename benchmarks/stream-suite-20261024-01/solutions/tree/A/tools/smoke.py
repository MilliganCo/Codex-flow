"""One offline command: python tools/smoke.py. No files or TTY needed."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.app import Explorer
from ascii_tree.model import generate_tree


def main():
    frames = {}
    for seed in (42, 43):
        for mode, angle in (("2d", 0), ("3d", 0), ("4d", 0), ("4d", 45)):
            args = [sys.executable, str(ROOT / "ascii-tree.py"), "render",
                    "--seed", str(seed), "--mode", mode, "--angle4d", str(angle),
                    "--width", "100", "--height", "40"]
            result = subprocess.run(args, input=b"", capture_output=True, cwd=ROOT, timeout=15)
            assert result.returncode == 0, result.stderr
            data = result.stdout
            assert len(data) == 4040 and len(data.splitlines()) == 40
            assert all(len(line) == 100 for line in data.splitlines())
            assert all(c == 10 or 32 <= c <= 126 for c in data)
            frames[seed, mode, angle] = data
    assert frames[42, "4d", 0] != frames[42, "4d", 45]
    assert frames[42, "3d", 0] != frames[43, "3d", 0]
    app = Explorer(generate_tree(42))
    tree = app.tree
    for key in ("1", "2", "3", "]", "+", "h", "h", " "):
        app.handle_key(key)
    app.tick(.1)
    assert app.tree is tree and app.settings.angle4d > 7.5
    assert len(app.screen(1, 1)) == 1
    app.handle_key("q")
    assert app.quitting
    print("PASS: 8 headless frames, 2 seeds, 3 modes, XW rotation, UI state, 1x1 and quit")


if __name__ == "__main__":
    main()
