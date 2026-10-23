"""Regenerate checked-in frames offline: python tools/make_samples.py."""

from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ascii_tree.geometry import generate_tree
from ascii_tree.projection import View
from ascii_tree.render import render_tree


def main() -> int:
    directory = ROOT / "samples"
    directory.mkdir(exist_ok=True)
    specifications = (
        ("seed42_2d.txt", 42, "2d", 0),
        ("seed42_3d.txt", 42, "3d", 0),
        ("seed42_4d_xw0.txt", 42, "4d", 0),
        ("seed42_4d_xw35.txt", 42, "4d", 35),
        ("seed2026_3d.txt", 2026, "3d", 0),
    )
    manifest = []
    for filename, seed, mode, angle in specifications:
        view = View(mode=mode, angle4d=angle)
        frame = render_tree(generate_tree(seed), 100, 40, view)
        frame.save(directory / filename)
        manifest.append({"file": filename, "seed": seed, "mode": mode, "width": 100, "height": 40,
                         "yaw": view.yaw, "pitch": view.pitch, "angle4d": angle,
                         "zoom": view.zoom, "aspect": view.aspect, "time": 0,
                         "sha256": hashlib.sha256(frame.to_bytes()).hexdigest()})
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii", newline="\n")
    print(f"Saved {len(manifest)} reproducible ASCII frames to samples/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
