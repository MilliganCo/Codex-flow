"""No task-time calibration or stale instruction promotion; no models or network."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from codex_flow import cli, native, benchmark
from codex_flow.config import Config
from codex_flow.contracts import PolicyError
from codex_flow.harness import runtime_guard


class RuntimeGuardTests(unittest.TestCase):
    def test_enabled_guard_has_no_io_or_model_side_effects(self):
        with patch('pathlib.Path.read_text') as read, patch('subprocess.Popen') as process:
            result = runtime_guard()
        read.assert_not_called()
        process.assert_not_called()
        self.assertEqual(result['status'], 'deferred')
        self.assertEqual(result['inspired_probes'], 0)
        self.assertFalse(result['decision']['adopted'])
        self.assertEqual(result['runs'], [])

    def test_run_with_guard_ignores_old_overlay_and_starts_only_primary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            active = root / '.codex-flow/lessons/active.txt'
            active.parent.mkdir(parents=True)
            active.write_text('UNVALIDATED OLD COVERAGE OVERLAY')
            def fake_run(exe, repo, cfg, prompt, output, **kwargs):
                self.assertEqual(kwargs['instructions'], cli.FLOW_INSTRUCTIONS)
                self.assertTrue(kwargs['parallel'])
                self.assertLessEqual(cfg.timeout_s, 1500)
                return {'run_id': 'fixture', 'status': 'completed_unverified',
                        'wall_clock_s': .01, 'input_tokens': 1, 'output_tokens': 1, 'cached_tokens': 0}
            with patch.object(cli, 'load', return_value=Config(enabled=True, harness2=True)), \
                 patch.object(native, 'executable', return_value='fake'), \
                 patch.object(native, 'run', side_effect=fake_run) as run, \
                 patch.object(benchmark, 'probe') as probe, contextlib.redirect_stdout(io.StringIO()) as output:
                code = cli.main(['--repo', str(root), 'run', 'Synthetic task', '--independent-steps', '3', '--timeout', '1500'])
            self.assertEqual(code, 0)
            self.assertEqual(run.call_count, 1)
            probe.assert_not_called()
            self.assertEqual(active.read_text(), 'UNVALIDATED OLD COVERAGE OVERLAY')
            self.assertEqual(json.loads(output.getvalue())['harness2']['status'], 'deferred')

    def test_invalid_groups_fail_before_auth_or_workspace_creation(self):
        with patch.object(benchmark, 'executable') as exe:
            for groups in ('A', 'BA', 'ABC', '', None):
                with self.subTest(groups=groups), self.assertRaises(PolicyError):
                    benchmark.execute(Path('missing'), Path('task'), Path('eval'), groups=groups)
        exe.assert_not_called()


if __name__ == '__main__': unittest.main()
