"""Read-only inspection of durable state; no model or checker execution."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from codex_flow import cli, workflow, workflow_display
from codex_flow.config import Config
from codex_flow.workflow_store import Store, WorkflowError
from test_workflow import FixtureBackend


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='flow-navigation-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve() / 'project # & space'
        self.repo.mkdir()
        self.root = self.repo / '.codex-flow/workflows'

    def store(self):
        return Store(self.root)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                for p in self.root.rglob('*') if p.is_file()}

    def invoke(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(['--repo', str(self.repo), 'workflow', *args])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_empty_list_never_initializes_state_or_native(self):
        with patch('codex_flow.native.executable') as native, patch.object(Store, '__init__') as init:
            code, out, _ = self.invoke('list', '--json')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['workflows'], [])
        self.assertFalse((self.repo / '.codex-flow').exists())
        native.assert_not_called()
        init.assert_not_called()

    def test_newest_created_order_limit_and_filter_are_explicit(self):
        store = self.store()
        ids = [store.create({}) for _ in range(3)]
        with store._transaction() as db:
            db.execute("UPDATE workflows SET state='paused' WHERE id=?", (ids[0],))
        reader = Store(self.root, read_only=True)
        before = self.snapshot()
        value = reader.list_workflows(limit=2)
        self.assertEqual([row['id'] for row in value['workflows']], ids[:0:-1])
        self.assertTrue(value['has_more'])
        self.assertTrue(all(row['integrity'] == 'not_checked' and 'accepted' not in row for row in value['workflows']))
        filtered = reader.list_workflows(state='paused')
        self.assertEqual([row['id'] for row in filtered['workflows']], ids[:1])
        self.assertFalse(filtered['has_more'])
        self.assertEqual(before, self.snapshot())

    def test_read_only_store_rejects_writes_before_creating_attempt_directories(self):
        self.store().create({})
        reader = Store(self.root, read_only=True)
        before = sorted(self.root.rglob('*')), self.snapshot()
        with self.assertRaisesRegex(WorkflowError, 'read-only'):
            reader.create({})
        self.assertEqual(before, (sorted(self.root.rglob('*')), self.snapshot()))

    def test_readers_work_during_reserved_writer_and_never_recover_owner(self):
        store = self.store()
        identity = store.create({})
        owner = store.acquire(identity)
        with store._transaction() as db:
            db.execute('UPDATE workflows SET requests_used=1 WHERE id=?', (identity,))
            reader = Store(self.root, read_only=True)
            self.assertEqual(reader.list_workflows()['workflows'][0]['requests_used'], 0)
            self.assertIsNotNone(reader.get(identity)['owner_pid'])
        self.assertEqual(store.get(identity)['requests_used'], 1)
        store.release(owner, 'paused')

    def test_cli_list_ignores_bad_current_config_and_omits_specs(self):
        identity = self.store().create({'private_context': 'DO_NOT_PRINT_TASK'})
        (self.repo / '.codex-flow/config.json').write_text('{broken', encoding='utf-8')
        before = self.snapshot()
        code, out, _ = self.invoke('list', '--json')
        self.assertEqual(code, 0)
        self.assertIn(identity, out)
        self.assertNotIn('DO_NOT_PRINT_TASK', out)
        self.assertEqual(before, self.snapshot())
        code, out, _ = self.invoke('list', '--lang', 'en')
        self.assertEqual(code, 0)
        self.assertIn('Integrity is not checked', out)

    def test_invalid_limit_fails_without_writes(self):
        for limit in ('0', '101', '-1'):
            with self.subTest(limit=limit):
                code, _, _ = self.invoke('list', '--limit', limit)
                self.assertEqual(code, 2)
        self.assertFalse(self.root.exists())

    def test_store_rejects_bad_bounds_and_state(self):
        reader = self.store()
        for opts in ({'limit': True}, {'limit': 101}, {'state': "paused' OR 1=1"}):
            with self.subTest(opts=opts), self.assertRaises(WorkflowError):
                reader.list_workflows(**opts)

    def test_damaged_database_fails_without_repair(self):
        store = self.store()
        store.path.write_bytes(b'corrupt')
        before = self.snapshot()
        code, _, error = self.invoke('list', '--json')
        self.assertEqual(code, 2)
        self.assertIn('database format', error)
        self.assertEqual(before, self.snapshot())

    def test_missing_schema_is_not_automatically_migrated(self):
        store = self.store()
        with sqlite3.connect(store.path) as db:
            db.execute('DROP TABLE workflows')
        db.close()
        before = self.snapshot()
        code, _, error = self.invoke('list', '--json')
        self.assertEqual(code, 2)
        self.assertIn('SQLITE_ERROR', error)
        self.assertEqual(before, self.snapshot())

    def test_wal_database_is_refused_without_creating_sidecars(self):
        store = self.store()
        db = sqlite3.connect(store.path)
        db.execute('PRAGMA journal_mode=WAL')
        db.close()
        before = self.snapshot()
        code, _, _ = self.invoke('list')
        self.assertEqual(code, 2)
        self.assertEqual(before, self.snapshot())

    def test_hardlinked_database_is_refused(self):
        store = self.store()
        alias = self.repo / 'alias.sqlite'
        try:
            alias.hardlink_to(store.path)
        except OSError:
            self.skipTest('hardlinks unavailable')
        code, _, error = self.invoke('list')
        self.assertEqual(code, 2)
        self.assertIn('one link', error)

    def test_status_is_read_only_and_rechecks_completed_artifacts(self):
        subprocess.run(['git', '-c', 'init.templateDir=' + str(self.repo / 'empty'), 'init', '--quiet', str(self.repo)],
                       capture_output=True, check=True)
        (self.repo / 'app.txt').write_text('original', encoding='utf-8')
        contract = self.repo / 'acceptance.json'
        contract.write_text(json.dumps({'schema': 1, 'checker': 'checker.py', 'inputs': ['app.txt'],
                                        'min_checks': 1, 'timeout_s': 10}), encoding='utf-8')
        (self.repo / 'checker.py').write_text('INERT DATA; NEVER EXECUTE', encoding='utf-8')
        engine = workflow.Engine(self.repo, backend=FixtureBackend())
        done = engine.start(Config(), 'fixture task', contract, enable=True)
        self.assertTrue(done['accepted'])
        before = self.snapshot()
        with patch.object(workflow.Engine, 'store', side_effect=AssertionError('writer store must not be used')):
            checked = workflow.Engine(self.repo).status(done['workflow_id'])
        self.assertTrue(checked['accepted'])
        self.assertEqual(before, self.snapshot())
        bundle = self.root / done['workflow_id'] / done['report']['bundle']
        (bundle / 'files/app.txt').write_text('tampered', encoding='utf-8')
        self.assertFalse(engine.status(done['workflow_id'])['accepted'])
        self.assertEqual(Store(self.root, read_only=True).list_workflows()['workflows'][0]['integrity'], 'not_checked')

    def test_human_status_explains_terminal_failure_and_sanitizes_reason(self):
        value = {'state': 'failed', 'stages': {'verify': {'state': 'failed', 'attempts': 1,
                  'retryable': False, 'output': {'reason': '\x1b[31mtests_failed'}}}}
        text = workflow_display.status(value)
        self.assertIn('tests_failed', text)
        self.assertIn('Повтор стадии запрещён', text)
        self.assertNotIn('\x1b', text)

    def test_human_status_prioritizes_integrity_processes_and_exhausted_budget(self):
        for value, expected in [({'integrity': 'failed', 'state': 'completed'}, 'integrity failure'),
                                ({'owner_pid': 100, 'state': 'paused'}, 'registered processes'),
                                ({'requests_remaining': 0, 'state': 'paused'}, 'Budget exhausted'),
                                ({'state': 'cancelled'}, 'terminal'),
                                ({'state': 'paused'}, 'explicit resume')]:
            with self.subTest(value=value):
                self.assertIn(expected, workflow_display.status(value, 'en'))


if __name__ == '__main__':
    unittest.main()
