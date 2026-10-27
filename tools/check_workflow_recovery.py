"""Real process crashes plus fixture generation and official sandbox verification."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

SOURCE = Path(__file__).resolve().parents[1]
ROOT: Path
FROZEN: Path
CODEX: Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write('\n')


def imports():
    sys.path.insert(0, str(FROZEN / 'runtime'))
    from codex_flow import workflow
    from codex_flow.config import Config
    from codex_flow.telemetry import write_json
    def forbidden_generation(*args, **kwargs):
        raise RuntimeError('Recovery control forbids real model generation')
    workflow.NativeBackend.generate = forbidden_generation
    return workflow, Config, write_json


def backend(case):
    workflow, _, write_json = imports()
    class FixtureWithSDK(workflow.NativeBackend):
        kind = 'fixture_generator_real_sdk'

        def bump(self, name):
            path = case / 'counters.json'
            current = json.loads(path.read_bytes()) if path.exists() else {'generation': 0, 'verification': 0, 'sdk': 0}
            current[name] += 1
            write_json(path, current)
            return current[name]

        def generate(self, workspace, cfg, task, run_dir, requests, budget, execution, on_process_start):
            sequence = requests.reserve()
            self.bump('generation')
            (workspace / 'sum_cli.py').write_bytes((case / 'correct-app.py').read_bytes())
            return {'status': 'completed_unverified', 'native_exit_code': 0, 'real_model_calls': 0,
                    'generator_kind': 'fixture', 'subscription': {'requests': [
                        {'sequence': sequence, 'status': 'completed', 'model': 'fixture', 'usage': None}]}}

        def verify(self, workspace, contract, run_dir, budget, on_process_start):
            index = self.bump('verification')
            if case.name == 'after_generation' and index == 1:
                raise OSError('Injected verifier interruption before any sandbox launch')
            self.bump('sdk')
            return super().verify(workspace, contract, run_dir, budget, on_process_start)
    return FixtureWithSDK()


def prepare_case(name):
    case = ROOT / name
    case.mkdir()
    repo = case / 'source'
    repo.mkdir()
    correct = (SOURCE / 'examples/acceptance-gate/sum_cli.py').read_bytes()
    assert correct.count(b"'sum': sum(data['numbers'])") == 1
    wrong = correct.replace(b"'sum': sum(data['numbers'])", b"'sum': sum(data['numbers']) + 1")
    (case / 'correct-app.py').write_bytes(correct)
    (repo / 'sum_cli.py').write_bytes(wrong)
    empty = case / 'empty-template'
    empty.mkdir()
    subprocess.run(['git', '-c', 'init.templateDir=' + str(empty), 'init', '--quiet', str(repo)], capture_output=True, check=True)
    subprocess.run(['git', '-C', str(repo), '-c', 'core.fsmonitor=false', 'add', '--', 'sum_cli.py'], capture_output=True, check=True)
    (case / 'verifier.py').write_bytes((SOURCE / 'examples/acceptance-gate/verifier.py').read_bytes())
    write(case / 'acceptance.json', {'schema': 1, 'checker': 'verifier.py', 'inputs': ['sum_cli.py'],
                                    'min_checks': 8, 'timeout_s': 30})
    return case


def child(name):
    case = ROOT / name
    workflow, Config, _ = imports()
    target = 'generate' if name == 'after_generation' else 'verify'
    def crash(stage, identity):
        if stage == target:
            write(case / 'checkpoint.json', {'workflow_id': identity, 'stage_committed_before_crash': stage,
                                             'generation_count': json.loads((case / 'counters.json').read_bytes())['generation']})
            os._exit(71 if target == 'generate' else 72)
    engine = workflow.Engine(case / 'source', backend=backend(case), checkpoint=crash)
    engine.start(Config(timeout_s=240, max_model_requests=3), 'Fixture correction; no model is called.',
                 case / 'acceptance.json', exe=str(CODEX), enable=True)
    raise RuntimeError('Crash injection was not reached')


def main():
    assert os.name == 'nt' and not ROOT.exists(), 'Preserve prior proof attempts'
    ROOT.mkdir()
    runtime = {}
    for path in [SOURCE / 'codex-flow.py', *sorted((SOURCE / 'runtime/codex_flow').glob('*.py'))]:
        relative = path.relative_to(SOURCE)
        dest = FROZEN / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())
        runtime[relative.as_posix()] = sha(dest)
    write(ROOT / 'preregistration.json', {'schema': 1, 'runtime_sha256': runtime,
          'codex_sha256': sha(CODEX), 'models': 0, 'generator': 'explicit fixture',
          'real_sdk': True, 'cases': ['after_generation', 'after_verification'], 'reruns': False,
          'per_workflow': {'max_request_reservations': 3, 'active_time_s': 240},
          'conditions': ['actual controller process death', 'committed stages reused',
                         'generation count stays one', 'counter not reset', 'real SDK eight checks',
                         'manual origin edit preserved', 'review bundle equals accepted snapshot']})
    rows = []
    workflow, _, _ = imports()
    for name in ('after_generation', 'after_verification'):
        case = prepare_case(name)
        repo = case / 'source'
        started = time.monotonic()
        process = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__)), '--output', str(ROOT), '--codex', str(CODEX), '--child', name],
                                 capture_output=True, timeout=90, check=False)
        (case / 'controller-stdout.bin').write_bytes(process.stdout)
        (case / 'controller-stderr.bin').write_bytes(process.stderr)
        assert process.returncode == (71 if name == 'after_generation' else 72), 'Unexpected child result; preserve diagnostics'
        point = json.loads((case / 'checkpoint.json').read_bytes())
        identity = point['workflow_id']
        engine = workflow.Engine(repo, backend=backend(case))
        before = engine.status(identity)
        assert before['stages']['generate']['state'] == 'succeeded' and before['requests_used'] == 1
        assert before['active_time_reserved_s'] > 0
        original = (repo / 'sum_cli.py').read_bytes()
        (repo / 'sum_cli.py').write_bytes(original + b'\n# independent manual edit while paused\n')
        manual_hash = sha(repo / 'sum_cli.py')
        if name == 'after_generation':
            interrupted = engine.resume(identity, enable=True, exe=str(CODEX))
            assert interrupted['state'] == 'failed' and interrupted['stages']['verify']['attempts'] == 1
            assert interrupted['stages']['generate']['attempts'] == 1 and interrupted['requests_used'] == 1
            write(case / 'interrupted.json', interrupted)
            engine = workflow.Engine(repo, backend=backend(case))
        result = engine.resume(identity, enable=True, exe=str(CODEX))
        assert result['accepted'] is True and result['state'] == 'completed'
        counters = json.loads((case / 'counters.json').read_bytes())
        assert counters['generation'] == 1 and counters['sdk'] == 1
        assert result['requests_used'] == 1 and result['stages']['generate']['attempts'] == 1
        assert result['active_time_used_s'] >= before['active_time_reserved_s']
        assert result['active_time_reserved_s'] == 0 and result['source_changed_since_start'] is True
        assert sha(repo / 'sum_cli.py') == manual_hash
        base = repo / '.codex-flow/workflows' / identity
        receipt = json.loads((base / result['stages']['verify']['output']['receipt']).read_bytes())
        assert receipt['status'] == 'passed' and receipt['checks_run'] == 8 and receipt['checks_failed'] == receipt['checks_skipped'] == 0
        assert receipt['model_calls'] == 0 and receipt['checker_executed_on_host'] is False
        assert receipt['sdk_root_exit_observed'] is True and receipt['capture_complete'] is True and receipt['exit_code'] == 0
        bundle = base / result['report']['bundle']
        assert sha(bundle / 'files/sum_cli.py') == sha(case / 'correct-app.py')
        cached = workflow.Engine(repo, backend=backend(case)).resume(identity, exe=str(CODEX))
        assert cached['accepted'] is True and counters == json.loads((case / 'counters.json').read_bytes())
        write(case / 'completed.json', result)
        rows.append({'case': name, 'passed': True, 'actual_crash_exit': process.returncode,
                     'generation_calls': counters['generation'], 'verification_calls': counters['verification'],
                     'real_sdk_launches': counters['sdk'], 'real_model_calls': 0, 'request_reservations': result['requests_used'],
                     'checks_passed': receipt['checks_run'], 'active_time_used_s': result['active_time_used_s'],
                     'conservative_crash_reservation_s': before['active_time_reserved_s'],
                     'manual_origin_preserved': True, 'source_project_updated': False,
                     'receipt_sha256': sha(base / result['stages']['verify']['output']['receipt']),
                     'bundle_manifest_sha256': sha(bundle / 'manifest.json'), 'controller_wall_s': round(time.monotonic() - started, 3)})
        print(json.dumps(rows[-1]), flush=True)
    assert all(sha(FROZEN / n) == expected for n, expected in runtime.items())
    result = {'schema': 1, 'kind': 'durable_workflow_recovery_sdk_proof', 'passed': True, 'cases': rows,
              'runtime_sha256': runtime, 'codex_sha256': sha(CODEX), 'real_model_calls': 0,
              'app_checker_host_executions': 0, 'proof_script_sha256': sha(Path(__file__)),
              'scope': 'recovery and acceptance mechanisms only; not model performance or generation quality'}
    write(ROOT / 'proof-result.json', result)
    print(json.dumps({'passed': True, 'cases': len(rows), 'model_calls': 0, 'result_sha256': sha(ROOT / 'proof-result.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True, help='Fresh, short output directory; all evidence is preserved')
    parser.add_argument('--codex', type=Path, required=True, help='Installed official Codex executable')
    parser.add_argument('--child', choices=['after_generation', 'after_verification'], help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError('Proof requires assertions enabled')
    ROOT = args.output.absolute()
    FROZEN = ROOT / 'runtime'
    CODEX = args.codex.absolute()
    if not ROOT.parent.is_dir():
        raise RuntimeError('Output parent must exist')
    import stat
    for point in (ROOT, *ROOT.parents):
        if point.exists() and (stat.S_ISLNK(point.lstat().st_mode) or getattr(point.lstat(), 'st_file_attributes', 0) & 0x400):
            raise RuntimeError('Linked output path refused')
    child(args.child) if args.child else main()
