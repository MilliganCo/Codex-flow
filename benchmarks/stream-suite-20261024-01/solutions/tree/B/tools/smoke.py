"""One-command finite smoke: subprocess CLI, all modes, ASCII, determinism, no-TTY."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ascii_tree.app import Explorer, compose


def call(*args):
    return subprocess.run([sys.executable, '-m', 'ascii_tree', *args], cwd=ROOT,
                          input=b'', capture_output=True, timeout=15)


def main():
    assert call('--help').returncode == 0
    with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as directory:
        frames = []
        for mode, angle in [('2d', '0'), ('3d', '0'), ('4d', '0'), ('4d', '35')]:
            path = Path(directory)/f'{mode}-{angle}.txt'
            args = ('render', '--seed', '42', '--mode', mode, '--angle4d', angle,
                    '--width', '100', '--height', '40', '--output', str(path))
            result = call(*args)
            assert result.returncode == 0, result.stderr
            content = path.read_bytes()
            assert len(content) == 4040
            assert all(c == 10 or 32 <= c <= 126 for c in content)
            assert call(*args).returncode == 0
            assert path.read_bytes() == content
            frames.append(content)
        assert len(set(frames)) == 4
    result = call('view')
    assert result.returncode == 2 and b'interactive TTY' in result.stderr
    app = Explorer()
    original = app.tree
    for key in '123':
        app.handle(key)
        assert app.tree is original
    assert len(compose(app, 1, 1)[0]) == 1
    print('PASS: 4 deterministic frames; ASCII 100x40; XW change; same object; 1x1; non-TTY exit.')
    print('Real TTY startup: python tools/native_probe.py --startup')
    return 0


if __name__ == '__main__':
    (ROOT/'.tmp').mkdir(exist_ok=True)
    raise SystemExit(main())
