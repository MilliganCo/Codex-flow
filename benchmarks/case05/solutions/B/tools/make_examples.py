"""Rebuild checked-in example rasters using the same public renderer."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.geometry import Camera
from ascii_tree.model import generate_tree
from ascii_tree.render import export_frame, render


def main():
    directory = ROOT / "examples"
    directory.mkdir(exist_ok=True)
    manifest = []
    for seed, mode, angle in ((42, "2d", 0), (42, "3d", 0), (42, "4d", 0),
                              (42, "4d", 45), (7, "3d", 0)):
        name = f"seed{seed}-{mode}" + (f"-xw{angle:03d}" if mode == "4d" else "") + ".txt"
        camera = Camera(100, 40, mode, angle4d=angle)
        path = directory / name
        export_frame(path, render(generate_tree(seed), camera))
        manifest.append({"file": name, "seed": seed, "mode": mode, "angle4d": angle,
                         "width": 100, "height": 40,
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "command": f"python -m ascii_tree render --seed {seed} --mode {mode} "
                                    f"--width 100 --height 40 --angle4d {angle} --output examples/{name}"})
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    print(f"Wrote {len(manifest)} reproducible ASCII frames to examples/")


if __name__ == "__main__":
    main()
