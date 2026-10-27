"""Post-verification cancellation/deadline regression; no model or checker execution."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from codex_flow import acceptance, cli, execution_contract as execution


class CompletionTests(unittest.TestCase):
    def test_post_gate_observation_cannot_promote_after_cancel_or_deadline(self):
        example = ROOT / 'examples/execution-contract'
        for stop in ('deadline', 'cancel'):
            with self.subTest(stop=stop), tempfile.TemporaryDirectory(prefix='flow-contract-completion-') as temporary:
                workspace = Path(temporary).resolve()
                for name in ('execution.json', 'acceptance.json', 'verifier.py'):
                    (workspace / name).write_bytes((example / name).read_bytes())
                budget = Mock()
                budget.remaining_s.return_value = 100
                budget.snapshot.return_value = {}
                active = {}
                def native_run(*args, **kwargs):
                    run_dir = Path(args[4])
                    run_dir.mkdir(parents=True)
                    active['dir'] = run_dir
                    return {'run_id': run_dir.name, 'status': 'completed_unverified', 'wall_clock_s': .01,
                            'input_tokens': None, 'output_tokens': None, 'cached_tokens': None}
                def observation(*args, **kwargs):
                    active['observations'] = active.get('observations', 0) + 1
                    if active['observations'] == 2:
                        if stop == 'deadline':
                            budget.remaining_s.return_value = 0
                        else:
                            (active['dir'] / 'cancel.request').touch()
                    return {'verified': True, 'status': 'observed', 'artifact_sha256': {'app.py': 'a' * 64}}
                output = io.StringIO()
                with patch('codex_flow.budget.ExecutionBudget', return_value=budget), \
                     patch('codex_flow.native.executable', return_value='codex'), \
                     patch('codex_flow.native.run', side_effect=native_run), \
                     patch.object(acceptance, 'require_backend'), \
                     patch.object(acceptance, 'verify', return_value={'status': 'passed', 'accepted': True}), \
                     patch.object(execution, 'observe', side_effect=observation), redirect_stdout(output):
                    code = cli.main(['--repo', str(workspace), 'run', 'task', '--enable',
                                     '--execution-contract', str(workspace / 'execution.json'),
                                     '--acceptance-file', str(workspace / 'acceptance.json')])
                result = json.loads(output.getvalue())
                self.assertEqual(code, 3)
                self.assertFalse(result['accepted'])
                self.assertEqual(result['native_status'], 'completed_unverified')
                self.assertEqual(result['status'], 'cancelled' if stop == 'cancel' else 'timed_out')
                self.assertEqual(result['acceptance']['status'], 'passed')
                self.assertEqual(result, json.loads((active['dir'] / 'metrics.json').read_text()))

    def test_windows_aliases_cannot_supply_a_fake_distinct_handoff(self):
        with tempfile.TemporaryDirectory(prefix='flow-contract-alias-') as temporary:
            workspace = Path(temporary).resolve()
            data = json.loads((ROOT / 'examples/execution-contract/execution.json').read_bytes())
            for name in ('core.py.', 'core.py ', '.CoDeX-FlOw/state'):
                data['handoff_artifact'] = name
                path = workspace / 'execution.json'
                path.write_text(json.dumps(data), encoding='utf-8')
                with self.subTest(name=name), self.assertRaises(ValueError):
                    execution.load(path, workspace)


if __name__ == '__main__':
    unittest.main()
