"""Offline acceptance guards. Checker/application strings are never host-executed."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from codex_flow import acceptance, cli
from codex_flow.budget import ExecutionBudget
from codex_flow.contracts import PolicyError


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='flow-acceptance-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.workspace = self.root / 'project'
        self.workspace.mkdir()
        (self.workspace / 'app.py').write_text('owner fixture; never execute on host', encoding='utf-8')
        self.checker = self.root / 'checker.py'
        self.checker.write_text('checker fixture; never execute on host', encoding='utf-8')
        self.spec = self.root / 'acceptance.json'
        self.data = {'schema': 1, 'checker': 'checker.py', 'inputs': ['app.py'], 'min_checks': 2, 'timeout_s': 10}
        self.spec.write_text(json.dumps(self.data), encoding='utf-8')
        self.run_dir = self.workspace / '.codex-flow/runs/test'

    def prepare(self):
        return acceptance.prepare(self.workspace, acceptance.load_contract(self.spec))

    @staticmethod
    def raw(nonce='fresh', checks=None):
        return json.dumps({'schema': 1, 'nonce': nonce, 'checks': checks if checks is not None else
                           [{'id': 'a', 'status': 'passed'}, {'id': 'b', 'status': 'passed'}]}).encode()

    def fake_capture(self, command, env, scratch, deadline, cancel_file, control_file):
        self.assertNotIn('CODEX_HOME', env)
        (scratch / 'report.json').write_bytes(self.raw(command[-1]))
        return {'exit_code': 0, 'stop_reason': None, 'capture_complete': True,
                'sdk_root_exit_observed': True, 'capture': {}, 'output_limit_exceeded': False}

    def verify(self, capture=None, budget=None):
        prepared = self.prepare()
        with patch.object(acceptance, 'capture', side_effect=capture or self.fake_capture), \
             patch.object(acceptance, 'require_backend'):
            result = acceptance.verify('official-codex', self.workspace, prepared, self.run_dir,
                                       budget or ExecutionBudget(30))
        self.assertEqual(json.loads((self.run_dir / 'acceptance.json').read_text()), result)
        return result

    def test_contract_validation_is_strict_and_has_no_snapshot_side_effect(self):
        for field, value in (('schema', True), ('schema', 2), ('min_checks', 0), ('min_checks', True),
                             ('timeout_s', 301), ('inputs', []), ('inputs', ['../other']),
                             ('inputs', ['.']), ('inputs', ['.codex-flow/state']),
                             ('inputs', ['app.py', 'app.py']), ('checker', '../checker.py')):
            with self.subTest(field=field, value=value):
                self.spec.write_text(json.dumps({**self.data, field: value}), encoding='utf-8')
                with self.assertRaises((PolicyError, OSError)):
                    acceptance.load_contract(self.spec)
        self.assertFalse((self.workspace / '.codex-flow').exists())

    def test_duplicate_keys_and_nonfinite_metadata_are_refused(self):
        for raw in (b'{"schema":1,"schema":1}', b'{"schema":NaN}',
                    b'{"checks":' + b'[' * 2000 + b']' * 2000 + b'}'):
            self.spec.write_bytes(raw)
            with self.assertRaises(PolicyError):
                acceptance.load_contract(self.spec)

    def test_zero_duplicate_skipped_failed_stale_and_boolean_reports_do_not_pass(self):
        for raw in (self.raw(checks=[]), self.raw('old'),
                    self.raw(checks=[{'id': 'a', 'status': 'passed'}] * 2),
                    b'{"schema":true,"nonce":"fresh","checks":[]}'):
            with self.subTest(raw=raw), self.assertRaises(PolicyError):
                acceptance.assess_report(raw, 'fresh', 2)
        for status in ('failed', 'skipped'):
            counts = acceptance.assess_report(self.raw(checks=[{'id': 'a', 'status': status}]), 'fresh', 1)
            self.assertNotEqual(counts['checks_passed'], counts['checks_run'])

    def test_frozen_checker_and_original_contract_drift_are_rejected(self):
        prepared = self.prepare()
        self.assertTrue(prepared.unchanged())
        self.checker.write_text('changed', encoding='utf-8')
        self.assertFalse(prepared.unchanged())
        with patch.object(acceptance, 'capture') as capture:
            result = acceptance.verify('codex', self.workspace, prepared, self.run_dir, ExecutionBudget(30))
        capture.assert_not_called()
        self.assertFalse(result['accepted'])

    def test_gate_pass_binds_inputs_and_checker_and_writes_metadata(self):
        result = self.verify()
        self.assertTrue(result['accepted'])
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['checks_run'], 2)
        self.assertTrue(result['inputs_unchanged'])
        self.assertTrue(result['checker_unchanged'])
        self.assertFalse(result['checker_executed_on_host'])
        self.assertEqual(result['model_calls'], 0)

    def test_exit_zero_without_report_is_not_acceptance(self):
        def missing(*args):
            return {'exit_code': 0, 'stop_reason': None, 'capture_complete': True,
                    'sdk_root_exit_observed': True, 'capture': {}, 'output_limit_exceeded': False}
        self.assertFalse(self.verify(missing)['accepted'])

    def test_cancellation_after_sdk_completion_still_prevents_acceptance(self):
        def cancelled(*args):
            result = self.fake_capture(*args)
            args[4].touch()
            return result
        result = self.verify(cancelled)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['status'], 'cancelled')

    def test_incomplete_capture_nonzero_and_timeout_are_not_acceptance(self):
        for key, value in (('capture_complete', False), ('exit_code', 1), ('sdk_root_exit_observed', False),
                           ('output_limit_exceeded', True), ('stop_reason', 'timed_out')):
            with self.subTest(key=key):
                self.run_dir = self.workspace / '.codex-flow/runs' / key
                def failed(*args):
                    return {**self.fake_capture(*args), key: value}
                self.assertFalse(self.verify(failed)['accepted'])

    def test_changed_application_inventory_is_not_accepted(self):
        def changed(*args):
            result = self.fake_capture(*args)
            (self.workspace / 'app.py').write_text('changed by checker', encoding='utf-8')
            return result
        result = self.verify(changed)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['reason'], 'acceptance_evidence_invalid')

    def test_cancelled_or_expired_gate_never_starts_sandbox(self):
        budget = Mock()
        budget.remaining_s.return_value = 0
        with patch.object(acceptance, 'capture') as capture:
            self.assertFalse(self.verify(budget=budget)['accepted'])
        capture.assert_not_called()
        self.run_dir = self.workspace / '.codex-flow/runs/cancelled'
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / 'cancel.request').touch()
        self.assertEqual(self.verify()['status'], 'cancelled')

    def test_snapshot_cannot_be_reused_for_another_gate(self):
        prepared = self.prepare()
        with patch.object(acceptance, 'capture', side_effect=self.fake_capture), patch.object(acceptance, 'require_backend'):
            first = acceptance.verify('codex', self.workspace, prepared, self.run_dir, ExecutionBudget(30))
            original = (self.run_dir / 'acceptance.json').read_bytes()
            with self.assertRaises(PolicyError):
                acceptance.verify('codex', self.workspace, prepared, self.run_dir, ExecutionBudget(30))
        self.assertTrue(first['accepted'])
        self.assertEqual(original, (self.run_dir / 'acceptance.json').read_bytes())

    def test_inventory_reenumeration_detects_additions_and_missing_sources(self):
        folder = self.workspace / 'src'
        folder.mkdir()
        (folder / 'a.py').write_text('a', encoding='utf-8')
        before = acceptance.inventory(self.workspace, ('src',))
        (folder / 'b.py').write_text('b', encoding='utf-8')
        self.assertNotEqual(before, acceptance.inventory(self.workspace, ('src',)))
        with self.assertRaises(OSError):
            acceptance.inventory(self.workspace, ('absent.py',))

    def test_hardlinked_checker_is_refused(self):
        alias = self.root / 'checker-alias.py'
        try:
            os.link(self.checker, alias)
        except OSError:
            self.skipTest('Hardlink creation unavailable')
        with self.assertRaises(PolicyError):
            acceptance.load_contract(self.spec)

    def test_sandbox_command_uses_readonly_workspace_and_owned_scratch(self):
        prepared = self.prepare()
        state = self.workspace / '.codex-flow/native-state'
        state.mkdir()
        scratch = prepared.root / 'scratch'
        command = acceptance.sandbox_command('codex', self.workspace, prepared, scratch, scratch / 'report.json', 'n', (self.root / 'private',))
        self.assertEqual(command[:4], ['codex', 'sandbox', '-P', 'flow_acceptance'])
        self.assertIn('-I', command)
        self.assertIn('-B', command)
        profile = next(s for s in command if s.startswith('permissions.'))
        self.assertIn(json.dumps(str(self.workspace).replace('\\', '/')) + '="read"', profile)
        self.assertIn('network={enabled=false}', profile)
        self.assertIn(json.dumps(str(state).replace('\\', '/')) + '="deny"', profile)
        self.assertNotIn('danger-full-access', ' '.join(command))

    def test_checker_environment_has_no_credentials_or_inherited_python_imports(self):
        scratch = self.root / 'scratch'
        scratch.mkdir()
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'private', 'CODEX_HOME': 'private', 'GITHUB_TOKEN': 'private',
                                     'CUSTOM_AUTH': 'private', 'PYTHONPATH': 'private'}):
            env = acceptance.sandbox_environment(scratch)
        for key in ('OPENAI_API_KEY', 'CODEX_HOME', 'GITHUB_TOKEN', 'CUSTOM_AUTH', 'PYTHONPATH'):
            self.assertNotIn(key, env)
        self.assertEqual(env['HOME'], str(scratch / 'home'))

    def test_promote_only_a_completed_native_run_with_passed_gate(self):
        for status in ('failed', 'timed_out', 'cancelled'):
            result = acceptance.apply_result({'status': status}, {'status': 'passed', 'accepted': True})
            self.assertFalse(result['accepted'])
            self.assertEqual(result['status'], status)
        self.assertEqual(acceptance.apply_result({'status': 'completed_unverified'}, None)['status'], 'completed_unverified')
        self.assertEqual(acceptance.apply_result({'status': 'completed_unverified'}, {'accepted': True, 'status': 'passed'})['status'], 'completed_verified')
        self.assertFalse(acceptance.apply_result({'status': 'completed_unverified'}, {'accepted': True, 'status': 'failed'})['accepted'])

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(['--repo', str(self.workspace), *args])
        return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()

    def test_verify_defaults_to_inert_dry_run_without_any_state_or_native_call(self):
        with patch('codex_flow.native.executable') as exe, patch.object(acceptance, 'prepare') as prepare:
            code, result, _ = self.invoke('verify', '--acceptance-file', str(self.spec))
        self.assertEqual(code, 0)
        self.assertEqual(result['model_calls'], 0)
        exe.assert_not_called()
        prepare.assert_not_called()
        self.assertFalse((self.workspace / '.codex-flow').exists())

    def test_invalid_contract_stops_run_before_mercury_executable_or_model(self):
        self.spec.write_text('{}', encoding='utf-8')
        with patch('codex_flow.native.executable') as exe, patch('codex_flow.native.run') as run, \
             patch('codex_flow.mercury.MercuryBridge') as mercury:
            code, _, _ = self.invoke('run', 'task', '--enable', '--independent-steps', '2', '--acceptance-file', str(self.spec))
        self.assertEqual(code, 2)
        exe.assert_not_called()
        run.assert_not_called()
        mercury.assert_not_called()

    def test_run_gate_pass_failure_and_missing_config_have_distinct_status_exit_and_receipt(self):
        for accepted, expected_status, expected_code in ((True, 'completed_verified', 0),
                                                        (False, 'verification_failed', 3),
                                                        (None, 'completed_unverified', 0)):
            with self.subTest(accepted=accepted):
                def native_run(*args, **kwargs):
                    self.assertTrue(Path(args[4]).is_dir() is False)
                    return {'run_id': Path(args[4]).name, 'status': 'completed_unverified',
                            'wall_clock_s': .001, 'input_tokens': None, 'output_tokens': None, 'cached_tokens': None}
                with patch('codex_flow.native.executable', return_value='codex'), \
                     patch('codex_flow.native.run', side_effect=native_run), patch.object(acceptance, 'require_backend'), \
                     patch.object(acceptance, 'verify', return_value={'accepted': accepted, 'status': 'passed' if accepted else 'failed'}):
                    flags = ['--acceptance-file', str(self.spec)] if accepted is not None else []
                    code, result, _ = self.invoke('run', 'task', '--enable', *flags)
                self.assertEqual((code, result['status']), (expected_code, expected_status))
                self.assertEqual(result['accepted'], accepted is True)
                saved = json.loads((self.workspace / '.codex-flow/runs' / result['run_id'] / 'metrics.json').read_text())
                self.assertEqual(saved, result)

    def test_failed_native_run_never_launches_acceptance(self):
        def failed(*args, **kwargs):
            return {'run_id': Path(args[4]).name, 'status': 'timed_out', 'wall_clock_s': .001,
                    'input_tokens': None, 'output_tokens': None, 'cached_tokens': None}
        with patch('codex_flow.native.executable', return_value='codex'), \
             patch('codex_flow.native.run', side_effect=failed), patch.object(acceptance, 'require_backend'), \
             patch.object(acceptance, 'verify') as verify:
            code, result, _ = self.invoke('run', 'task', '--enable', '--acceptance-file', str(self.spec))
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'timed_out')
        self.assertFalse(result['accepted'])
        verify.assert_not_called()

    def test_unsupported_gate_backend_is_refused_before_generation(self):
        with patch.object(acceptance, 'require_backend', side_effect=PolicyError('unsupported sandbox')), \
             patch('codex_flow.native.run') as run, patch('codex_flow.native.executable') as executable:
            code, _, _ = self.invoke('run', 'task', '--enable', '--acceptance-file', str(self.spec))
        self.assertEqual(code, 2)
        run.assert_not_called()
        executable.assert_not_called()


if __name__ == '__main__':
    unittest.main()
