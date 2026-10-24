"""Finite renderer benchmark; records this machine rather than a speed promise."""
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ascii_tree.model import generate_tree
from ascii_tree.render import View, render_tree

tree = generate_tree(42)
report = {'python': platform.python_version(), 'platform': platform.platform(),
          'seed': 42, 'dimensions': [100, 40], 'results': {}}
for mode in ('2d', '3d', '4d'):
    samples = []
    for _ in range(20):
        start = time.perf_counter()
        render_tree(tree, 100, 40, View(mode=mode, angle4d=35))
        samples.append((time.perf_counter()-start)*1000)
    report['results'][mode] = {'median_ms': round(statistics.median(samples), 3),
                              'max_ms': round(max(samples), 3), 'frames': 20}
(ROOT/'artifacts').mkdir(exist_ok=True)
(ROOT/'artifacts'/'performance.json').write_text(json.dumps(report, indent=2)+'\n', encoding='ascii')
print(json.dumps(report))
