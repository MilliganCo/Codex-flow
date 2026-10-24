"""Regenerate checked-in raw ASCII samples and their reproducibility manifest."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ascii_tree.model import generate_tree
from ascii_tree.render import Camera, render


def main():
    folder = ROOT / "samples"
    folder.mkdir(exist_ok=True)
    manifest = []
    for seed, mode, angle in ((42, "2d", 0), (42, "3d", 0), (42, "4d", 0),
                              (42, "4d", 45), (137, "2d", 0), (137, "3d", 0)):
        tree = generate_tree(seed)
        camera = Camera(mode=mode, angle4d=angle)
        name = f"seed-{seed}-{mode}" + (f"-xw-{angle}" if mode == "4d" else "") + ".txt"
        frame = render(tree, 100, 40, camera).encode("ascii")
        (folder / name).write_bytes(frame)
        manifest.append({"file": name, "seed": seed, "mode": mode, "angle4d": angle,
                         "yaw": 25, "pitch": -7, "zoom": 1, "aspect": .5, "time": 0,
                         "width": 100, "height": 40, "segments": len(tree.segments),
                         "leaves": len(tree.leaves), "sha256": hashlib.sha256(frame).hexdigest()})
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(manifest)} deterministic ASCII frames to {folder}")


if __name__ == "__main__":
    main()
