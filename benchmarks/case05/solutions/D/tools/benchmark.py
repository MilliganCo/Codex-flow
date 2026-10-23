"""Finite local benchmark; reports measured latency, never an FPS guarantee."""

from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ascii_tree.geometry import generate_tree
from ascii_tree.projection import View
from ascii_tree.render import render_tree


def main():
    start = time.perf_counter()
    tree = generate_tree(42)
    generation_ms = (time.perf_counter() - start) * 1000
    print(f"Python {sys.version.split()[0]}; seed=42; segments={len(tree.segments)}; leaves={len(tree.leaves)}")
    print(f"Generation: {generation_ms:.2f} ms")
    for mode in ("2d", "3d", "4d"):
        durations = []
        for index in range(12):
            view = View(mode=mode, yaw=25 + index * 3, angle4d=index * 3)
            start = time.perf_counter()
            frame = render_tree(tree, 100, 40, view)
            durations.append((time.perf_counter() - start) * 1000)
            if frame.width != 100 or frame.height != 40:
                raise RuntimeError("Unexpected frame size")
        print(f"{mode} 100x40, 12 frames: median={statistics.median(durations):.2f} ms; max={max(durations):.2f} ms")


if __name__ == "__main__":
    main()
