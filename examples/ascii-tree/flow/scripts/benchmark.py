"""Finite performance sample; no performance assertion tied to hardware speed."""

from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.model import generate_tree
from ascii_tree.render import RenderOptions, render


def main():
    start = time.perf_counter()
    tree = generate_tree(42)
    print(f"seed=42: {len(tree.segments)} segments, {len(tree.leaves)} leaves; generation {(time.perf_counter()-start)*1000:.2f} ms")
    for mode in ("2d", "3d", "4d"):
        samples = []
        for i in range(20):
            options = RenderOptions(mode=mode, time=i / 15)
            start = time.perf_counter()
            frame = render(tree, options)
            samples.append((time.perf_counter() - start) * 1000)
            if len(frame) != 4040:
                raise RuntimeError("invalid frame dimensions")
        print(f"{mode} 100x40: median {statistics.median(samples):.2f} ms, max {max(samples):.2f} ms, n=20")


if __name__ == "__main__":
    main()
