"""Regenerate every committed example via the real headless CLI (offline)."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    directory = ROOT / "samples"
    directory.mkdir(exist_ok=True)
    manifest = []
    for seed in (42, 43):
        for mode, angle in (("2d", 0), ("3d", 0), ("4d", 0), ("4d", 45)):
            suffix = f"-xw{angle:03d}" if mode == "4d" else ""
            name = f"seed{seed}-{mode}{suffix}.txt"
            args = ["render", "--seed", str(seed), "--mode", mode,
                    "--width", "100", "--height", "40", "--yaw", "25", "--pitch", "-8",
                    "--angle4d", str(angle), "--output", str(directory / name)]
            subprocess.run([sys.executable, str(ROOT / "ascii-tree.py"), *args],
                           check=True, cwd=ROOT, timeout=15)
            data = (directory / name).read_bytes()
            assert len(data) == 4040 and all(len(line) == 100 for line in data.splitlines())
            assert all(c == 10 or 32 <= c <= 126 for c in data)
            manifest.append(dict(file=name, seed=seed, mode=mode, angle4d=angle,
                                 yaw=25, pitch=-8, width=100, height=40, zoom=1,
                                 aspect=2, time=0, sha256=hashlib.sha256(data).hexdigest()))
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    print(f"PASS: {len(manifest)} reproducible ASCII samples + manifest.json")


if __name__ == "__main__":
    main()
