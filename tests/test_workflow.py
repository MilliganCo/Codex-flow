"""Durable stage wiring with labelled fixtures, no inference/checker execution."""
from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from codex_flow import cli, workflow
from codex_flow.config import Config
from codex_flow.contracts import PolicyError
from codex_flow.workflow_store import WorkflowError


class FixtureBackend:
    kind = 'fixture'

    def __init__(self):
        self.generations = self.verifications = 0
        self.fail_verify = False
        self.reject = False
        self.native_failure = False

    def fingerprint(self, explicit=None):
        return {'executable': 'fixture', 'backend_kind': self.kind, 'runtime': 'fixture-v1'}

    def generate(self, workspace, cfg, task, run_dir, requests, budget, execution, on_process_start):
        sequence = requests.reserve()
        self.generations += 1
        (workspace / 'app.txt').write_text('verified fixture output\n', encoding='utf-8')
        return {'status': 'failed' if self.native_failure else 'completed_unverified', 'native_exit_code': 0,
                'subscription': {'requests': [{'sequence': sequence, 'status': 'completed', 'model': 'fixture'}]},
                'fixture_generator': True, 'real_model_calls': 0}

    def verify(self, workspace, contract, run_dir, budget, on_process_start):
        self.verifications += 1
        if self.fail_verify:
            self.fail_verify = False
            raise OSError('synthetic verifier infrastructure interruption')
        return {'accepted': not self.reject, 'status': 'failed' if self.reject else 'passed',
                'checks_run': 1, 'checks_failed': int(self.reject), 'checks_skipped': 0,
                'sdk_root_exit_observed': True, 'fixture_verifier': True, 'real_model_calls': 0}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='flow-workflow-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', '-c', 'init.templateDir=' + str(self.root / 'empty-template'),
                        'init', '--quiet', str(self.repo)], capture_output=True, check=True)
        (self.repo / 'app.txt').write_text('original manual work\n', encoding='utf-8')
        subprocess.run(['git', '-C', str(self.repo), 'add', '--', 'app.txt'], capture_output=True, check=True)
        self.contract = self.root / 'acceptance.json'
        self.contract.write_text(json.dumps({'schema': 1, 'checker': 'checker.py', 'inputs': ['app.txt'],
                                            'min_checks': 1, 'timeout_s': 10}), encoding='utf-8')
        (self.root / 'checker.py').write_text('INERT UNIT FIXTURE - NEVER EXECUTE', encoding='utf-8')
        self.backend = FixtureBackend()
        self.engine = workflow.Engine(self.repo, backend=self.backend)
        self.cfg = Config(timeout_s=120, max_model_requests=3)

    def start(self):
        return self.engine.start(self.cfg, 'bounded fixture task', self.contract, enable=True)

    def test_dry_run_creates_no_control_state_or_backend_call(self):
        with patch.object(self.backend, 'fingerprint') as fingerprint:
            result = self.engine.start(self.cfg, 'task', self.contract, dry_run=True)
        self.assertTrue(result['dry_run'])
        self.assertEqual(result['model_calls'], 0)
        self.assertFalse((self.repo / '.codex-flow').exists())
        fingerprint.assert_not_called()

    def test_workflow_requires_explicit_enable_before_backend(self):
        with patch.object(self.backend, 'fingerprint') as fingerprint, self.assertRaises(PolicyError):
            self.engine.start(self.cfg, 'task', self.contract)
        fingerprint.assert_not_called()
        self.assertFalse((self.repo / '.codex-flow').exists())

    def test_complete_bundle_preserves_origin_and_labels_fixture(self):
        result = self.start()
        self.assertTrue(result['accepted'])
        self.assertEqual(result['state'], 'completed')
        self.assertEqual((self.backend.generations, self.backend.verifications), (1, 1))
        self.assertEqual(result['requests_used'], 1)
        self.assertLess(len(result['stages']['generate']['output']['tree']), 40)
        self.assertEqual((self.repo / 'app.txt').read_text(), 'original manual work\n')
        base = self.engine._base(result['workflow_id'])
        bundle = base / result['report']['bundle']
        self.assertEqual((bundle / 'files/app.txt').read_text(), 'verified fixture output\n')
        self.assertEqual(result['report']['summary']['backend_kind'], 'fixture')
        self.assertFalse(result['source_project_updated'])
        self.assertEqual(result['active_time_reserved_s'], 0)

    def test_verifier_interruption_resume_does_not_repeat_generation(self):
        self.backend.fail_verify = True
        failed = self.start()
        self.assertFalse(failed['accepted'])
        self.assertEqual(failed['stages']['generate']['state'], 'succeeded')
        self.assertEqual(failed['stages']['verify']['state'], 'failed')
        new_engine = workflow.Engine(self.repo, backend=self.backend)
        completed = new_engine.resume(failed['workflow_id'], enable=True)
        self.assertTrue(completed['accepted'])
        self.assertEqual((self.backend.generations, self.backend.verifications), (1, 2))
        self.assertEqual(completed['requests_used'], 1)
        self.assertEqual(completed['stages']['verify']['attempts'], 2)

    def test_pause_after_generation_and_resume_only_checks(self):
        def pause(stage, identity):
            if stage == 'generate':
                self.engine.store.signal(identity, 'pause')
        self.engine.checkpoint = pause
        paused = self.start()
        self.assertEqual(paused['state'], 'paused')
        self.assertEqual(self.backend.verifications, 0)
        completed = workflow.Engine(self.repo, backend=self.backend).resume(paused['workflow_id'], enable=True)
        self.assertTrue(completed['accepted'])
        self.assertEqual((self.backend.generations, self.backend.verifications), (1, 1))
        self.assertEqual(completed['requests_used'], paused['requests_used'])

    def test_unchanged_semantic_rejection_is_not_retried(self):
        self.backend.reject = True
        rejected = self.start()
        with self.assertRaises(WorkflowError):
            self.engine.resume(rejected['workflow_id'], enable=True)
        self.assertEqual(self.backend.verifications, 1)
        self.assertEqual(self.backend.generations, 1)

    def test_request_budget_is_not_reset_for_failed_generation(self):
        self.engine.checkpoint = None
        self.backend.native_failure = True
        self.cfg = replace(self.cfg, max_model_requests=1)
        failed = self.start()
        resumed = self.engine.resume(failed['workflow_id'], enable=True)
        self.assertFalse(resumed['accepted'])
        self.assertEqual(resumed['requests_used'], 1)
        self.assertEqual(self.backend.generations, 1)
        self.assertEqual(resumed['stages']['generate']['attempts'], 2)

    def test_changed_saved_checker_blocks_before_new_model_call(self):
        self.backend.fail_verify = True
        failed = self.start()
        base = self.engine._base(failed['workflow_id'])
        (base / 'inputs/checker.py').write_text('TAMPERED DATA', encoding='utf-8')
        with self.assertRaises(PolicyError):
            self.engine.resume(failed['workflow_id'], enable=True)
        self.assertEqual(self.backend.generations, 1)
        self.assertEqual(self.backend.verifications, 1)

    def test_changed_generation_blocks_reuse(self):
        self.backend.fail_verify = True
        failed = self.start()
        out = failed['stages']['generate']['output']
        (self.engine._base(failed['workflow_id']) / out['tree'] / 'app.txt').write_text('tampered', encoding='utf-8')
        with self.assertRaises(PolicyError):
            self.engine.resume(failed['workflow_id'], enable=True)
        self.assertEqual(self.backend.verifications, 1)

    def test_report_interruption_is_metadata_only_on_resume(self):
        original = workflow.snapshots.report_bundle
        with patch.object(workflow.snapshots, 'report_bundle', side_effect=OSError('synthetic report failure')):
            failed = self.start()
        self.assertEqual(failed['stages']['verify']['state'], 'succeeded')
        with patch.object(workflow.snapshots, 'report_bundle', wraps=original):
            completed = self.engine.resume(failed['workflow_id'], enable=True)
        self.assertTrue(completed['accepted'])
        self.assertEqual((self.backend.generations, self.backend.verifications), (1, 1))

    def test_original_changes_during_pause_are_not_mixed_into_snapshot(self):
        self.backend.fail_verify = True
        failed = self.start()
        (self.repo / 'app.txt').write_text('new independent user edit', encoding='utf-8')
        completed = self.engine.resume(failed['workflow_id'], enable=True)
        self.assertTrue(completed['accepted'])
        self.assertTrue(completed['report']['summary']['source_changed_since_start'])
        self.assertEqual((self.repo / 'app.txt').read_text(), 'new independent user edit')

    def test_corrupted_completed_bundle_is_not_reported_accepted(self):
        completed = self.start()
        path = self.engine._base(completed['workflow_id']) / completed['report']['bundle'] / 'files/app.txt'
        path.write_text('modified', encoding='utf-8')
        self.assertFalse(self.engine.status(completed['workflow_id'])['accepted'])
        with self.assertRaises(PolicyError):
            self.engine.resume(completed['workflow_id'], enable=True)

    def test_completed_resume_uses_no_new_generator_or_verifier(self):
        completed = self.start()
        second = self.engine.resume(completed['workflow_id'])
        self.assertTrue(second['accepted'])
        self.assertEqual((self.backend.generations, self.backend.verifications), (1, 1))

    def test_cancelled_workflow_does_not_restart(self):
        self.engine.checkpoint = lambda stage, identity: self.engine.store.signal(identity, 'pause') if stage == 'prepare' else None
        paused = self.start()
        cancelled = self.engine.signal(paused['workflow_id'], 'cancel')
        self.assertEqual(cancelled['state'], 'cancelled')
        with self.assertRaises(WorkflowError):
            self.engine.resume(cancelled['workflow_id'], enable=True)
        self.assertEqual(self.backend.generations, 0)

    def test_cli_workflow_dry_run_remains_inert(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.main(['--repo', str(self.repo), 'workflow', 'start', 'task',
                             '--acceptance-file', str(self.contract), '--dry-run'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['external_calls'], 0)
        self.assertFalse((self.repo / '.codex-flow').exists())

    def test_two_concurrent_resume_calls_start_only_one_verifier(self):
        self.engine.checkpoint = lambda stage, identity: self.engine.store.signal(identity, 'pause') if stage == 'generate' else None
        paused = self.start()
        entered, release = threading.Event(), threading.Event()
        original = self.backend.verify
        results, errors = [], []
        def waiting(*args):
            entered.set()
            if not release.wait(10):
                raise RuntimeError('test synchronization failed')
            return original(*args)
        def resume():
            try:
                results.append(workflow.Engine(self.repo, backend=self.backend).resume(paused['workflow_id'], enable=True))
            except BaseException as error:
                errors.append(error)
        with patch.object(self.backend, 'verify', side_effect=waiting):
            thread = threading.Thread(target=resume)
            thread.start()
            try:
                self.assertTrue(entered.wait(10))
                with self.assertRaises(WorkflowError):
                    workflow.Engine(self.repo, backend=self.backend).resume(paused['workflow_id'], enable=True)
            finally:
                release.set()
                thread.join(15)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(results[0]['accepted'])
        self.assertEqual((self.backend.generations, self.backend.verifications), (1, 1))

    def test_control_commands_work_even_with_invalid_current_project_config(self):
        self.engine.checkpoint = lambda stage, identity: self.engine.store.signal(identity, 'pause') if stage == 'prepare' else None
        paused = self.start()
        (self.repo / '.codex-flow/config.json').write_text('{invalid json', encoding='utf-8')
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.main(['--repo', str(self.repo), 'workflow', 'cancel', paused['workflow_id']])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['state'], 'cancelled')

    def test_queued_start_exposes_id_and_rejects_origin_drift_before_snapshot(self):
        with patch.object(self.engine, '_execute', side_effect=workflow.BusyError('fixture busy')):
            queued = self.start()
        self.assertEqual(queued['state'], 'pending')
        self.assertEqual(queued['reason'], 'project_busy')
        (self.repo / 'app.txt').write_text('changed while queued', encoding='utf-8')
        rejected = self.engine.resume(queued['workflow_id'], enable=True)
        self.assertFalse(rejected['accepted'])
        self.assertEqual(rejected['stages']['prepare']['output']['reason'], 'source_changed_before_snapshot')
        self.assertEqual(self.backend.generations, 0)

    def test_final_budget_settlement_cannot_create_false_success(self):
        original = workflow.ActiveBudget
        class ExhaustAtSettlement(original):
            def __exit__(budget, *args):
                super().__exit__(*args)
                budget.store.charge_active(budget.owner, 120)
        with patch.object(workflow, 'ActiveBudget', ExhaustAtSettlement):
            result = self.start()
        self.assertEqual(result['stages']['report']['state'], 'succeeded')
        self.assertEqual(result['state'], 'failed')
        self.assertFalse(result['accepted'])
        self.assertEqual(result['active_time_remaining_s'], 0)


if __name__ == '__main__':
    unittest.main()
