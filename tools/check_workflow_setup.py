"""Real SDK controls for generated unittest acceptance; no model generation."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

import argparse

SOURCE = Path(__file__).resolve().parents[1]
ROOT: Path
CODEX: Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


PASS = 'import unittest\nimport app\nclass Tests(unittest.TestCase):\n def test_add(self): self.assertEqual(app.add(2,3),5)\n'
CASES = {
    'pass': (PASS, 0, True),
    'wrong_code': (PASS, 0, False),
    'zero': ('import unittest\ndef helper_only(): pass\n', 0, False),
    'all_skip': ('import unittest\n@unittest.skip("declared")\nclass Tests(unittest.TestCase):\n def test_one(self): pass\n', 1, False),
    'mixed_skip': (PASS + '@unittest.skip("declared")\nclass Skipped(unittest.TestCase):\n def test_one(self): pass\n', 1, True),
    'class_skip': (PASS + 'class Skipped(unittest.TestCase):\n @classmethod\n def setUpClass(cls): raise unittest.SkipTest("declared")\n def test_one(self): pass\n', 1, True),
    'expected_failure': ('import unittest\nclass Tests(unittest.TestCase):\n @unittest.expectedFailure\n def test_one(self): self.fail("expected")\n', 0, False),
    'unexpected_success': ('import unittest\nclass Tests(unittest.TestCase):\n @unittest.expectedFailure\n def test_one(self): pass\n', 0, False),
    'changed_baseline': (PASS, 0, False),
    'added_tests': (PASS, 0, True),
    'import_error': ('import unittest\nimport definitely_missing_fixture_module\n', 0, False),
    'subtest_failure': ('import unittest\nclass Tests(unittest.TestCase):\n def test_one(self):\n  for value in (1,2):\n   with self.subTest(value=value): self.assertEqual(value,1)\n', 0, False),
    'max_800': ('import unittest\nclass Tests(unittest.TestCase):\n def test_one(self): pass\ndef load_tests(loader,tests,pattern): return unittest.TestSuite(Tests("test_one") for _ in range(800))\n', 0, True),
    'over_800': ('import unittest\nclass Tests(unittest.TestCase):\n def test_one(self): pass\ndef load_tests(loader,tests,pattern): return unittest.TestSuite(Tests("test_one") for _ in range(801))\n', 0, False),
}


def workflow_control():
    from codex_flow import workflow, workflow_setup, workflow_display
    from codex_flow.config import Config
    calls = {'fixture_generation': 0, 'sdk_verification': 0}
    class FixtureWithSDK(workflow.NativeBackend):
        kind = 'fixture_generator_real_sdk'

        def generate(self, workspace, cfg, task, run_dir, requests, budget, execution, on_process_start):
            sequence = requests.reserve()
            calls['fixture_generation'] += 1
            (workspace / 'app.py').write_bytes(b'def add(a,b): return a+b\n')
            return {'status': 'completed_unverified', 'native_exit_code': 0, 'real_model_calls': 0,
                    'generator_kind': 'fixture', 'subscription': {'requests': [
                        {'sequence': sequence, 'status': 'completed', 'model': 'fixture', 'usage': None}]}}

        def verify(self, *args, **kwargs):
            calls['sdk_verification'] += 1
            return super().verify(*args, **kwargs)

    repo = ROOT / 'workflow-default'
    repo.mkdir()
    (repo / 'tests').mkdir()
    (repo / 'tests/test_app.py').write_text(PASS, encoding='utf-8', newline='\n')
    original = b'def add(a,b): return a+b+1\n'
    (repo / 'app.py').write_bytes(original)
    subprocess.run(['git', '-c', 'init.templateDir=' + str(ROOT / 'empty-template'), 'init', '--quiet', str(repo)],
                   capture_output=True, check=True)
    workflow_setup.initialize(repo)
    selected = workflow_setup.default_contract(repo)
    engine = workflow.Engine(repo, backend=FixtureWithSDK())
    completed = engine.start(Config(timeout_s=90, max_model_requests=2), 'Repair fixture addition', selected,
                             enable=True, exe=str(CODEX))
    assert completed['accepted'] is True and completed['state'] == 'completed', completed['state']
    assert calls == {'fixture_generation': 1, 'sdk_verification': 1}
    assert completed['requests_used'] == 1 and completed['requests_remaining'] == 1
    assert (repo / 'app.py').read_bytes() == original
    bundle = engine._base(completed['workflow_id']) / completed['report']['bundle']
    assert (bundle / 'files/app.py').read_bytes() == b'def add(a,b): return a+b\n'
    assert (bundle / 'files/tests/test_app.py').read_bytes() == PASS.encode('utf-8')
    write(ROOT / 'workflow-default-status.json', completed)
    (ROOT / 'workflow-default-status.txt').write_text(workflow_display.status(completed), encoding='utf-8')
    return {'accepted': True, 'state': 'completed', 'calls': calls, 'requests_reserved': 1,
            'origin_unchanged': True, 'result_bundle_correct': True, 'real_model_calls': 0,
            'status_sha256': sha(ROOT / 'workflow-default-status.json')}


def main():
    global ROOT, CODEX
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='New external output directory')
    parser.add_argument('--codex', type=Path, required=True, help='Reviewed existing native executable')
    args = parser.parse_args()
    ROOT, CODEX = args.root.absolute(), args.codex.absolute()
    assert os.name == 'nt' and not ROOT.exists(), 'Preserve existing controls'
    ROOT.mkdir()
    sys.path.insert(0, str(SOURCE / 'runtime'))
    from codex_flow import workflow_setup
    runtime = {p.name: sha(p) for p in (SOURCE / 'runtime/codex_flow').glob('*.py')}
    write(ROOT / 'preregistration.json', {'schema': 1, 'cases': {name: {'allow_skips': row[1], 'accepted': row[2]} for name, row in CASES.items()},
          'runtime_sha256': runtime, 'codex_sha256': sha(CODEX), 'real_model_calls': 0,
          'checker_application_execution': 'official Windows SDK only', 'reruns': False,
          'workflow_default_control': 'one fixture generation, one SDK verification, origin unchanged'})
    results = []
    for name, (test_source, skips, expected) in CASES.items():
        repo = ROOT / name
        repo.mkdir()
        (repo / 'tests').mkdir()
        (repo / 'tests/test_app.py').write_text(test_source, encoding='utf-8', newline='\n')
        (repo / 'app.py').write_text('def add(a,b): return a+b\n', encoding='utf-8', newline='\n')
        subprocess.run(['git', '-c', 'init.templateDir=' + str(ROOT / 'empty-template'), 'init', '--quiet', str(repo)],
                       capture_output=True, check=True)
        initialized = workflow_setup.initialize(repo, allow_skips=skips)
        contract = workflow_setup.default_contract(repo).path
        if name == 'wrong_code':
            (repo / 'app.py').write_text('def add(a,b): return a+b+1\n', encoding='utf-8')
        if name == 'changed_baseline':
            (repo / 'tests/test_app.py').write_text('import unittest\nclass Tests(unittest.TestCase):\n def test_one(self): pass\n', encoding='utf-8')
        if name == 'added_tests':
            (repo / 'tests/test_extra.py').write_text('import unittest\nclass Extra(unittest.TestCase):\n def test_two(self): self.assertEqual(2*3,6)\n', encoding='utf-8')
        before = {str(p.relative_to(repo)): sha(p) for p in [repo / 'app.py', *sorted((repo / 'tests').glob('*.py'))]}
        checker_sha = sha(contract.parent / 'checker.py')
        command = [sys.executable, '-I', '-B', str(SOURCE / 'codex-flow.py'), '--repo', str(repo), '--codex', str(CODEX),
                   'verify', '--acceptance-file', str(contract), '--execute', '--timeout', '90']
        process = subprocess.run(command, capture_output=True, check=False, timeout=110)
        (ROOT / (name + '-stdout.bin')).write_bytes(process.stdout)
        (ROOT / (name + '-stderr.bin')).write_bytes(process.stderr)
        assert process.returncode in (0, 3), name + ': unexpected controller failure'
        output = json.loads(process.stdout)
        gate = output['acceptance']
        assert output['accepted'] is expected and process.returncode == (0 if expected else 3), name
        assert gate['model_calls'] == 0 and gate['checker_executed_on_host'] is False
        assert checker_sha == sha(contract.parent / 'checker.py')
        assert before == {str(p.relative_to(repo)): sha(p) for p in [repo / 'app.py', *sorted((repo / 'tests').glob('*.py'))]}
        details_paths = list((repo / '.codex-flow/acceptance').glob('*/scratch/details.json'))
        assert len(details_paths) == 1, name + ': no checker details'
        details = json.loads(details_paths[0].read_bytes())
        if expected:
            assert details['passed'] > 0 and gate['capture_complete'] is True and gate['sdk_root_exit_observed'] is True
        if name in ('zero', 'all_skip'):
            assert details['passed'] == 0
        if name == 'max_800':
            assert details['passed'] == 800
        if name in ('mixed_skip', 'class_skip'):
            assert details['passed'] == 1 and details['skipped'] == 1
        receipt = repo / '.codex-flow/runs' / output['run_id'] / 'acceptance.json'
        results.append({'case': name, 'accepted': output['accepted'], 'expected': expected,
                        'actual_unittest_counts': details, 'gate_checks': gate.get('checks_run'),
                        'receipt_sha256': sha(receipt), 'checker_sha256': checker_sha,
                        'application_and_tests_unchanged': True, 'real_model_calls': 0})
        print(json.dumps({'case': name, 'accepted': output['accepted'], 'actual_passed': details['passed']}), flush=True)
    control = workflow_control()
    assert runtime == {p.name: sha(p) for p in (SOURCE / 'runtime/codex_flow').glob('*.py')}
    result = {'schema': 1, 'kind': 'workflow_init_unittest_sdk_controls', 'passed': True, 'cases': results,
              'runtime_sha256': runtime, 'codex_sha256': sha(CODEX), 'real_model_calls': 0,
              'app_checker_host_executions': 0, 'proof_script_sha256': sha(Path(__file__)),
              'workflow_default_control': control}
    write(ROOT / 'proof-result.json', result)
    print(json.dumps({'passed': True, 'cases': len(results), 'real_model_calls': 0, 'result_sha256': sha(ROOT / 'proof-result.json')}))


if __name__ == '__main__':
    main()
