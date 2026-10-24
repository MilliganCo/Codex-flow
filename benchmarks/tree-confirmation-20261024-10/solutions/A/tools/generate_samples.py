"""Regenerate the committed-to-source ASCII examples, without external tools."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from ascii_tree.app import Explorer, compose
from ascii_tree.geometry import generate_tree
from ascii_tree.projection import RenderOptions
from ascii_tree.render import render_tree

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / "samples"
    destination.mkdir(exist_ok=True)
    manifest = []
    specifications = ((42, "2d", 0, 25), (42, "3d", 0, 25), (42, "3d", 0, 100),
                      (42, "4d", 0, 25), (42, "4d", 65, 25),
                      (7, "2d", 0, 25), (7, "3d", 0, 25), (7, "4d", 65, 25))
    for seed, mode, angle4, yaw in specifications:
        options = RenderOptions(mode=mode, angle4=angle4, yaw=yaw)
        suffix = f"_xw{angle4:03d}" if mode == "4d" else (f"_yaw{yaw}" if yaw != 25 else "")
        name = f"seed{seed}_{mode}{suffix}.txt"
        data = render_tree(generate_tree(seed), options).bytes()
        (destination / name).write_bytes(data)
        manifest.append({"file": name, "seed": seed, "options": asdict(options),
                         "sha256": hashlib.sha256(data).hexdigest()})
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")

    state = Explorer()
    transcript = []
    for label, keys in (("START / 3D", ()), ("KEY 1 / SAME TREE IN 2D", ("1",)),
                        ("KEY 3 / SAME TREE IN 4D", ("3",)),
                        ("KEY ] SIX TIMES / XW 60 DEG", ("]",) * 6),
                        ("KEY G / NEXT SEED", ("g",))):
        for key in keys:
            state.key(key)
        transcript += [label, "=" * 100, *compose(state, 100, 40), ""]
    (destination / "interactive_demo.txt").write_bytes(("\n".join(transcript) + "\n").encode("ascii"))
    print(f"Generated {len(manifest)} frames and a scripted UI transcript in samples/.")


if __name__ == "__main__":
    main()
