"""Finite, offline end-to-end check: python tools/smoke.py."""

from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.model import generate_tree
from ascii_tree.state import ExplorerState


def run(*args):
    result = subprocess.run([sys.executable, "-m", "ascii_tree", *args], cwd=ROOT,
                            input=b"", capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result


def main():
    temporary_root = ROOT / ".tmp"
    temporary_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="smoke-", dir=temporary_root) as directory:
        run("--help")
        frames = []
        for mode, angle in (("2d", "0"), ("3d", "0"), ("4d", "0"), ("4d", "40")):
            path = Path(directory) / f"{mode}-{angle}.txt"
            args = ("render", "--seed", "42", "--mode", mode, "--angle4", angle,
                    "--width", "100", "--height", "40")
            run(*args, "--output", str(path))
            data = path.read_bytes()
            assert len(data) == 101 * 40
            assert all(len(row) == 100 for row in data.splitlines())
            assert all(c == 10 or 32 <= c <= 126 for c in data)
            assert run(*args).stdout == data, "non-deterministic export"
            frames.append(data)
        assert len(set(frames)) == 4, "projections must differ"
        other = run("render", "--seed", "7", "--mode", "3d").stdout
        assert other != frames[1], "seed must change the tree"
        fallback = run("view", "--width", "1", "--height", "1")
        assert len(fallback.stdout) == 2 and b"No interactive TTY" in fallback.stderr
        state = ExplorerState(generate_tree(42))
        original = state.tree
        for key in ("1", "2", "3", "]", "right", "r"):
            state.handle_key(key)
            assert state.tree is original
    print("PASS: CLI startup; 2D/3D/4D ASCII exports; repeatable bytes; XW rotation; seed variety.")
    print("PASS: same object across modes; 1x1 non-TTY fallback; clean shutdown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
