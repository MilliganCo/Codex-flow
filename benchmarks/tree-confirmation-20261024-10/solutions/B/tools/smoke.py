"""One-command finite headless smoke: python tools/smoke.py."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as folder:
        frames = []
        for mode, angle in (("2d", "0"), ("3d", "0"), ("4d", "0"), ("4d", "45")):
            target = Path(folder) / f"{mode}-{angle}.txt"
            subprocess.run([sys.executable, "-m", "ascii_tree", "render", "--seed", "42",
                            "--mode", mode, "--angle4d", angle, "--output", str(target)],
                           cwd=ROOT, check=True, timeout=15)
            frame = target.read_bytes()
            assert len(frame.splitlines()) == 40
            assert all(len(row) == 100 for row in frame.splitlines())
            assert all(32 <= b <= 126 or b == 10 for b in frame)
            frames.append(frame)
        assert frames[2] != frames[3], "XW rotation must change the frame"
        result = subprocess.run([sys.executable, "-m", "ascii_tree", "view", "--width", "1",
                                 "--height", "1"], cwd=ROOT, capture_output=True, timeout=15)
        assert result.returncode == 0 and result.stdout.strip(b"\r\n").isascii()
    print("PASS: 2D/3D/4D CLI, 100x40 ASCII exports, XW change, tiny headless view")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
