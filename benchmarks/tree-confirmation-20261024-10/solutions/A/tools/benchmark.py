"""Finite renderer timing; deliberately separate from correctness tests."""

import argparse
import json
from pathlib import Path
import platform
import statistics
import time

from ascii_tree.geometry import generate_tree
from ascii_tree.projection import RenderOptions
from ascii_tree.render import render_tree


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.frames <= 200:
        parser.error("frames must be 1..200")
    report = {"python": platform.python_version(), "platform": platform.system(),
              "size": [100, 40], "frames_per_case": args.frames, "cases": []}
    for seed in (42, 7):
        start = time.perf_counter()
        tree = generate_tree(seed)
        generation_ms = (time.perf_counter() - start) * 1000
        for mode in ("2d", "3d", "4d"):
            times = []
            for frame in range(args.frames):
                options = RenderOptions(mode=mode, yaw=25 + frame * 3, angle4=frame * 4)
                start = time.perf_counter()
                render_tree(tree, options)
                times.append((time.perf_counter() - start) * 1000)
            report["cases"].append({"seed": seed, "mode": mode, "segments": len(tree.segments),
                                    "leaves": len(tree.leaves), "generation_ms": round(generation_ms, 3),
                                    "mean_ms": round(statistics.mean(times), 3),
                                    "max_ms": round(max(times), 3)})
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="ascii")
    print(text, end="")


if __name__ == "__main__":
    main()
