"""Owner-selected checks; execute only inside the official Codex sandbox."""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--nonce', required=True)
    args = parser.parse_args()
    checks = []
    try:
        proposal = (args.workspace / 'worker-proposal.txt').read_text(encoding='utf-8')
        blocks = re.findall(r'```python\s*\n(.*?)\n```', proposal, flags=re.DOTALL)
        source = (args.workspace / 'core.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        bound = (len(blocks) == 1 and proposal.count('```') == 2 and len(blocks[0].splitlines()) <= 150
                 and ast.dump(ast.parse(blocks[0]), include_attributes=False) == ast.dump(tree, include_attributes=False)
                 and len(functions) == 1 and functions[0].name == 'clamp_int'
                 and [a.arg for a in functions[0].args.args] == ['value', 'minimum', 'maximum'])
    except (OSError, ValueError, SyntaxError):
        bound = False
    checks.append({'id': 'handoff.source_matches', 'status': 'passed' if bound else 'failed'})
    readme = args.workspace / 'README.md'
    checks.append({'id': 'readme.present', 'status': 'passed' if readme.is_file() and readme.stat().st_size > 0 else 'failed'})
    cases = [
        ('inside', '{"value":3,"min":0,"max":9}', 0, 3),
        ('left', '{"value":-3,"min":0,"max":9}', 0, 0),
        ('right', '{"value":10,"min":0,"max":9}', 0, 9),
        ('equal_bounds', '{"value":-1,"min":5,"max":5}', 0, 5),
        ('negative', '{"value":-2,"min":-9,"max":-1}', 0, -2),
        ('large', '{"value":999999999999999999999,"min":0,"max":1000000000000000000000}', 0, 999999999999999999999),
        ('bool_value', '{"value":true,"min":0,"max":9}', 2, None),
        ('float_value', '{"value":1.5,"min":0,"max":9}', 2, None),
        ('bool_bound', '{"value":1,"min":false,"max":9}', 2, None),
        ('reversed', '{"value":1,"min":9,"max":0}', 2, None),
        ('missing', '{"value":1,"min":0}', 2, None),
        ('extra', '{"value":1,"min":0,"max":9,"extra":1}', 2, None),
        ('bad_json', '{', 2, None),
    ]
    for identity, raw, expected_exit, expected_value in cases:
        try:
            process = subprocess.run([sys.executable, '-I', '-B', str(args.workspace / 'app.py')],
                                     input=raw, capture_output=True, text=True, check=False, timeout=2)
            ok = process.returncode == expected_exit
            if expected_exit == 0:
                result = json.loads(process.stdout)
                ok = ok and result == {'value': expected_value} and type(result['value']) is int
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
            ok = False
        checks.append({'id': 'cli.' + identity, 'status': 'passed' if ok else 'failed'})
    with args.report.open('x', encoding='utf-8') as stream:
        json.dump({'schema': 1, 'nonce': args.nonce, 'checks': checks}, stream)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
