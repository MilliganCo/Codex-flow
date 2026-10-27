"""Owner-selected black-box checks. Execute only through the official sandbox."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--nonce', required=True)
    args = parser.parse_args()
    cases = [
        ('sum.empty', '{"numbers":[]}', 0, {'sum': 0}),
        ('sum.positive', '{"numbers":[2,3]}', 0, {'sum': 5}),
        ('sum.negative', '{"numbers":[-8,3]}', 0, {'sum': -5}),
        ('sum.large', '{"numbers":[999999999999999999,1]}', 0, {'sum': 1000000000000000000}),
        ('reject.boolean', '{"numbers":[true]}', 2, None),
        ('reject.float', '{"numbers":[1.5]}', 2, None),
        ('reject.extra', '{"numbers":[1],"extra":0}', 2, None),
        ('reject.invalid_json', '{', 2, None),
    ]
    checks = []
    for identity, raw, expected_exit, expected_json in cases:
        try:
            completed = subprocess.run([sys.executable, '-I', '-B', str(args.workspace / 'sum_cli.py')],
                                       input=raw, text=True, capture_output=True, timeout=3, check=False)
            passed = completed.returncode == expected_exit
            if expected_json is not None:
                passed = passed and json.loads(completed.stdout) == expected_json
        except (OSError, ValueError, subprocess.TimeoutExpired):
            passed = False
        checks.append({'id': identity, 'status': 'passed' if passed else 'failed'})
    with args.report.open('x', encoding='utf-8') as stream:
        json.dump({'schema': 1, 'nonce': args.nonce, 'checks': checks}, stream)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
