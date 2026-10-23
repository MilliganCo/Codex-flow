"""Finite CPU benchmark; no third-party modules or rendering in the terminal."""

import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.geometry import generate_tree
from ascii_tree.render import RenderOptions, frame_bytes


def main():
    start = time.perf_counter()
    tree = generate_tree(42)
    result = {"python": sys.version.split()[0], "seed": 42,
              "generation_ms": round((time.perf_counter() - start) * 1000, 3), "frames": []}
    for width, height in ((100, 40), (200, 60)):
        for mode in ("2d", "3d", "4d"):
            options = RenderOptions(mode=mode, width=width, height=height, angle4=35)
            frame_bytes(tree, options)
            samples = []
            for _ in range(20):
                start = time.perf_counter()
                frame_bytes(tree, options)
                samples.append((time.perf_counter() - start) * 1000)
            result["frames"].append({"mode": mode, "width": width, "height": height,
                                      "median_ms": round(statistics.median(samples), 3),
                                      "max_ms": round(max(samples), 3), "samples": len(samples)})
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
