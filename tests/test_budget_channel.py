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


if __name__ == '__main__':
    unittest.main()
