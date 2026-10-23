"""Regenerate the shipped ASCII artifacts and their exact input manifest."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.model import generate_tree
from ascii_tree.renderer import RenderOptions, render_tree
from ascii_tree.state import ExplorerState
from ascii_tree.terminal import compose_screen

SAMPLES = (
    ("seed42_2d.txt", 42, RenderOptions(mode="2d")),
    ("seed42_3d.txt", 42, RenderOptions(mode="3d")),
    ("seed42_4d_xw_000.txt", 42, RenderOptions(mode="4d", angle4=0)),
    ("seed42_4d_xw_040.txt", 42, RenderOptions(mode="4d", angle4=40)),
    ("seed7_3d.txt", 7, RenderOptions(mode="3d")),
)


def main():
    directory = ROOT / "examples"
    directory.mkdir(exist_ok=True)
    trees = {seed: generate_tree(seed) for _, seed, _ in SAMPLES}
    manifest = []
    for name, seed, options in SAMPLES:
        data = render_tree(trees[seed], options).text().encode("ascii")
        (directory / name).write_bytes(data)
        manifest.append({"file": name, "seed": seed, "tree_fingerprint": trees[seed].fingerprint,
                         "options": asdict(options), "sha256": hashlib.sha256(data).hexdigest()})
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    screen = compose_screen(ExplorerState(trees[42], RenderOptions(mode="4d", angle4=40)), 99, 40)
    (directory / "interactive_layout.txt").write_bytes(("\n".join(screen.rows) + "\n").encode("ascii"))
    print(f"Saved {len(manifest)} canonical frames + UI layout to examples/.")


if __name__ == "__main__":
    main()
