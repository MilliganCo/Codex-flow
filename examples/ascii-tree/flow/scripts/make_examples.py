"""Regenerate the included deterministic frames and their SHA-256 manifest."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.model import generate_tree
from ascii_tree.render import RenderOptions, render, write_frame


def main():
    target = ROOT / "examples"
    target.mkdir(exist_ok=True)
    manifest = []
    cases = [(42, "2d", 0), (42, "3d", 0), (42, "4d", 0), (42, "4d", 65),
             (7, "2d", 0), (7, "3d", 0)]
    for seed, mode, angle in cases:
        options = RenderOptions(mode=mode, angle4d=angle)
        name = f"seed-{seed}-{mode}" + (f"-xw-{angle}" if mode == "4d" else "") + ".txt"
        frame = render(generate_tree(seed), options)
        write_frame(target / name, frame)
        manifest.append({"file": name, "seed": seed, "options": asdict(options),
                         "sha256": hashlib.sha256(frame.encode("ascii")).hexdigest()})
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {len(cases)} reproducible frames in examples/ (100x40, ASCII/LF)")


if __name__ == "__main__":
    main()
