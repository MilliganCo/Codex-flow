"""Small finite local benchmark; writes artifacts/benchmark.json."""

import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.model import generate_tree
from ascii_tree.render import RenderSettings, render


def main():
    start = time.perf_counter()
    tree = generate_tree(42)
    generation = (time.perf_counter() - start) * 1000
    measurements = []
    for width, height, repeats in ((100, 40, 8), (500, 200, 3)):
        for mode in ("2d", "3d", "4d"):
            settings = RenderSettings(width, height, mode, angle4d=45 if mode == "4d" else 0)
            samples = []
            for _ in range(repeats):
                start = time.perf_counter()
                render(tree, settings)
                samples.append((time.perf_counter() - start) * 1000)
            measurements.append(dict(mode=mode, width=width, height=height, repeats=repeats,
                                     median_ms=round(statistics.median(samples), 3),
                                     max_ms=round(max(samples), 3)))
    result = dict(python=platform.python_version(), platform=sys.platform, seed=42,
                  segments=len(tree.segments), leaves=len(tree.leaves),
                  generation_ms=round(generation, 3), frames=measurements,
                  note="CPU render only; terminal transport excluded; local measurements, not a guarantee")
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts" / "benchmark.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
