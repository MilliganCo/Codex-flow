"""Finite combined check with saved evidence; does not launch a terminal or browser."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
target = ROOT/'artifacts'
target.mkdir(exist_ok=True)

with (target/'unittest.txt').open('w', encoding='utf-8', newline='\n') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.discover(str(ROOT/'tests')))
assert result.wasSuccessful(), 'See artifacts/unittest.txt'
smoke = subprocess.run([sys.executable, str(ROOT/'tools'/'smoke.py')], cwd=ROOT,
                       capture_output=True, timeout=30)
(target/'smoke.txt').write_bytes(smoke.stdout+smoke.stderr)
assert smoke.returncode == 0, 'See artifacts/smoke.txt'
manifest = json.loads((target/'frames'/'manifest.json').read_text(encoding='ascii'))
for item in manifest:
    content = (target/'frames'/item['file']).read_bytes()
    assert hashlib.sha256(content).hexdigest() == item['sha256'], item['file']
    assert len(content) == (item['width']+1)*item['height']
    assert all(c == 10 or 32 <= c <= 126 for c in content)
exports = list((target/'probe-exports').glob('*.txt'))
for path in exports:
    content = path.read_bytes()
    lines = content.splitlines()
    assert lines and all(len(row) == len(lines[0]) for row in lines)
    assert all(c == 10 or 32 <= c <= 126 for c in content)
summary = {'unit_tests': result.testsRun, 'unit_failures': len(result.failures),
           'unit_errors': len(result.errors), 'smoke': 'pass',
           'saved_frames_verified': len(manifest), 'native_exports_verified': len(exports),
           'native_tty_not_run_by_this_script': True}
(target/'verification.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='ascii')
print(json.dumps(summary))
