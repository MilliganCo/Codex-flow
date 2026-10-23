"""Small bounded local measurement, not a performance guarantee."""

import json
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.model import generate_tree
from ascii_tree.render import RenderOptions, render_tree


def main():
    start = perf_counter()
    tree = generate_tree(42)
    generation_ms = (perf_counter() - start) * 1000
    results = {}
    for mode in ("2d", "3d", "4d"):
        samples = []
        for index in range(12):
            start = perf_counter()
            render_tree(tree, RenderOptions(mode=mode, yaw=25 + index * 3, angle4d=index * 3))
            samples.append((perf_counter() - start) * 1000)
        results[mode] = {"median_ms": round(statistics.median(samples), 3), "max_ms": round(max(samples), 3)}
    report = {"python": platform.python_version(), "platform": platform.system(),
              "dimensions": [100, 40], "seed": 42, "frames_per_mode": 12,
              "segments": len(tree.segments), "leaves": len(tree.leaves),
              "generation_ms": round(generation_ms, 3), "render": results}
    output = ROOT / "artifacts" / "benchmark.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
