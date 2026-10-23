"""Rebuild the checked-in plain ASCII examples and their reproducible manifest."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.geometry import generate_tree
from ascii_tree.render import RenderOptions, frame_bytes


def main():
    destination = ROOT / "examples"
    destination.mkdir(exist_ok=True)
    entries = []
    for seed, mode, angle in ((42, "2d", 0), (42, "3d", 0), (42, "4d", 0),
                              (42, "4d", 55), (7, "2d", 0), (7, "3d", 0), (7, "4d", 35)):
        options = RenderOptions(mode=mode, angle4=angle)
        tree = generate_tree(seed)
        name = f"seed{seed}-{mode}" + (f"-xw{angle}" if mode == "4d" else "") + ".txt"
        data = frame_bytes(tree, options)
        (destination / name).write_bytes(data)
        entries.append({"file": name, "seed": seed, "options": asdict(options),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "nodes": len(tree.nodes), "segments": len(tree.segments),
                        "leaves": len(tree.leaves)})
    (destination / "manifest.json").write_text(json.dumps(entries, indent=2) + "\n", encoding="ascii", newline="\n")
    print(f"Wrote {len(entries)} deterministic ASCII frames and examples/manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
