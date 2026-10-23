"""Finite warm CPU render benchmark; writes nothing."""

from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.geometry import Camera
from ascii_tree.model import generate_tree
from ascii_tree.render import render

print(f"Python {platform.python_version()}, {platform.system()} {platform.release()}")
start = time.perf_counter()
tree = generate_tree(42)
print(f"Generation: {(time.perf_counter() - start)*1000:.2f} ms; "
      f"{len(tree.segments)} segments, {len(tree.leaves)} leaves")
for mode in ("2d", "3d", "4d"):
    durations = []
    for i in range(30):
        camera = Camera(mode=mode, yaw=25 + i*3, angle4d=i*2)
        start = time.perf_counter()
        render(tree, camera)
        durations.append((time.perf_counter() - start)*1000)
    print(f"{mode.upper()} 100x40, 30 frames: median {statistics.median(durations):.2f} ms, "
          f"max {max(durations):.2f} ms")
