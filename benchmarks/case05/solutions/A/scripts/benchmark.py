"""Small finite benchmark, including all modes and two tree geometries."""

import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.geometry import View
from ascii_tree.model import generate_tree
from ascii_tree.render import render


def main():
    results = []
    for seed in (42, 7):
        started = time.perf_counter()
        tree = generate_tree(seed)
        generation_ms = (time.perf_counter() - started) * 1000
        for mode in ('2d', '3d', '4d'):
            durations = []
            for index in range(8):
                started = time.perf_counter()
                render(tree, View(mode=mode, time=index * 0.1), 100, 40)
                durations.append((time.perf_counter() - started) * 1000)
            results.append({'seed': seed, 'mode': mode, 'segments': len(tree.segments),
                            'leaves': len(tree.leaves), 'generation_ms': round(generation_ms, 2),
                            'median_ms': round(statistics.median(durations), 2),
                            'max_ms': round(max(durations), 2), 'frames': len(durations),
                            'width': 100, 'height': 40})
    destination = ROOT / 'verification'
    destination.mkdir(exist_ok=True)
    report = {'python': sys.version.split()[0], 'platform': sys.platform, 'results': results}
    (destination / 'benchmark.json').write_text(json.dumps(report, indent=2) + '\n', encoding='ascii')
    for result in results:
        print(f"seed {result['seed']} {result['mode']}: median {result['median_ms']} ms, max {result['max_ms']} ms")


if __name__ == '__main__':
    main()
