"""One command, finite, offline smoke test: python scripts/smoke.py."""

from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    result = subprocess.run([sys.executable, "-m", "ascii_tree", *args], cwd=ROOT,
                            input=b"", capture_output=True, timeout=10)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("ascii", errors="replace"))
    return result


def main():
    (ROOT / ".tmp").mkdir(exist_ok=True)
    run("--help")
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
        frames = []
        for mode, angle in (("2d", 0), ("3d", 0), ("4d", 0), ("4d", 45)):
            target = Path(directory) / f"{mode}-{angle}.txt"
            args = ("render", "--seed", "42", "--mode", mode, "--angle4", str(angle),
                    "--width", "100", "--height", "40")
            run(*args, "--output", str(target))
            data = target.read_bytes()
            if len(data) != 4040 or len(data.splitlines()) != 40 or b"\x1b" in data:
                raise RuntimeError("Wrong frame dimensions or ANSI in export")
            if not all(c == 10 or 32 <= c <= 126 for c in data):
                raise RuntimeError("Non-printable/non-ASCII frame")
            if data != run(*args).stdout:
                raise RuntimeError("Render is not deterministic")
            frames.append(data)
        if len(set(frames)) != 4:
            raise RuntimeError("Modes or XW rotation do not change projection")
        if frames[1] == run("render", "--seed", "137").stdout:
            raise RuntimeError("Seed does not change image")
        result = run("view", "--width", "1", "--height", "1")
        if len(result.stdout) != 2 or b"No interactive TTY" not in result.stderr:
            raise RuntimeError("Non-TTY fallback failed")
    print("PASS: help, 2D/3D/4D, XW rotation, two seeds, deterministic ASCII export, tiny non-TTY view")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
