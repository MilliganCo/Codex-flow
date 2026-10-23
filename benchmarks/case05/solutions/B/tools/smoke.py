"""One finite command, zero installs/network. Run from any working directory."""

import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def call(*args):
    result = subprocess.run([sys.executable, "-m", "ascii_tree", *args], cwd=ROOT,
                            input=b"", capture_output=True, timeout=10)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result


def main():
    call("--help")
    temporary = ROOT / ".tmp"
    temporary.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temporary) as directory:
        images = []
        for mode, angle in (("2d", "0"), ("3d", "0"), ("4d", "0"), ("4d", "45")):
            args = ("render", "--seed", "42", "--mode", mode, "--width", "100",
                    "--height", "40", "--angle4d", angle)
            a, b = call(*args).stdout, call(*args).stdout
            if a != b or len(a) != 4040:
                raise RuntimeError("determinism or size failure")
            if len(a.splitlines()) != 40 or any(len(row) != 100 for row in a.splitlines()):
                raise RuntimeError("incorrect frame dimensions")
            if not all(byte == 10 or 32 <= byte <= 126 for byte in a):
                raise RuntimeError("non-ASCII/control byte in frame")
            path = Path(directory) / f"{mode}-{angle}.txt"
            call(*args, "--output", str(path))
            if path.read_bytes() != a:
                raise RuntimeError("file/stdout mismatch")
            images.append(a)
        if len(set(images)) != 4:
            raise RuntimeError("mode or XW rotation has no visible effect")
        different_seed = call("render", "--seed", "7", "--mode", "3d").stdout
        if different_seed == images[1]:
            raise RuntimeError("seed has no visible effect")
        tiny = call("view", "--width", "1", "--height", "1")
        if len(tiny.stdout) != 2 or b"No interactive TTY" not in tiny.stderr:
            raise RuntimeError("non-TTY view did not shut down cleanly")
    print("PASS: CLI help, 2D/3D/4D, XW rotation, seeds 42/7, deterministic bytes,")
    print("      100x40 printable ASCII, file export, 1x1 non-TTY startup/shutdown.")
    print("seed42-4d-xw45 sha256=" + hashlib.sha256(images[3]).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
