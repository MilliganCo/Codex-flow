"""Offline smoke for packaged, independently accepted case02 applications.

Runs real module entrypoints and their submitted suites, without model calls,
browser launches, optional package installation, or native terminal automation.
"""
from pathlib import Path
import json
import os
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def invoke(folder, *args):
    env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-B', *args], cwd=folder, env=env,
                            capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', 'replace')[-4000:])
    return result

def main():
    report = {}
    for name in ('solo', 'flow'):
        folder = ROOT / 'examples/ascii-tree' / name
        tested = invoke(folder, '-m', 'unittest', 'discover', '-s', 'tests', '-q')
        match = re.search(rb'Ran (\d+) tests?', tested.stderr)
        skipped_match = re.search(rb'skipped=(\d+)', tested.stderr)
        skipped = int(skipped_match[1]) if skipped_match else 0
        checks = []
        for mode in ('2d', '3d', '4d'):
            def render(seed):
                return invoke(folder, '-m', 'ascii_tree', 'render', '--mode', mode,
                              '--seed', str(seed), '--width', '80', '--height', '30').stdout
            frame = render(42)
            rows = frame.splitlines()
            assert len(rows) == 30 and all(len(row) == 80 for row in rows), (name, mode, 'dimensions')
            assert b'\x1b' not in frame and b'\r' not in frame, (name, mode, 'plain LF ASCII')
            assert all(32 <= c <= 126 for row in rows for c in row), (name, mode, 'ASCII')
            assert frame == render(42), (name, mode, 'determinism')
            assert frame != render(137), (name, mode, 'seed variation')
            checks.append({'mode': mode, 'dimensions_ascii_repeat_seed': 'pass'})
        report[name] = {'submitted_tests': int(match[1]) if match else None,
                        'submitted_skipped': skipped,
                        'submitted_passed': int(match[1]) - skipped if match else None,
                        'module_smoke': checks, 'interactive_terminal': 'not run by this CI smoke'}
    print(json.dumps(report, indent=2))

if __name__ == '__main__': main()
