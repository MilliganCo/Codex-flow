"""Rebuild saved frames and deterministic SHA-256 manifest, with finite timings."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import statistics
import time

from ascii_tree.model import generate_tree
from ascii_tree.render import RenderOptions, render_tree


ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ("seed42_2d.txt", 42, RenderOptions(mode="2d")),
    ("seed42_3d.txt", 42, RenderOptions(mode="3d")),
    ("seed42_4d_xw_000.txt", 42, RenderOptions(mode="4d", angle4=0)),
    ("seed42_4d_xw_048.txt", 42, RenderOptions(mode="4d", angle4=48)),
    ("seed7_2d.txt", 7, RenderOptions(mode="2d")),
    ("seed7_3d.txt", 7, RenderOptions(mode="3d")),
)


def main() -> None:
    directory = ROOT / "examples"
    directory.mkdir(exist_ok=True)
    manifest = []
    timings = []
    trees = {seed: generate_tree(seed) for seed in (42, 7)}
    for name, seed, options in CASES:
        start = time.perf_counter()
        data = render_tree(trees[seed], options).encode("ascii")
        timings.append((time.perf_counter() - start) * 1000)
        assert len(data) == (options.width + 1) * options.height
        assert all(c == 10 or 32 <= c <= 126 for c in data)
        (directory / name).write_bytes(data)
        manifest.append({"file": name, "seed": seed, "options": asdict(options),
                         "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii", newline="\n")
    for seed, tree in trees.items():
        print(f"seed={seed}: {len(tree.segments)} segments, {len(tree.leaves)} leaves")
    print(f"Saved {len(CASES)} frames; render ms: min={min(timings):.1f}, median={statistics.median(timings):.1f}, max={max(timings):.1f}")


if __name__ == "__main__":
    main()
