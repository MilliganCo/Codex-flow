"""CLI admission order with mocked providers/native execution; no model calls."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from codex_flow import cli, native


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='flow-cli-admission-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        folder = self.root / '.codex-flow'
        folder.mkdir()
        (folder / 'config.json').write_text(json.dumps({'enabled': True, 'mercury': True}), encoding='utf-8')
        self.bridge = Mock()
        self.bridge.decide.return_value = {'status': 'OBSERVED', 'route': 'parallel', 'confidence': .9, 'successful_calls': 1}

    def invoke(self, *flags):
        out, err = io.StringIO(), io.StringIO()
        def fake_run(*args, **kwargs):
            return {'run_id': 'synthetic-run', 'wall_clock_s': .01, 'status': 'completed_unverified',
                    'input_tokens': None, 'output_tokens': None, 'cached_tokens': None}
        with patch('codex_flow.mercury.MercuryBridge', return_value=self.bridge) as factory, \
             patch.object(native, 'executable', return_value='fake-codex') as executable, \
             patch.object(native, 'run', side_effect=fake_run) as run, \
             patch.object(cli, 'write_json'), redirect_stdout(out), redirect_stderr(err):
            code = cli.main(['--repo', str(self.root), 'run', 'Synthetic task; no paths or secrets.', *flags])
        return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue(), factory, executable, run

    def test_escalated_risks_stop_before_mercury_or_native_even_with_single_flag(self):
        for risk in ('medium', 'high', 'critical'):
            with self.subTest(risk=risk):
                code, _, error, factory, executable, run = self.invoke('--independent-steps', '3', '--risk-level', risk, '--single-agent')
                self.assertEqual(code, 2)
                self.assertIn('risk requires', error)
                factory.assert_not_called()
                executable.assert_not_called()
                run.assert_not_called()
        self.bridge.decide.assert_not_called()

    def test_forced_single_and_ownership_conflict_suppress_mercury(self):
        for flags in (('--single-agent',), ('--strategy', 'single'), ('--conflicting-paths',)):
            with self.subTest(flags=flags):
                code, output, _, factory, _, run = self.invoke('--independent-steps', '3', *flags)
                self.assertEqual(code, 0)
                self.assertEqual(output['route']['strategy'], 'single')
                factory.assert_not_called()
                self.assertFalse(run.call_args.kwargs['parallel'])
        self.bridge.decide.assert_not_called()

    def test_explicit_parallel_strategy_keeps_independence_gate(self):
        code, output, _, factory, _, run = self.invoke('--strategy', 'parallel')
        self.assertEqual(code, 0)
        self.assertEqual(output['route']['strategy'], 'single')
        self.assertFalse(run.call_args.kwargs['parallel'])
        factory.assert_not_called()

    def test_dry_run_has_zero_mercury_and_execution_calls(self):
        for flags, strategy in (((), 'parallel'), (('--risk-level', 'high'), 'escalate'),
                                (('--conflicting-paths',), 'single')):
            with self.subTest(flags=flags):
                code, output, _, factory, executable, run = self.invoke('--dry-run', '--independent-steps', '3', *flags)
                self.assertEqual(code, 0)
                self.assertEqual(output['external_calls'], 0)
                self.assertEqual(output['route']['strategy'], strategy)
                factory.assert_not_called()
                executable.assert_not_called()
                run.assert_not_called()

    def test_parallel_candidate_sends_only_bounded_state_with_valid_risk_enum(self):
        code, output, _, factory, _, run = self.invoke('--independent-steps', '999')
        self.assertEqual(code, 0)
        factory.assert_called_once()
        self.bridge.decide.assert_called_once_with({'complexity': 'high', 'independent_steps': 100,
                                                   'conflicting_paths': False, 'risk_level': 'low'}, enabled=True)
        self.assertEqual(output['route']['source'], 'mercury')
        self.assertTrue(run.call_args.kwargs['parallel'])

    def test_declared_low_risk_is_preserved(self):
        code, _, _, _, _, _ = self.invoke('--independent-steps', '3', '--risk-level', 'low')
        self.assertEqual(code, 0)
        self.assertEqual(self.bridge.decide.call_args.args[0]['risk_level'], 'low')

    def test_no_mercury_flag_and_unavailable_provider_keep_rules_fallback(self):
        code, output, _, factory, _, _ = self.invoke('--independent-steps', '3', '--no-mercury')
        self.assertEqual(code, 0)
        self.assertEqual(output['route']['source'], 'rules')
        factory.assert_not_called()
        self.bridge.decide.return_value = {'status': 'UNAVAILABLE', 'route': 'rules', 'reason': 'offline'}
        code, output, _, _, _, _ = self.invoke('--independent-steps', '3')
        self.assertEqual(code, 0)
        self.assertEqual(output['route']['source'], 'rules')
        self.assertEqual(output['route']['fallback_reason'], 'offline')


if __name__ == '__main__': unittest.main()
