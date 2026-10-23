"""Rebuild the checked-in demonstration frames and their byte hashes."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.geometry import View
from ascii_tree.model import generate_tree
from ascii_tree.render import render


def main():
    destination = ROOT / 'samples'
    destination.mkdir(exist_ok=True)
    manifest = []
    for seed in (42, 7):
        tree = generate_tree(seed)
        for mode, angle in (('2d', 0), ('3d', 0), ('4d', 0), ('4d', 45)):
            suffix = f'-xw{angle:03d}' if mode == '4d' else ''
            name = f'seed{seed}-{mode}{suffix}.txt'
            frame = render(tree, View(mode=mode, angle4=angle), 100, 40)
            frame.save(destination / name)
            manifest.append({'file': name, 'seed': seed, 'mode': mode, 'width': 100, 'height': 40,
                             'yaw': -20, 'pitch': 8, 'angle4': angle, 'zoom': 1, 'time': 0,
                             'sha256': hashlib.sha256(frame.text().encode('ascii')).hexdigest()})
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='ascii')
    print(f'PASS: wrote {len(manifest)} ASCII frames (100x40) and manifest.json')


if __name__ == '__main__':
    main()
