"""Owned SQLite fixtures only; no native/global metadata, sandbox, or models."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import io
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from codex_flow import native, benchmark
from codex_flow.config import Config
from codex_flow.native_metadata import observe_children, canonical_cwd


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='flow-own-metadata-')
        self.addCleanup(self.tmp.cleanup)
        self.fixture = Path(self.tmp.name).resolve()
        self.workspace = self.fixture / 'workspace'
        self.state = self.workspace / '.codex-flow/native-state'
        self.state.mkdir(parents=True)
        self.database = self.state / 'state_5.sqlite'
        self.root_id, self.child_id = str(uuid.uuid4()), str(uuid.uuid4())
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('CREATE TABLE threads(id TEXT PRIMARY KEY,cwd TEXT,source TEXT,tokens_used INTEGER,model TEXT,reasoning_effort TEXT,agent_role TEXT,created_at INTEGER,rollout_path TEXT)')
        self.add(self.root_id, 'exec', 87806)

    def source(self, parent=None, depth=1):
        return json.dumps({'subagent': {'thread_spawn': {'parent_thread_id': parent or self.root_id,
                                                       'depth': depth, 'agent_role': 'worker'}}})

    def add(self, identity, source, tokens, cwd=None):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('INSERT INTO threads VALUES(?,?,?,?,?,?,?,?,?)',
                (identity, str(cwd or self.workspace), source, tokens, 'gpt-6.1-sol', 'medium', 'worker', 1,
                 'private unrelated rollout path - never selected'))

    def test_exact_root_parent_link_and_positive_child_usage_produce_sanitized_evidence(self):
        self.add(self.child_id, self.source(), 33234)
        result = observe_children(self.workspace, self.root_id)
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(result['reason'], 'native_parent_link_and_usage_metadata')
        self.assertEqual(len(result['children']), 1)
        child = result['children'][0]
        self.assertEqual((child['model'], child['requested_effort'], child['depth'], child['tokens_used']),
                         ('gpt-6.1-sol', 'medium', 1, 33234))
        self.assertEqual(len(child['thread_sha256']), 64)
        self.assertIsNone(result['peak_concurrent_agents'])
        serialized = json.dumps(result)
        for private in (self.root_id, self.child_id, str(self.workspace), self.source(), 'rollout', 'nickname'):
            self.assertNotIn(private, serialized)
        evidence = benchmark.delegation_evidence({'native_child_ids': [child['thread_sha256']],
                    'delegation_evidence': result['reason']}, Config())
        self.assertTrue(evidence['multi_agent_verified'])

    def test_zero_usage_and_foreign_child_cwd_do_not_verify_inference(self):
        self.add(self.child_id, self.source(), 0)
        self.add(str(uuid.uuid4()), self.source(), 100, cwd=self.fixture / 'foreign')
        result = observe_children(self.workspace, self.root_id)
        self.assertEqual(result['children'], [])
        self.assertEqual(result['reason'], 'no_used_children')

    def test_uuid_in_unrelated_or_malformed_source_never_reads_child_values(self):
        foreign_id = str(uuid.uuid4())
        foreign = json.loads(self.source(parent=str(uuid.uuid4())))
        foreign['note'] = self.root_id
        self.add(foreign_id, json.dumps(foreign), 700)
        self.add(str(uuid.uuid4()), 'malformed source contains ' + self.root_id, 800)
        statements = []
        original = sqlite3.connect
        def connect(*args, **kwargs):
            connection = original(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection
        with patch('codex_flow.native_metadata.sqlite3.connect', side_effect=connect):
            result = observe_children(self.workspace, self.root_id)
        self.assertEqual(result['children'], [])
        self.assertFalse(any('SELECT cwd,tokens_used' in sql for sql in statements))
        self.assertFalse(any('rollout_path' in sql for sql in statements))

    def test_foreign_root_cwd_stops_before_any_source_candidates(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('UPDATE threads SET cwd=? WHERE id=?', (str(self.fixture / 'foreign'), self.root_id))
        result = observe_children(self.workspace, self.root_id)
        self.assertEqual(result['reason'], 'root_cwd_mismatch')
        self.assertIsNone(result['children'])

    def test_unknown_root_source_and_relative_root_cwd_are_not_execution_evidence(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('UPDATE threads SET source=? WHERE id=?', ('unknown', self.root_id))
        self.assertEqual(observe_children(self.workspace, self.root_id)['reason'], 'root_source_schema')
        self.assertIsNone(canonical_cwd(''))
        self.assertIsNone(canonical_cwd('relative-workspace'))

    def test_unknown_parent_shape_fails_closed(self):
        self.add(self.child_id, self.source(depth='1'), 12)
        result = observe_children(self.workspace, self.root_id)
        self.assertEqual(result['reason'], 'parent_link_schema')
        self.assertIsNone(result['children'])

    def test_missing_identity_never_connects_and_missing_database_is_not_created(self):
        with patch('codex_flow.native_metadata.sqlite3.connect', side_effect=AssertionError('unexpected database read')):
            self.assertEqual(observe_children(self.workspace, None)['reason'], 'root_id_unavailable')
        self.database.unlink()
        self.assertEqual(observe_children(self.workspace, self.root_id)['reason'], 'state_missing')
        self.assertFalse(self.database.exists())

    def test_unknown_schema_is_unavailable(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('DROP TABLE threads')
            connection.execute('CREATE TABLE threads(id TEXT)')
        self.assertEqual(observe_children(self.workspace, self.root_id)['reason'], 'state_schema')

    def test_database_symlink_is_rejected_before_connect(self):
        outside = self.fixture / 'outside.sqlite'
        self.database.replace(outside)
        try:
            self.database.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest('Symlink creation unavailable on this runner')
        before = outside.read_bytes()
        with patch('codex_flow.native_metadata.sqlite3.connect', side_effect=AssertionError('symlink database opened')):
            result = observe_children(self.workspace, self.root_id)
        self.assertEqual(result['reason'], 'state_unavailable')
        self.assertEqual(outside.read_bytes(), before)

    def test_windows_extended_prefix_and_case_canonicalization(self):
        self.assertEqual(canonical_cwd(r'\\?\E:\Owned\Workspace'), canonical_cwd('e:/owned/workspace'))
        self.assertEqual(canonical_cwd(r'\\?\UNC\server\share\Workspace'), canonical_cwd(r'\\SERVER\share\workspace'))

    def test_actual_controller_plan_only_changes_parallel_developer_instructions(self):
        original = 'Caller instructions remain stable.'
        def instructions(parallel):
            argv = native.argv('fake', self.workspace, Config(max_agents=2), parallel=parallel, instructions=original)
            return next(json.loads(argv[index + 1].split('=', 1)[1]) for index, item in enumerate(argv[:-1])
                        if item == '-c' and argv[index + 1].startswith('developer_instructions='))
        self.assertEqual(instructions(False), original)
        actual = instructions(True)
        self.assertTrue(actual.startswith(original))
        for required in ('selected_strategy=parallel', 'max_helpers=2', 'delegation_depth=1',
                         'human owner explicitly authorized', 'FIRST TOOL ACTION', 'exactly one', 'read-only worker',
                         'required execution step', 'BEFORE editing', 'receive its evidence', 'do not retry'):
            self.assertIn(required, actual)

    def test_cli_root_identity_is_used_only_after_exit_and_is_never_persisted_raw(self):
        self.add(self.child_id, self.source(), 33234)
        events = [{'type': 'thread.started', 'thread_id': self.root_id}, {'type': 'turn.completed', 'usage': {}}]
        class Process:
            pid = 1234
            returncode = None
            stdin = io.StringIO()
            stdout = io.StringIO(''.join(json.dumps(event) + '\n' for event in events))
            stderr = io.StringIO('')
            def poll(self): return self.returncode
            def wait(self, timeout=None): self.returncode = 0; return 0
        process = Process()
        def after_exit(workspace, identity):
            self.assertEqual(process.returncode, 0)
            self.assertEqual(identity, self.root_id)
            return observe_children(workspace, identity)
        output = self.fixture / 'run'
        with patch.object(native, 'subscription'), patch.object(native.subprocess, 'Popen', return_value=process), \
             patch('codex_flow.native_metadata.observe_children', side_effect=after_exit):
            result = native._run('fake', self.workspace, Config(), 'Unchanged synthetic task brief', output, parallel=True)
        self.assertEqual(result['delegation_evidence'], 'native_parent_link_and_usage_metadata')
        self.assertEqual(result['native_child_count'], 1)
        self.assertEqual(result['orchestration_status'], 'verified')
        self.assertEqual(result['orchestration_reason'], 'native_parent_link_and_usage_metadata')
        self.assertEqual(result['status'], 'completed_unverified')
        self.assertTrue(benchmark.delegation_evidence(result, Config())['multi_agent_verified'])
        for path in (output / 'metrics.json', output / 'events.jsonl'):
            data = path.read_text(encoding='utf-8')
            self.assertNotIn(self.root_id, data)
            self.assertNotIn(self.child_id, data)

    def test_parallel_without_authoritative_child_is_degraded_despite_completed_execution(self):
        class Process:
            pid = 1234
            returncode = None
            stdin = io.StringIO()
            stdout = io.StringIO(json.dumps({'type': 'thread.started', 'thread_id': self.root_id}) + '\n' +
                                 json.dumps({'type': 'turn.completed', 'usage': {}}) + '\n')
            stderr = io.StringIO('')
            def poll(self): return self.returncode
            def wait(self, timeout=None): self.returncode = 0; return 0
        with patch.object(native, 'subscription'), patch.object(native.subprocess, 'Popen', return_value=Process()):
            result = native._run('fake', self.workspace, Config(), 'Unchanged synthetic task brief',
                                 self.fixture / 'run', parallel=True)
        self.assertEqual(result['status'], 'completed_unverified')
        self.assertEqual(result['orchestration_status'], 'degraded')
        self.assertEqual(result['orchestration_reason'], 'helper_not_observed')
        self.assertIsNone(result['native_child_count'])


if __name__ == '__main__': unittest.main()
