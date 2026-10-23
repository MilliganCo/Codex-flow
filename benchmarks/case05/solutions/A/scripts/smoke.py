"""Finite headless smoke: real CLI processes, exports and checked-in samples."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*arguments):
    result = subprocess.run([sys.executable, '-m', 'ascii_tree', *arguments], cwd=ROOT,
                            stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
    if result.returncode:
        raise AssertionError(f'CLI returned {result.returncode}: {result.stderr.decode(errors="replace")}')
    return result


def valid_frame(data, width, height):
    assert len(data) == (width + 1) * height, 'Incorrect frame byte count'
    assert len(data.splitlines()) == height, 'Incorrect row count'
    assert all(len(line) == width for line in data.splitlines()), 'Incorrect column count'
    assert all(c == 10 or 32 <= c <= 126 for c in data), 'Non-printable ASCII or ANSI escape'


def main():
    (ROOT / '.tmp').mkdir(exist_ok=True)
    run('--help')
    print('PASS 1/5: CLI startup and help')
    with tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as directory:
        frames = []
        for mode, angle in (('2d', 0), ('3d', 0), ('4d', 0), ('4d', 45)):
            target = Path(directory) / f'{mode}-{angle}.txt'
            args = ('render', '--seed', '42', '--mode', mode, '--angle4', str(angle), '--output', str(target))
            run(*args)
            first = target.read_bytes()
            run(*args)
            assert first == target.read_bytes(), 'Nondeterministic output'
            valid_frame(first, 100, 40)
            frames.append(first)
        print('PASS 2/5: all modes, exact dimensions, ASCII and byte determinism')
        assert len(set(frames)) == 4, 'Modes or XW rotation did not change the frame'
        seed7 = run('render', '--seed', '7', '--mode', '3d').stdout
        assert seed7 != frames[1], 'Seeds did not change the frame'
        print('PASS 3/5: different seeds and meaningful 4D rotation')
        fallback = run('view', '--width', '1', '--height', '1')
        valid_frame(fallback.stdout, 1, 1)
        assert b'No interactive TTY' in fallback.stderr
        print('PASS 4/5: non-TTY view, minimum size and shutdown')
    manifest = json.loads((ROOT / 'samples' / 'manifest.json').read_text(encoding='ascii'))
    for entry in manifest:
        data = (ROOT / 'samples' / entry['file']).read_bytes()
        valid_frame(data, entry['width'], entry['height'])
        assert hashlib.sha256(data).hexdigest() == entry['sha256'], 'Sample hash mismatch'
        actual = run('render', '--seed', str(entry['seed']), '--mode', entry['mode'],
                     '--angle4', str(entry['angle4'])).stdout
        assert actual == data, 'Saved sample differs from current renderer'
    print(f'PASS 5/5: {len(manifest)} saved samples match fresh CLI renders')


if __name__ == '__main__':
    main()
