"""One finite, offline command: python scripts/smoke.py."""

from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    result = subprocess.run([sys.executable, "-m", "ascii_tree", *args], cwd=ROOT,
                            input=b"", capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))
    return result.stdout


def main():
    run("--help")
    frames = []
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
        for mode in ("2d", "3d", "4d"):
            path = Path(directory) / f"{mode}.txt"
            args = ("render", "--seed", "42", "--mode", mode, "--width", "100", "--height", "40")
            run(*args, "--output", str(path))
            data = path.read_bytes()
            if data != run(*args) or len(data.splitlines()) != 40 or any(len(row) != 100 for row in data.splitlines()):
                raise RuntimeError(f"{mode}: nondeterministic bytes or invalid dimensions")
            if not data.isascii() or b"\x1b" in data or b"\r" in data:
                raise RuntimeError(f"{mode}: not clean ASCII/LF")
            frames.append(data)
        turned = run("render", "--mode", "4d", "--angle4d", "65")
        if len(set(frames + [turned])) != 4:
            raise RuntimeError("projections / XW rotation did not differ")
        other = run("render", "--seed", "7")
        if other == frames[1]:
            raise RuntimeError("seed did not change the tree")
    print("PASS: help; 3 modes; deterministic 100x40 ASCII/LF; export; XW rotation; seeds 42/7")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
