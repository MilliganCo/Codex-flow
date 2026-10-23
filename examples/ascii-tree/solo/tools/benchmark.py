"""Small finite benchmark; stores measurements, never asserts machine speed."""

import argparse
import json
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.model import generate_tree
from ascii_tree.renderer import RenderOptions, render_tree


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, choices=range(1, 101), default=7, metavar="1..100")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    start = perf_counter()
    tree = generate_tree(42)
    generation_ms = (perf_counter() - start) * 1000
    result = {"python": platform.python_version(), "platform": sys.platform, "seed": 42,
              "size": [100, 40], "frames_per_mode": args.frames,
              "generation_ms": round(generation_ms, 2),
              "segments": len(tree.segments), "leaves": len(tree.leaves), "render": {}}
    for mode in ("2d", "3d", "4d"):
        render_tree(tree, RenderOptions(mode=mode))
        times = []
        for index in range(args.frames):
            start = perf_counter()
            render_tree(tree, RenderOptions(mode=mode, time=index * .125))
            times.append((perf_counter() - start) * 1000)
        median = statistics.median(times)
        result["render"][mode] = {"median_ms": round(median, 2), "max_ms": round(max(times), 2),
                                  "render_only_fps": round(1000 / median, 1)}
    data = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data, encoding="ascii")
    print(data, end="")


if __name__ == "__main__":
    main()
