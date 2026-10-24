"""Rebuild saved examples through the real headless CLI, with a hash manifest."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT/'artifacts'/'frames'
    target.mkdir(parents=True, exist_ok=True)
    manifest = []
    for seed, mode, angle in [(42, '2d', 0), (42, '3d', 0), (42, '4d', 0),
                              (42, '4d', 35), (43, '2d', 0), (43, '3d', 0)]:
        filename = f'seed{seed}-{mode}'+(f'-xw{angle}' if mode == '4d' else '')+'.txt'
        path = target/filename
        args = ['render', '--seed', str(seed), '--mode', mode, '--angle4d', str(angle),
                '--width', '100', '--height', '40', '--output', str(path)]
        result = subprocess.run([sys.executable, '-m', 'ascii_tree', *args], cwd=ROOT,
                                input=b'', capture_output=True, timeout=15)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())
        content = path.read_bytes()
        assert len(content) == 4040 and len(content.splitlines()) == 40
        assert all(len(row) == 100 for row in content.splitlines())
        assert all(c == 10 or 32 <= c <= 126 for c in content)
        manifest.append({'file': filename, 'seed': seed, 'mode': mode, 'angle4d': angle,
                         'width': 100, 'height': 40, 'yaw': -22, 'pitch': 8,
                         'zoom': 1, 'time': 0, 'aspect': .5,
                         'sha256': hashlib.sha256(content).hexdigest()})
    (target/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='ascii')
    print(f'PASS: {len(manifest)} ASCII frames and hash manifest saved in artifacts/frames')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
