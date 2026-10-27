"""Owner initialization reads project data; test/checker code is never host-executed."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from codex_flow import acceptance, cli, workflow_setup as setup, workflow_display as display, workflow
from codex_flow.config import Config
from codex_flow.contracts import PolicyError

TEST = b'import unittest\nclass Tests(unittest.TestCase):\n    def test_case(self): self.assertTrue(True)\n'


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='flow-setup-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve()
        subprocess.run(['git', '-c', 'init.templateDir=' + str(self.repo / 'empty-template'),
                        'init', '--quiet', str(self.repo)], capture_output=True, check=True)
        (self.repo / 'tests').mkdir()
        (self.repo / 'tests/test_app.py').write_bytes(TEST)
        (self.repo / 'app.py').write_bytes(b'# PROJECT FIXTURE; NEVER EXECUTE ON HOST\n')

    def invoke(self, *flags):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(['--repo', str(self.repo), 'workflow', *flags])
        return code, out.getvalue(), err.getvalue()

    def test_inspection_has_no_setup_or_native_side_effect(self):
        with patch('codex_flow.native.executable') as native:
            result = setup.initialize(self.repo, dry_run=True)
        self.assertEqual(result['setup_state'], 'planned')
        self.assertEqual(result['baseline_test_files'], 1)
        self.assertFalse((self.repo / '.codex-flow').exists())
        native.assert_not_called()

    def test_creation_selects_valid_bound_contract_without_changing_config(self):
        result = setup.initialize(self.repo)
        contract = setup.default_contract(self.repo)
        self.assertEqual(result['model_calls'], 0)
        self.assertEqual(contract.min_checks, 1)
        self.assertEqual(set(contract.inputs), {'app.py', 'tests'})
        self.assertFalse((self.repo / '.codex-flow/config.json').exists())
        self.assertEqual((self.repo / 'tests/test_app.py').read_bytes(), TEST)

    def test_idempotent_init_preserves_edited_task(self):
        first = setup.initialize(self.repo)
        task = self.repo / first['task_file']
        task.write_text('Actual owner task', encoding='utf-8')
        second = setup.initialize(self.repo)
        self.assertEqual(second['setup_state'], 'existing')
        self.assertEqual(second['task_file'], first['task_file'])
        self.assertEqual(task.read_text(), 'Actual owner task')

    def test_changed_checker_cannot_be_silently_trusted(self):
        first = setup.initialize(self.repo)
        checker = (self.repo / first['acceptance_file']).parent / 'checker.py'
        checker.write_text('Owner modification; never execute', encoding='utf-8')
        with self.assertRaises(PolicyError):
            setup.default_contract(self.repo)
        with self.assertRaises(PolicyError):
            setup.initialize(self.repo)
        refreshed = setup.initialize(self.repo, refresh=True)
        self.assertNotEqual(first['acceptance_file'], refreshed['acceptance_file'])
        self.assertEqual(checker.read_text(), 'Owner modification; never execute')
        self.assertTrue(setup.default_contract(self.repo).path.is_file())

    def test_checker_swap_during_binding_is_rejected(self):
        result = setup.initialize(self.repo)
        original = acceptance.load_contract
        def changed(path):
            (path.parent / 'checker.py').write_bytes(b'# changed after binding validation\n')
            return original(path)
        with patch('codex_flow.acceptance.load_contract', side_effect=changed):
            with self.assertRaisesRegex(PolicyError, 'during admission'):
                setup.default_contract(self.repo)
        self.assertTrue((self.repo / result['acceptance_file']).is_file())

    def test_bound_checker_swap_before_engine_admission_never_starts_backend(self):
        setup.initialize(self.repo)
        contract = setup.default_contract(self.repo)
        contract.checker.write_bytes(b'# changed after owner selection\n')
        engine = workflow.Engine(self.repo)
        with patch.object(engine.backend, 'fingerprint') as backend:
            with self.assertRaisesRegex(PolicyError, 'during admission'):
                engine.start(Config(), 'Actual task', contract, enable=True)
        backend.assert_not_called()
        self.assertFalse(engine.root.exists())

    def test_engine_freezes_the_same_execution_contract_that_was_admitted(self):
        setup.initialize(self.repo)
        selected = setup.default_contract(self.repo)
        execution = self.repo / 'execution.json'
        data = {'schema': 1, 'handoff_artifact': 'tests/handoff.md', 'tasks': [
            {'id': 'helper', 'role': 'executor', 'goal': 'Propose additional tests',
             'allowed_paths': ['tests'], 'dependencies': [], 'artifacts': ['tests/test_extra.py'],
             'acceptance_criteria': ['Exercise boundary cases'], 'risk_level': 'low'},
            {'id': 'chief', 'role': 'chief', 'goal': 'Integrate the proposal',
             'allowed_paths': ['app.py'], 'dependencies': [], 'artifacts': ['app.py'],
             'acceptance_criteria': ['Preserve all baseline tests'], 'risk_level': 'low'}]}
        execution.write_text(json.dumps(data), encoding='utf-8')
        original = workflow.execution_contract.load
        admitted = original(execution, self.repo)
        def swap_after_read(path, repo):
            execution.write_text('{"changed":true}', encoding='utf-8')
            return admitted
        engine = workflow.Engine(self.repo)
        with patch('codex_flow.execution_contract.load', side_effect=swap_after_read) as load:
            with patch('codex_flow.execution_contract.admit', wraps=workflow.execution_contract.admit) as admit:
                with patch.object(engine.backend, 'fingerprint', side_effect=OSError('stop before backend')):
                    with self.assertRaisesRegex(OSError, 'stop before backend'):
                        engine.start(Config(), 'Actual task', selected, execution, enable=True)
        self.assertEqual(load.call_count, 1)
        admit.assert_called_once_with(admitted, selected.inputs)
        self.assertFalse(engine.root.exists())

    def test_changed_options_require_explicit_new_version(self):
        setup.initialize(self.repo)
        with self.assertRaises(PolicyError):
            setup.initialize(self.repo, allow_skips=1)
        result = setup.initialize(self.repo, allow_skips=1, refresh=True)
        self.assertEqual(result['options']['allow_skips'], 1)

    def test_bad_or_missing_tests_fail_before_writes(self):
        (self.repo / 'tests/test_app.py').write_bytes(b'def test_pytest_style(): pass\n')
        with self.assertRaises(PolicyError):
            setup.initialize(self.repo)
        self.assertFalse((self.repo / '.codex-flow').exists())
        for directory in ('../tests', '.CoDeX-FlOw/tests', 'tests.', '/tmp/tests'):
            with self.subTest(directory=directory), self.assertRaises(ValueError):
                setup.initialize(self.repo, test_dir=directory)

    def test_inputs_must_bind_baseline_tests(self):
        with self.assertRaises(PolicyError):
            setup.initialize(self.repo, inputs=['app.py'])
        with self.assertRaises(ValueError):
            setup.initialize(self.repo, allow_skips=True)
        self.assertFalse((self.repo / '.codex-flow').exists())

    def test_active_revision_traversal_is_refused(self):
        setup.initialize(self.repo)
        path = self.repo / '.codex-flow/project/active.json'
        value = json.loads(path.read_bytes())
        value['revision'] = '../elsewhere'
        path.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaises(PolicyError):
            setup.default_contract(self.repo)

    def test_start_without_owner_selection_does_not_touch_native(self):
        with patch('codex_flow.native.executable') as native:
            code, _, error = self.invoke('start', 'Actual task', '--enable')
        self.assertEqual(code, 2)
        self.assertIn('workflow init', error)
        native.assert_not_called()
        self.assertFalse((self.repo / '.codex-flow').exists())

    def test_initialized_start_dry_run_needs_only_task(self):
        setup.initialize(self.repo)
        with patch('codex_flow.native.executable') as native, patch('codex_flow.workflow.Engine.store') as store:
            code, out, _ = self.invoke('start', 'Actual task', '--dry-run')
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertTrue(result['dry_run'])
        self.assertEqual(result['model_calls'], 0)
        native.assert_not_called()
        store.assert_not_called()

    def test_placeholder_task_is_not_dispatched(self):
        result = setup.initialize(self.repo)
        with patch('codex_flow.native.executable') as native:
            code, _, error = self.invoke('start', '--task-file', str(self.repo / result['task_file']), '--enable')
        self.assertEqual(code, 2)
        self.assertIn('actual requested change', error)
        native.assert_not_called()

    def test_init_human_and_json_modes_are_explicit(self):
        code, text, _ = self.invoke('init', '--dry-run')
        self.assertEqual(code, 0)
        self.assertIn('Настройка:', text)
        code, text, _ = self.invoke('init', '--dry-run', '--json')
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(text)['dry_run'])

    def test_model_catalog_has_no_native_or_config_access(self):
        (self.repo / '.codex-flow').mkdir()
        (self.repo / '.codex-flow/config.json').write_text('{invalid', encoding='utf-8')
        with patch('codex_flow.native.executable') as native:
            code, text, _ = self.invoke('models', '--json', '--cli-version', 'codex-cli 0.164.0-alpha.11.1')
        self.assertEqual(code, 0)
        terra = next(m for m in json.loads(text)['models'] if m['id'] == 'gpt-6.1-terra')
        self.assertTrue(terra['cli_compatible'])
        self.assertFalse(terra['flow_dispatch_enabled'])
        self.assertIsNone(terra['native_account_verified'])
        native.assert_not_called()

    def test_human_preview_and_integrity_never_claim_live_project_acceptance(self):
        preview = display.status({'dry_run': True, 'stages': ['prepare', 'generate']})
        self.assertIn('без исполнения', preview)
        result = {'workflow_id': 'a' * 32, 'state': 'completed', 'accepted': False, 'integrity': 'failed',
                  'stages': {'generate': {'state': 'succeeded', 'attempts': 1}}, 'requests_used': 1,
                  'requests_remaining': 9, 'active_time_remaining_s': 10.5, 'launch_pending': True,
                  'reason': '\x1b[31mnot accepted', 'source_changed_since_start': True}
        text = display.status(result)
        self.assertIn('приёмка недействительна', text)
        self.assertNotIn('\x1b', text)
        self.assertIn('no', text)
        self.assertIn('State: completed', display.status(result, 'en'))


if __name__ == '__main__':
    unittest.main()
