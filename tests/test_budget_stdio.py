"""Offline MCP stdio protocol, freshness, privacy and fixed-path boundaries."""
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from codex_flow.budget import ExecutionBudget
from codex_flow.budget_stdio import BudgetStdio, main
from codex_flow.contracts import PolicyError


class BudgetStdioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='flow-budget-stdio-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'workspace'
        self.private = self.root / '.codex-flow'
        self.audit = self.private / 'mcp-audit'
        self.audit.mkdir(parents=True)
        self.path = self.private / 'budget.json'
        self.now = datetime(2026, 10, 24, 0, 0, tzinfo=timezone.utc).timestamp()
        self.budget = ExecutionBudget(100, 10, clock=lambda: 0).snapshot(2)
        self.publish()
        self.server = BudgetStdio(self.root, self.path, self.audit, clock=lambda: self.now)

    def publish(self, *, age=0, budget=None, extra=None):
        data = {'schema': 1, 'observed_utc': datetime.fromtimestamp(self.now - age, timezone.utc).isoformat(),
                'budget': self.budget if budget is None else budget}
        data.update(extra or {})
        self.path.write_text(json.dumps(data), encoding='utf-8')

    def rpc(self, method='tools/call', params=None, identity=1):
        if params is None:
            params = {'name': 'status', 'arguments': {}} if method == 'tools/call' else {}
        return self.server.handle({'jsonrpc': '2.0', 'id': identity, 'method': method, 'params': params})

    def result(self):
        reply = self.rpc()
        result = reply['result']
        return json.loads(result['content'][0]['text']), result['isError']

    def link(self, source, target, *, directory=False):
        try:
            source.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest('Symlink creation unavailable on this runner')

    def test_status_is_readonly_fresh_and_audits_only_metadata(self):
        reply = self.rpc(identity='DO_NOT_LOG_PRIVATE_REQUEST_ID')
        result = json.loads(reply['result']['content'][0]['text'])
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['budget'], self.budget)
        self.assertEqual(result['sample_age_s'], 0.)
        self.assertFalse(reply['result']['isError'])
        for text in ('existing ownership and permissions', 'Read-only workers return evidence or requested proposal text',
                     'never write files or delegate',
                     'never proves acceptance', 'Do not skip required tests'):
            self.assertIn(text, result['guidance'])
        logs = list(self.audit.glob('*.jsonl'))
        self.assertEqual(len(logs), 1)
        record = json.loads(logs[0].read_text(encoding='utf-8'))
        self.assertEqual(set(record), {'timestamp', 'result', 'phase', 'requests_used'})
        self.assertEqual((record['result'], record['phase'], record['requests_used']), ('ok', 'build', 2))
        self.assertNotIn('DO_NOT_LOG_PRIVATE_REQUEST_ID', logs[0].read_text(encoding='utf-8'))
        self.assertNotIn(str(self.root), logs[0].read_text(encoding='utf-8'))

    def test_each_server_uses_exclusive_uuid_audit_and_multiple_calls_append(self):
        self.result()
        self.result()
        other = BudgetStdio(self.root, self.path, self.audit, clock=lambda: self.now)
        other.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'status', 'arguments': {}}})
        logs = list(self.audit.glob('*.jsonl'))
        self.assertEqual(len(logs), 2)
        self.assertEqual(sorted(len(p.read_text(encoding='utf-8').splitlines()) for p in logs), [1, 2])
        self.assertTrue(all(len(line) < 512 for p in logs for line in p.read_text(encoding='utf-8').splitlines()))

    def test_missing_status_is_unavailable_with_null_budget_and_audited(self):
        self.path.unlink()
        result, is_error = self.result()
        self.assertTrue(is_error)
        self.assertEqual(result, {'status': 'unavailable', 'reason': 'status_missing', 'budget': None})
        record = json.loads(next(self.audit.glob('*.jsonl')).read_text(encoding='utf-8'))
        self.assertIsNone(record['phase'])
        self.assertIsNone(record['requests_used'])

    def test_age_boundaries_and_small_future_tolerance(self):
        self.publish(age=10)
        self.assertEqual(self.result()[0]['status'], 'ok')
        self.publish(age=10.001)
        self.assertEqual(self.result()[0]['reason'], 'status_stale')
        self.publish(age=-.75)
        result, _ = self.result()
        self.assertEqual((result['status'], result['sample_age_s']), ('ok', 0.))
        self.publish(age=-1.01)
        self.assertEqual(self.result()[0]['reason'], 'status_future')

    def test_invalid_status_schemas_timestamps_and_extra_budget_values_never_leak(self):
        for value in [None, [], {'schema': True},
                      {'schema': 1, 'observed_utc': '2026-10-24T00:00:00', 'budget': self.budget},
                      {'schema': 1, 'observed_utc': '2026-99-24T00:00:00Z', 'budget': self.budget},
                      {'schema': 1, 'observed_utc': '2026-10-24T00:00:00Z',
                       'budget': dict(self.budget, secret='DO_NOT_LEAK_PRIVATE_VALUE')}]:
            with self.subTest(value=value):
                self.path.write_text(json.dumps(value), encoding='utf-8')
                result, error = self.result()
                self.assertTrue(error)
                self.assertEqual(result['reason'], 'status_invalid')
                self.assertIsNone(result['budget'])
                self.assertNotIn('DO_NOT_LEAK_PRIVATE_VALUE', json.dumps(result))
        self.publish(extra={'prompt': 'DO_NOT_LEAK_PRIVATE_VALUE'})
        self.assertEqual(self.result()[0]['reason'], 'status_invalid')

    def test_malformed_oversized_and_nonfinite_status_are_fixed_errors(self):
        for raw in [b'not JSON', b'\xff', b'{}' + b' ' * 16383,
                    json.dumps({'schema': 1, 'observed_utc': '2026-10-24T00:00:00Z',
                                'budget': dict(self.budget, remaining_s=float('nan'))}).encode()]:
            self.path.write_bytes(raw)
            result, _ = self.result()
            self.assertIn(result['reason'], ('status_invalid', 'status_oversize'))
            self.assertIsNone(result['budget'])

    def test_measured_exhausted_budget_zero_remains_known(self):
        clock = [0.]
        budget = ExecutionBudget(1, 1, clock=lambda: clock[0])
        clock[0] = 2.
        self.publish(budget=budget.snapshot(1))
        result, error = self.result()
        self.assertFalse(error)
        self.assertEqual(result['budget']['remaining_s'], 0.)
        self.assertEqual(result['budget']['phase'], 'finalize')

    def test_outside_relative_and_uncreated_audit_paths_rejected_without_writes(self):
        outside = self.root.parent / 'outside.json'
        for status, audit in [(outside, self.audit), (self.path, self.root.parent),
                              (Path('relative.json'), self.audit), (self.path, self.audit / 'missing')]:
            with self.subTest(status=status, audit=audit), self.assertRaises(PolicyError):
                BudgetStdio(self.root, status, audit)
        self.assertFalse(outside.exists())
        self.assertFalse((self.audit / 'missing').exists())

    def test_status_symlink_rejected_before_outside_read(self):
        outside = self.root.parent / 'outside.json'
        outside.write_text(self.path.read_text(encoding='utf-8'), encoding='utf-8')
        self.path.unlink()
        self.link(self.path, outside)
        result, error = self.result()
        self.assertTrue(error)
        self.assertEqual(result['reason'], 'status_path_rejected')
        self.assertIsNone(result['budget'])
        with self.assertRaises(PolicyError):
            BudgetStdio(self.root, self.path, self.audit)

    def test_audit_file_symlink_rejected_before_outside_append(self):
        outside = self.root.parent / 'outside-audit.txt'
        outside.write_text('Preserve outside marker\n', encoding='utf-8')
        self.link(self.server.audit_file, outside)
        result, error = self.result()
        self.assertTrue(error)
        self.assertEqual(result, {'status': 'unavailable', 'reason': 'audit_unavailable', 'budget': None})
        self.assertEqual(outside.read_text(encoding='utf-8'), 'Preserve outside marker\n')

    def test_audit_directory_replacement_link_is_rejected(self):
        outside = self.root.parent / 'outside-audit'
        outside.mkdir()
        self.audit.rename(self.private / 'original-audit')
        self.link(self.audit, outside, directory=True)
        self.assertEqual(self.result()[0]['reason'], 'audit_unavailable')
        self.assertEqual(list(outside.iterdir()), [])

    def test_hardlinked_status_is_rejected(self):
        outside = self.root.parent / 'outside-hardlink.json'
        outside.write_bytes(self.path.read_bytes())
        self.path.unlink()
        try:
            os.link(outside, self.path)
        except OSError:
            self.skipTest('Hardlinks unavailable on this runner')
        self.assertEqual(self.result()[0]['reason'], 'status_path_rejected')

    def test_initialize_echoes_valid_ascii_date_and_exposes_one_readonly_tool(self):
        reply = self.rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'fixture', 'version': '1'}})
        self.assertEqual(reply['result']['protocolVersion'], '2025-06-18')
        tools = self.rpc('tools/list')['result']['tools']
        self.assertEqual(self.rpc('tools/list', {'cursor': None})['result']['tools'], tools)
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]['name'], 'status')
        self.assertEqual(tools[0]['inputSchema'], {'type': 'object', 'properties': {}, 'additionalProperties': False})
        self.assertEqual(tools[0]['annotations'], {'readOnlyHint': True, 'destructiveHint': False,
                                                 'idempotentHint': True, 'openWorldHint': False})
        self.assertEqual(list(self.audit.iterdir()), [])

    def test_invalid_protocol_dates_and_model_arguments_are_rejected_without_audit(self):
        for version in ['2025-02-30', '２０２５-06-18', '2025-06-18-extra', 7, None]:
            self.assertEqual(self.rpc('initialize', {'protocolVersion': version})['error']['code'], -32602)
        self.assertEqual(self.rpc('initialize', {'protocolVersion': '2025-06-18', 'path': 'DO_NOT_READ'})['error']['code'], -32602)
        for params in [{'name': 'status', 'arguments': {'path': 'DO_NOT_READ'}},
                       {'name': 'status', 'arguments': {'command': 'DO_NOT_EXECUTE'}},
                       {'name': 'other', 'arguments': {}}, {'name': 'status'},
                       {'name': 'status', 'arguments': None},
                       {'name': 'status', 'arguments': {}, 'path': 'DO_NOT_READ'}]:
            self.assertEqual(self.rpc(params=params)['error']['code'], -32602)
        self.assertEqual(list(self.audit.iterdir()), [])

    def test_ping_unknown_methods_notifications_and_invalid_envelope(self):
        self.assertEqual(self.rpc('ping')['result'], {})
        self.assertEqual(self.rpc('unknown')['error']['code'], -32601)
        self.assertIsNone(self.server.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'}))
        self.assertIsNone(self.server.handle({'jsonrpc': '2.0', 'method': 'tools/call', 'params': {'name': 'status', 'arguments': {}}}))
        self.assertEqual(self.server.handle([])['error']['code'], -32600)
        self.assertEqual(list(self.audit.iterdir()), [])

    def test_stdio_parse_errors_are_fixed_and_oversized_frame_stops_processing(self):
        output = io.StringIO()
        self.server.serve(io.StringIO('DO_NOT_ECHO_PRIVATE_BODY\n' + json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'ping'}) + '\n'), output)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(responses[0], {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}})
        self.assertEqual(responses[1]['result'], {})
        self.assertNotIn('DO_NOT_ECHO_PRIVATE_BODY', output.getvalue())
        output = io.StringIO()
        self.server.serve(io.StringIO('x' * 65537 + '\n{"jsonrpc":"2.0","id":3,"method":"ping"}\n'), output)
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertEqual(json.loads(output.getvalue())['error']['code'], -32700)

    def test_main_eof_stdout_is_only_rpc_and_invalid_paths_fail_silently(self):
        output = io.StringIO()
        code = main(['--root', str(self.root), '--status-file', str(self.path), '--audit-dir', str(self.audit)],
                    stdin=io.StringIO('{"jsonrpc":"2.0","id":1,"method":"ping"}\n'), stdout=output)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['result'], {})
        output = io.StringIO()
        self.assertEqual(main(['--root', str(self.root), '--status-file', str(self.root.parent / 'outside'),
                               '--audit-dir', str(self.audit)], stdin=io.StringIO(), stdout=output), 2)
        self.assertEqual(output.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
