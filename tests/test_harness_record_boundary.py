"""Exact rollback-record boundary regressions using owned temporary fixtures."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from codex_flow.contracts import PolicyError
from codex_flow.harness import GuardedHarness, HarnessProposal, EvaluationResult


class RollbackRecordBoundaryTests(unittest.TestCase):
    def test_individual_record_symlink_rejected_before_read_with_files_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='flow-record-boundary-') as temporary:
            fixture = Path(temporary).resolve()
            workspace = fixture / 'workspace'
            workspace.mkdir()
            harness = GuardedHarness(workspace)
            harness.store.mkdir(parents=True)
            active = harness.store / 'active.txt'
            active.write_text('Owned active instructions', encoding='utf-8')
            outside = fixture / 'outside-record.json'
            outside.write_text(json.dumps({'adopted': True,
                'adopted_sha256': hashlib.sha256(active.read_bytes()).hexdigest(),
                'previous': 'Untrusted replacement instructions'}), encoding='utf-8')
            record = harness.store / 'proposal-candidate.json'
            try:
                record.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest('Symlink creation unavailable on this runner')
            previous_outside, previous_active = outside.read_bytes(), active.read_bytes()
            original = Path.read_text
            def guarded_read(path, *args, **kwargs):
                if path in (record, outside):
                    self.fail('Rollback attempted to read a linked record before validating its boundary')
                return original(path, *args, **kwargs)
            with patch.object(Path, 'read_text', autospec=True, side_effect=guarded_read):
                with self.assertRaises(PolicyError):
                    harness.rollback('candidate')
            self.assertEqual(outside.read_bytes(), previous_outside)
            self.assertEqual(active.read_bytes(), previous_active)

    def test_regular_utf8_record_restores_exact_unicode_instructions(self):
        with tempfile.TemporaryDirectory(prefix='flow-record-utf8-') as temporary:
            workspace = Path(temporary).resolve()
            harness = GuardedHarness(workspace)
            harness.store.mkdir(parents=True)
            active = harness.store / 'active.txt'
            original = 'Исходные инструкции: точность и проверка.'
            active.write_text(original, encoding='utf-8')
            proposal = HarnessProposal('candidate', 'Новые инструкции.', 'Measured fixture improvement')
            harness.compare(proposal, EvaluationResult(1, 2, True, True, 'baseline'),
                            EvaluationResult(2, 1, True, True, 'candidate'), adopt=True)
            self.assertTrue(harness.rollback('candidate')['rolled_back'])
            self.assertEqual(active.read_text(encoding='utf-8'), original)


if __name__ == '__main__': unittest.main()
