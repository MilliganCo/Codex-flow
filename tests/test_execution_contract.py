"""Offline execution-contract admission and evidence; fixtures are never executed."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from codex_flow import acceptance, cli, execution_contract as execution, native
from codex_flow.config import Config
from codex_flow.contracts import PolicyError


class ExecutionContractTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='flow-execution-contract-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.workspace = self.root / 'project'
        self.workspace.mkdir()
        self.spec = self.root / 'execution.json'
        self.data = {'schema': 1, 'handoff_artifact': 'evidence/proposal.txt', 'tasks': [
            self.task('chief', 'chief', 'app'), self.task('helper', 'executor', 'lib')]}
        self.acceptance = self.root / 'acceptance.json'
        self.acceptance.write_text(json.dumps({'schema': 1, 'checker': 'checker.py',
            'inputs': ['app', 'lib', 'evidence'], 'min_checks': 1, 'timeout_s': 10}), encoding='utf-8')
        (self.root / 'checker.py').write_text('INERT CHECKER FIXTURE; NEVER EXECUTE', encoding='utf-8')
        self.write(self.data)

    @staticmethod
    def task(identity, role, scope):
        return {'id': identity, 'role': role, 'goal': 'Implement a bounded module',
                'allowed_paths': [scope], 'dependencies': [], 'artifacts': [scope + '/result.py'],
                'acceptance_criteria': ['Matches the declared interface'], 'risk_level': 'low'}
    def write(self, data):
        self.spec.write_text(json.dumps(data), encoding='utf-8')
    def load(self, data=None):
        if data is not None:
            self.write(data)
        return execution.load(self.spec, self.workspace)
    def invalid(self, data):
        with self.assertRaises(PolicyError):
            self.load(data)
    def evidence(self):
        contract = self.load()
        for name in contract.artifacts:
            path = self.workspace / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('INERT SOURCE OR HANDOFF FIXTURE', encoding='utf-8')
        child = {'agent_role': 'worker', 'model': 'gpt-6-luna', 'requested_effort': 'medium', 'depth': 1, 'tokens_used': 10}
        requests = [{'model': m, 'effort': e, 'status': 'completed', 'actual_model': m,
                     'semantic_completion_observed': True} for m, e in
                    [('gpt-6.1-sol', 'xhigh'), ('gpt-6-luna', 'medium')]]
        result = {'status': 'completed_unverified', 'native_child_count': 1,
                  'native_metadata': {'status': 'observed', 'children': [child]},
                  'subscription': {'requests': requests, 'active_requests': 0}}
        return contract, execution.freeze(contract), result
    def test_valid_contract_resolves_repo_scopes_and_is_inert(self):
        contract = self.load()
        self.assertEqual(contract.batches, (('chief', 'helper'),))
        self.assertEqual(contract.tasks[1].allowed_paths, (str(self.workspace / 'lib'),))
        self.assertEqual(contract.summary()['executor']['model'], 'gpt-6-luna')
        self.assertIn('sole_writer', contract.summary()['chief'])
        self.assertIn('EXECUTION_CONTRACT_JSON:', contract.instructions())
        self.assertEqual(list(self.workspace.iterdir()), [])
    def test_strict_top_level_and_task_schema(self):
        for field, value in [('schema', True), ('schema', 2), ('extra', 'ignored'), ('tasks', []),
                             ('tasks', [self.data['tasks'][0]]), ('tasks', self.data['tasks'] * 5)]:
            with self.subTest(field=field, value=value):
                self.invalid({**self.data, field: value})
        for field in self.data['tasks'][0]:
            data = deepcopy(self.data)
            del data['tasks'][0][field]
            with self.subTest(missing=field):
                self.invalid(data)
        data = deepcopy(self.data)
        data['tasks'][0]['model'] = 'unapproved'
        self.invalid(data)
        self.spec.write_bytes(b'{"schema":1,"schema":1}')
        with self.assertRaises(PolicyError):
            execution.load(self.spec, self.workspace)
    def test_text_list_and_numeric_bounds(self):
        for field, value in [('id', '../bad'), ('goal', ''), ('goal', 'x' * 2049), ('goal', '\0'),
                             ('allowed_paths', []), ('allowed_paths', ['app', 'APP']),
                             ('dependencies', ['helper', 'helper']), ('dependencies', [1]),
                             ('acceptance_criteria', []), ('acceptance_criteria', ['x' * 257])]:
            data = deepcopy(self.data)
            data['tasks'][0][field] = value
            with self.subTest(field=field, value=value):
                self.invalid(data)
        self.spec.write_bytes(b' ' * (execution.MAX_BYTES + 1))
        with self.assertRaises(PolicyError):
            execution.load(self.spec, self.workspace)
    def test_duplicate_unknown_cyclic_and_serial_task_graphs_are_refused(self):
        for identity, dependencies in [('helper', []), ('chief', ['missing']), ('chief', ['helper'])]:
            data = deepcopy(self.data)
            data['tasks'][0].update(id=identity, dependencies=dependencies)
            with self.subTest(identity=identity, dependencies=dependencies):
                self.invalid(data)
        data = deepcopy(self.data)
        data['tasks'][0]['dependencies'] = ['helper']
        data['tasks'][1]['dependencies'] = ['chief']
        self.invalid(data)
    def test_roles_risk_and_executor_independence_are_mandatory(self):
        for field, value in [('role', 'planner'), ('role', 'executor'), ('risk_level', 'normal')]:
            data = deepcopy(self.data)
            data['tasks'][0][field] = value
            self.invalid(data)
        data = deepcopy(self.data)
        data['tasks'][1]['dependencies'] = ['chief']
        self.invalid(data)
    def test_casefold_overlap_artifact_ownership_and_distinct_handoff(self):
        for scope, artifact in [('APP/nested', 'APP/nested/out.py'), ('lib', 'app/out.py')]:
            data = deepcopy(self.data)
            data['tasks'][1].update(allowed_paths=[scope], artifacts=[artifact])
            self.invalid(data)
        for handoff in ('APP/result.py', 'app/result.py/child'):
            self.invalid({**self.data, 'handoff_artifact': handoff})

    def test_traversal_absolute_and_reserved_paths_are_refused_everywhere(self):
        for name in ('../escape', '/absolute', 'C:/outside', 'app\\x', '.git/state',
                     '.codex-flow/state', '.CoDeX-FlOw/state', '.home/state', '.tmp/state'):
            for field in ('allowed_paths', 'artifacts', 'handoff_artifact'):
                data = deepcopy(self.data)
                if field == 'handoff_artifact':
                    data[field] = name
                else:
                    data['tasks'][0][field] = [name]
                    if field == 'allowed_paths':
                        data['tasks'][0]['artifacts'] = [name + '/out.py']
                with self.subTest(name=name, field=field):
                    self.invalid(data)
    def test_reparse_point_in_responsibility_scope_is_refused(self):
        real_lstat = Path.lstat
        def lstat(path, *args, **kwargs):
            if path == self.workspace / 'app':
                return SimpleNamespace(st_mode=0, st_file_attributes=0x400)
            return real_lstat(path, *args, **kwargs)
        with patch.object(Path, 'lstat', lstat), self.assertRaises(PolicyError):
            self.load()

    def test_admission_requires_all_artifacts_and_respects_existing_conflicts(self):
        contract = self.load()
        self.assertEqual(execution.admit(contract, ('app', 'lib', 'evidence')).strategy, 'parallel')
        for kwargs in ({'single': True}, {'conflicting': True}, {'risk': 'critical'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(PolicyError):
                execution.admit(contract, ('app', 'lib', 'evidence'), **kwargs)
        for inputs in (('app', 'lib'), ('app', 'evidence'), ('app/result.py/child', 'lib', 'evidence')):
            with self.subTest(inputs=inputs), self.assertRaises(PolicyError):
                execution.admit(contract, inputs)
    def test_freeze_binds_original_and_snapshot_bytes(self):
        contract = self.load()
        frozen = execution.freeze(contract)
        self.assertEqual(frozen.path.read_bytes(), contract.raw)
        for path in (self.spec, frozen.path):
            path.write_bytes(contract.raw + b' ')
            self.assertFalse(frozen.unchanged())
            path.write_bytes(contract.raw)
            self.assertTrue(frozen.unchanged())
    def test_observation_binds_artifacts_and_limits_semantic_claim(self):
        contract, frozen, result = self.evidence()
        observed = execution.observe(contract, frozen, result)
        self.assertTrue(observed['verified'])
        self.assertEqual(set(observed['artifact_sha256']), set(contract.artifacts))
        self.assertFalse(observed['proposal_use_independently_verified'])
    def test_missing_wrong_or_unused_child_is_degraded(self):
        contract, frozen, good = self.evidence()
        cases = [{'status': 'failed'}, {'native_child_count': 2}, {'native_metadata': {}},
                 {'native_metadata': {'status': 'observed', 'children': []}}]
        for field, value in [('agent_role', 'reviewer'), ('model', 'gpt-6.1-sol'), ('requested_effort', 'high'),
                             ('depth', 2), ('tokens_used', 0), ('tokens_used', True)]:
            result = deepcopy(good)
            result['native_metadata']['children'][0][field] = value
            cases.append(result)
        for change in cases:
            with self.subTest(change=change):
                self.assertFalse(execution.observe(contract, frozen, {**good, **change})['verified'])

    def test_completion_requires_both_actual_models_and_allowed_request_profiles(self):
        contract, frozen, good = self.evidence()
        for index in (0, 1):
            for field, value in [('actual_model', 'wrong'), ('status', 'failed'),
                                 ('semantic_completion_observed', False), ('effort', 'high')]:
                result = deepcopy(good)
                result['subscription']['requests'][index][field] = value
                with self.subTest(index=index, field=field):
                    self.assertFalse(execution.observe(contract, frozen, result)['verified'])

    def test_missing_empty_or_changed_artifact_does_not_reuse_old_hash(self):
        contract, frozen, result = self.evidence()
        path = self.workspace / contract.handoff
        path.write_bytes(b'')
        self.assertFalse(execution.observe(contract, frozen, result)['verified'])
        path.unlink()
        self.assertFalse(execution.observe(contract, frozen, result)['verified'])
        self.spec.write_bytes(contract.raw + b' ')
        self.assertFalse(execution.observe(contract, frozen, result)['checks']['contract_unchanged'])

    def test_executor_profiles_change_only_worker_and_suppress_legacy_reviewer(self):
        old = native.role_profiles(self.workspace, named_permissions=False)
        new = native.role_profiles(self.workspace, named_permissions=False, executor_mode=True)
        for name in old:
            left, right = old[name].read_text(), new[name].read_text()
            if name == 'worker':
                self.assertIn('gpt-6-luna', right)
                self.assertIn('shell_tool = false', right)
                self.assertEqual(right.replace('gpt-6-luna', 'gpt-6.1-sol').replace('shell_tool = false\n', ''), left)
            else:
                self.assertEqual(left, right)
        old_args = native.argv('inert', self.workspace, Config(), parallel=True)
        new_args = native.argv('inert', self.workspace, Config(), parallel=True, executor_mode=True)
        self.assertIn('Exactly one initial read-only reviewer', ' '.join(old_args))
        self.assertNotIn('Exactly one initial read-only reviewer', ' '.join(new_args))
        with self.assertRaises(PolicyError):
            native.argv('inert', self.workspace, Config(), executor_mode=True)
    def invoke(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with ExitStack() as stack:
            for owner, name in [(native, 'executable'), (native, 'run'), (native, 'role_profiles'),
                                (acceptance, 'require_backend'), (acceptance, 'prepare'),
                                (acceptance, 'capture'), (execution, 'freeze')]:
                stack.enter_context(patch.object(owner, name, side_effect=AssertionError('forbidden: ' + name)))
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli.main(['--repo', str(self.workspace), 'run', 'task', '--dry-run', *args])
        return code, json.loads(stdout.getvalue()) if stdout.getvalue() else {}, stderr.getvalue()

    def test_cli_contract_dry_run_has_no_native_provider_or_state_side_effects(self):
        code, out, _ = self.invoke('--execution-contract', str(self.spec), '--acceptance-file', str(self.acceptance))
        self.assertEqual(code, 0)
        self.assertEqual(out['external_calls'], 0)
        self.assertEqual(out['route']['source'], 'execution_contract')
        self.assertTrue(out['execution_contract']['configured'])
        self.assertEqual(list(self.workspace.iterdir()), [])
    def test_cli_requires_acceptance_preserves_admission_and_legacy_routes(self):
        self.assertEqual(self.invoke('--execution-contract', str(self.spec))[0], 2)
        for flags in (['--single-agent'], ['--strategy', 'single'], ['--conflicting-paths'], ['--risk-level', 'high']):
            self.assertEqual(self.invoke('--execution-contract', str(self.spec), '--acceptance-file',
                                         str(self.acceptance), *flags)[0], 2)
        for flags, expected in [([], 'single'), (['--independent-steps', '2'], 'parallel'),
                                (['--independent-steps', '2', '--single-agent'], 'single')]:
            code, out, _ = self.invoke(*flags)
            self.assertEqual((code, out['route']['strategy']), (0, expected))
            self.assertFalse(out['execution_contract']['configured'])
        self.assertEqual(list(self.workspace.iterdir()), [])
