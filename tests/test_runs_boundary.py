"""Run-record CLI boundaries using only synthetic owned temporary fixtures."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from codex_flow import cli, native


class RunsBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='flow-runs-boundary-')
        self.addCleanup(self.tmp.cleanup)
        self.fixture = Path(self.tmp.name).resolve()
        self.repo = self.fixture / 'workspace'
        self.repo.mkdir()
        self.runs = self.repo / '.codex-flow/runs'
        self.runs.mkdir(parents=True)
        self.outside = self.fixture / 'outside-record.json'
        self.outside.write_text(json.dumps({'owned_marker': 'outside-fixture-marker'}), encoding='utf-8')

    def link(self, path, target, directory=False):
        try:path.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError):self.skipTest('Symlink creation unavailable on this runner')

    def invoke(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(native, 'executable', side_effect=AssertionError('native calls forbidden')), \
             redirect_stdout(out), redirect_stderr(err):
            status = cli.main(['--repo', str(self.repo), 'runs', *arguments])
        return status, out.getvalue(), err.getvalue()

    def refused(self, *arguments):
        status, out, err = self.invoke(*arguments)
        self.assertEqual(status, 2)
        self.assertEqual(out, '')
        self.assertIn('run record boundary refused', err)
        self.assertNotIn('outside-fixture-marker', err)

    def folder(self, name='record'):
        folder = self.runs / name
        folder.mkdir()
        return folder

    def test_show_rejects_individual_metrics_symlink_before_read(self):
        self.link(self.folder() / 'metrics.json', self.outside)
        before = self.outside.read_bytes()
        self.refused('show', 'record')
        self.assertEqual(self.outside.read_bytes(), before)

    def test_show_rejects_individual_control_symlink_before_read(self):
        self.link(self.folder() / 'control.json', self.outside)
        self.refused('show', 'record')

    def test_list_rejects_individual_metrics_symlink_before_read(self):
        self.link(self.folder() / 'metrics.json', self.outside)
        self.refused('list')

    def test_replay_rejects_individual_events_symlink_before_read(self):
        events = self.fixture / 'outside-events.jsonl'
        events.write_text(json.dumps({'event_type': 'outside-fixture-marker'}) + '\n', encoding='utf-8')
        self.link(self.folder() / 'events.jsonl', events)
        before = events.read_bytes()
        self.refused('replay', 'record')
        self.assertEqual(events.read_bytes(), before)

    def test_cancel_rejects_linked_run_folder_before_creating_outside_marker(self):
        outside = self.fixture / 'outside-run'
        outside.mkdir()
        self.link(self.runs / 'record', outside, directory=True)
        self.refused('cancel', 'record')
        self.assertFalse((outside / 'cancel.request').exists())

    def test_cancel_rejects_dangling_individual_link_without_creating_target(self):
        outside = self.fixture / 'outside-created'
        self.link(self.folder() / 'cancel.request', outside)
        self.refused('cancel', 'record')
        self.assertFalse(outside.exists())

    def test_dangling_metrics_link_is_not_treated_as_absent(self):
        folder = self.folder()
        self.link(folder / 'metrics.json', self.fixture / 'absent-outside')
        (folder / 'control.json').write_text('{"status":"running"}', encoding='utf-8')
        self.refused('show', 'record')

    def test_runs_root_link_rejected_before_glob(self):
        self.runs.rmdir()
        outside = self.fixture / 'outside-runs'
        outside.mkdir()
        self.link(self.runs, outside, directory=True)
        with patch.object(Path, 'glob', side_effect=AssertionError('glob before boundary validation')):
            self.refused('list')
        self.assertEqual(list(outside.iterdir()), [])

    def test_codex_flow_parent_link_rejected_before_glob(self):
        self.runs.rmdir()
        self.runs.parent.rmdir()
        outside = self.fixture / 'outside-flow'
        outside.mkdir()
        self.link(self.repo / '.codex-flow', outside, directory=True)
        with patch.object(Path, 'glob', side_effect=AssertionError('glob before boundary validation')):
            self.refused('list')
        self.assertEqual(list(outside.iterdir()), [])

    def test_normal_utf8_record_show_list_replay_and_cancel_are_preserved(self):
        folder = self.folder()
        record = {'status': 'completed_unverified', 'label': 'Проверка'}
        (folder / 'metrics.json').write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
        (folder / 'events.jsonl').write_text(json.dumps({'event_type': 'synthetic.event'}) + '\n', encoding='utf-8')
        status, out, _ = self.invoke('show', 'record')
        self.assertEqual((status, json.loads(out)), (0, record))
        status, out, _ = self.invoke('list')
        self.assertEqual((status, json.loads(out)), (0, [{'run_id': 'record', **record}]))
        status, out, _ = self.invoke('replay', 'record')
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out)['events'], {'synthetic.event': 1})
        status, out, _ = self.invoke('cancel', 'record')
        self.assertEqual((status, json.loads(out)), (0, {'cancel_requested': True}))
        self.assertTrue((folder / 'cancel.request').is_file())

    def test_control_fallback_show_retains_trace_and_missing_list_is_empty(self):
        status, out, _ = self.invoke('list')
        self.assertEqual((status, json.loads(out)), (0, []))
        folder = self.folder()
        (folder / 'control.json').write_text('{"status":"running"}', encoding='utf-8')
        (folder / 'events.jsonl').write_text(json.dumps({'event_type': 'synthetic.start'}) + '\n', encoding='utf-8')
        status, out, _ = self.invoke('show', 'record')
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out)['trace']['events'], {'synthetic.start': 1})


if __name__ == '__main__': unittest.main()
