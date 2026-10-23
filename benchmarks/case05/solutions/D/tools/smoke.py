"""Finite, offline smoke test: python tools/smoke.py (from the project root)."""

from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
        frames = []
        for mode, angle in (("2d", "0"), ("3d", "0"), ("4d", "0"), ("4d", "35")):
            target = Path(directory) / f"{mode}_{angle}.txt"
            subprocess.run([sys.executable, "-m", "ascii_tree", "render", "--seed", "42", "--mode", mode,
                            "--angle4d", angle, "--width", "100", "--height", "40", "--output", str(target)],
                           cwd=ROOT, check=True, timeout=15)
            data = target.read_bytes()
            if len(data) != 4040 or len(data.splitlines()) != 40 or not all(
                    len(row) == 100 and all(32 <= c <= 126 for c in row) for row in data.splitlines()):
                raise RuntimeError(f"Invalid ASCII frame: {mode}")
            frames.append(data)
        if len(set(frames)) != 4:
            raise RuntimeError("2D / 3D / 4D / XW rotation must produce distinct projections")
        result = subprocess.run([sys.executable, "-m", "ascii_tree", "view"], cwd=ROOT,
                                input=b"", capture_output=True, timeout=15)
        if result.returncode != 2 or b"interactive TTY" not in result.stderr:
            raise RuntimeError("Non-TTY view must exit promptly with guidance")
    print("PASS: 2D, 3D, 4D, XW rotation, exact ASCII dimensions, and non-TTY shutdown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
