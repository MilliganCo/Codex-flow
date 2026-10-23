"""One-command, finite, offline smoke test: python smoke_test.py."""

from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def run(*args):
    return subprocess.run([sys.executable, "-m", "ascii_tree", *args], cwd=ROOT,
                          input=b"", capture_output=True, timeout=10)


def main():
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
        frames = []
        for mode, angle in (("2d", "0"), ("3d", "0"), ("4d", "0"), ("4d", "55")):
            path = Path(directory) / f"{mode}-{angle}.txt"
            result = run("render", "--seed", "42", "--mode", mode, "--angle4", angle,
                         "--width", "100", "--height", "40", "--output", str(path))
            assert result.returncode == 0, result.stderr
            data = path.read_bytes()
            assert len(data.splitlines()) == 40
            assert all(len(row) == 100 for row in data.splitlines())
            assert all(c == 10 or 32 <= c <= 126 for c in data)
            assert b"\x1b" not in data
            frames.append(data)
        assert len(set(frames)) == 4, "Projections did not change"
        assert run("render", "--seed", "42", "--mode", "3d").stdout == frames[1]
        assert run("render", "--seed", "7", "--mode", "3d").stdout != frames[1]
        view = run("view")
        assert view.returncode == 2 and b"TTY" in view.stderr
        assert run("--help").returncode == 0
    print("PASS: 2D / 3D / 4D, XW rotation, seeds 42/7, exact ASCII exports, determinism, non-TTY, help")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
