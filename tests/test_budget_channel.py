"""Owned publisher lifecycle and process-local MCP configuration; no models."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from codex_flow.budget import BudgetChannel, ExecutionBudget
from codex_flow.budget_stdio import BudgetStdio
from codex_flow.config import Config
from codex_flow import native
from codex_flow.subscription import RequestBudget


class BudgetChannelTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def test_fresh_publication_and_audit_survive_lifecycle(self):
        requests = RequestBudget(8)
        with BudgetChannel(self.root, ExecutionBudget(100, 8), requests) as channel:
            tool = BudgetStdio(self.root, channel.status_file, channel.audit_dir)
            self.assertEqual(tool.status()['budget']['requests_remaining'], 8)
            requests.reserve()
            channel.publish()
            self.assertEqual(tool.status()['budget']['requests_used'], 1)
        report = channel.summary()
        self.assertEqual(report, {'configured': True, 'publisher_failed': False,
                         'publisher_error_counts': {}, 'publisher_last_errno': None,
                         'publisher_retry_attempts': 0, 'publisher_recovered_publications': 0,
                         'publisher_failed_publications': 0,
                         'publisher_last_winerror': None,
                         'status_calls': 2, 'successful_calls': 2, 'unavailable_calls': 0,
                         'audit_valid': True, 'phases': {'build': 2}})
        self.assertFalse(channel._thread.is_alive())

    def test_corrupt_owned_audit_is_not_accepted(self):
        channel = BudgetChannel(self.root, ExecutionBudget(100), RequestBudget(80))
        (channel.audit_dir / ('a' * 32 + '.jsonl')).write_text('{"command":"private"}\n')
        self.assertFalse(channel.summary()['audit_valid'])
        self.assertNotIn('private', json.dumps(channel.summary()))

    def test_publication_failure_is_visible(self):
        channel = BudgetChannel(self.root, ExecutionBudget(100), RequestBudget(80))
        with patch('codex_flow.telemetry.write_json', side_effect=OSError):
            channel.publish()
        self.assertTrue(channel.summary()['publisher_failed'])
        self.assertEqual(channel.summary()['publisher_error_counts'], {'io': 1})
        self.assertEqual(channel.summary()['publisher_failed_publications'], 1)

    def test_validation_and_unrelated_permission_errors_never_retry(self):
        error = PermissionError(13, 'synthetic error; never record its message')
        error.winerror = 33
        for failure, kind in ((error, 'io'), (ValueError('private details'), 'validation')):
            with self.subTest(kind=kind):
                channel = BudgetChannel(self.root, ExecutionBudget(100), RequestBudget(80))
                with patch('codex_flow.telemetry.write_json', side_effect=failure) as write:
                    channel.publish()
                self.assertEqual(write.call_count, 1)
                summary = channel.summary()
                self.assertTrue(summary['publisher_failed'])
                self.assertEqual(summary['publisher_error_counts'], {kind: 1})
                self.assertEqual(summary['publisher_retry_attempts'], 0)
                self.assertEqual(summary['publisher_failed_publications'], 1)
                self.assertNotIn('private details', json.dumps(summary))
                self.assertNotIn('synthetic error', json.dumps(summary))

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing regression')
    def test_transient_reader_lock_recovers_atomic_publication_without_hiding_error(self):
        import threading
        from codex_flow.telemetry import write_json
        requests = RequestBudget(80)
        channel = BudgetChannel(self.root, ExecutionBudget(100), requests)
        channel.publish()
        ready, release = threading.Event(), threading.Event()
        def read():
            with channel.status_file.open('rb'):
                ready.set()
                release.wait(timeout=5)
        thread = threading.Thread(target=read)
        thread.start()
        self.addCleanup(release.set)
        self.assertTrue(ready.wait(timeout=2))
        def writing(*args, **kwargs):
            try:
                return write_json(*args, **kwargs)
            except PermissionError:
                # First attempt genuinely collided. Close that reader before retry.
                release.set()
                thread.join(timeout=2)
                raise
        requests.reserve()
        with patch('codex_flow.telemetry.write_json', side_effect=writing):
            channel.publish()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertFalse(channel.publisher_failed)
        self.assertEqual(json.loads(channel.status_file.read_text())['budget']['requests_used'], 1)
        self.assertEqual(channel.summary()['publisher_error_counts'], {'io': 1})
        self.assertEqual(channel.summary()['publisher_recovered_publications'], 1)
        self.assertEqual(channel.summary()['publisher_retry_attempts'], 1)
        self.assertEqual(channel.summary()['publisher_failed_publications'], 0)
        self.assertEqual(list(channel.root.glob('.flow-*.tmp')), [])

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing reproduction')
    def test_legacy_read_handle_reproduces_atomic_replace_failure_with_typed_diagnostics(self):
        channel = BudgetChannel(self.root, ExecutionBudget(100), RequestBudget(80))
        channel.publish()
        before = channel.status_file.read_bytes()
        with channel.status_file.open('rb'):
            channel.publish()
            self.assertTrue(channel.publisher_failed)
            self.assertEqual(channel.status_file.read_bytes(), before)
        channel.publish()
        self.assertTrue(channel.publisher_failed)  # Do not hide a recovered failure.
        summary = channel.summary()
        self.assertEqual(summary['publisher_error_counts'], {'io': 4})
        self.assertEqual(summary['publisher_retry_attempts'], 3)
        self.assertEqual(summary['publisher_failed_publications'], 1)
        self.assertEqual(summary['publisher_last_errno'], 13)
        self.assertIn(summary['publisher_last_winerror'], (5, 32))

    def test_only_parallel_config_has_readonly_fixed_path_mcp(self):
        channel = BudgetChannel(self.root, ExecutionBudget(100), RequestBudget(80))
        command = native.argv('fake', self.root, Config(), parallel=True, budget_channel=channel)
        overrides = dict(command[i+1].split('=', 1) for i, value in enumerate(command) if value == '-c')
        self.assertEqual(json.loads(overrides['mcp_servers.flow_budget.enabled_tools']), ['status'])
        self.assertEqual(json.loads(overrides['mcp_servers.flow_budget.tools.status.approval_mode']), 'approve')
        args = json.loads(overrides['mcp_servers.flow_budget.args'])
        self.assertEqual(args[:3], ['-I', '-B', '-c'])
        self.assertIn('runpy.run_module', args[3])
        self.assertEqual(args[-4:], ['--status-file', str(channel.status_file), '--audit-dir', str(channel.audit_dir)])
        self.assertNotIn('mcp_servers', ' '.join(native.argv('fake', self.root, Config())))

    def test_gateway_suffix_disabled_by_default_and_single_has_no_channel(self):
        for parallel in (False, True):
            run_dir = self.root / ('parallel' if parallel else 'single')
            base = {'input_tokens': 0, 'output_tokens': 0, 'cached_tokens': 0}
            with patch.object(native, '_run', return_value=base.copy()) as execute, \
                    patch('codex_flow.subscription.SubscriptionGateway') as gateway:
                instance = gateway.return_value.__enter__.return_value
                instance.summary.return_value = {'completed_requests': 0, 'aggregate_usage': {}}
                native.run('fake', self.root, Config(), 'task', run_dir, parallel=parallel)
            self.assertFalse(gateway.call_args.kwargs['guidance'])
            self.assertEqual(execute.call_args.kwargs['budget_channel'] is not None, parallel)

    def test_mcp_bootstrap_excludes_workspace_and_pythonpath_imports(self):
        with BudgetChannel(self.root, ExecutionBudget(100), RequestBudget(80)) as channel:
            for name in ('argparse.py', 'json.py'):
                (self.root / name).write_text('raise RuntimeError("untrusted workspace import")\n')
            command = native.argv('fake', self.root, Config(), parallel=True, budget_channel=channel)
            overrides = dict(command[i+1].split('=', 1) for i, value in enumerate(command) if value == '-c')
            arguments = json.loads(overrides['mcp_servers.flow_budget.args'])
            request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                       'params': {'name': 'status', 'arguments': {}}}
            process = subprocess.run([sys.executable, *arguments], cwd=self.root,
                                     env={**os.environ, 'PYTHONPATH': str(self.root)},
                                     input=json.dumps(request)+'\n', text=True,
                                     capture_output=True, timeout=10)
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(process.stdout)['result']
            self.assertEqual(json.loads(result['content'][0]['text'])['status'], 'ok')

    def test_server_imports_prelaunch_snapshot_after_editable_source_changes(self):
        from importlib.resources import files
        editable = self.root / 'editable-package'
        editable.mkdir()
        for name in ('__init__.py', 'budget.py', 'contracts.py', 'budget_stdio.py'):
            (editable/name).write_bytes(files('codex_flow').joinpath(name).read_bytes())
        with patch('importlib.resources.files', return_value=editable):
            channel = BudgetChannel(self.root, ExecutionBudget(100), RequestBudget(80))
        for original in editable.iterdir():
            original.write_text('raise RuntimeError("edited application source executed on host")\n')
        channel.publish()
        command = native.argv('fake', self.root, Config(), parallel=True, budget_channel=channel)
        overrides = dict(command[i+1].split('=', 1) for i, value in enumerate(command) if value == '-c')
        arguments = json.loads(overrides['mcp_servers.flow_budget.args'])
        self.assertIn(repr(str(channel.runtime_root)), arguments[3])
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                   'params': {'name': 'status', 'arguments': {}}}
        process = subprocess.run([sys.executable, *arguments], cwd=self.root,
                                 input=json.dumps(request)+'\n', text=True,
                                 capture_output=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(json.loads(process.stdout)['result']['content'][0]['text'])['status'], 'ok')

    def test_snapshot_failure_does_not_fall_back_to_source(self):
        with patch('importlib.resources.files', side_effect=OSError):
            with self.assertRaises(OSError):
                BudgetChannel(self.root, ExecutionBudget(100), RequestBudget(80))


if __name__ == '__main__':
    unittest.main()
