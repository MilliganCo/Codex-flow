"""Owned-fixture JSONL boundary and per-Trace concurrent append regressions."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from codex_flow.contracts import PolicyError
from codex_flow.telemetry import Trace


class TraceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='flow-trace-boundary-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def link(self, source, target, *, directory=False):
        try:
            source.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest('Symlink creation unavailable on this runner')

    def test_emit_rejects_individual_log_symlink_before_outside_append(self):
        workspace = self.root / 'workspace'
        path = workspace / 'events.jsonl'
        trace = Trace(path, 'synthetic-run')
        outside = self.root / 'outside.txt'
        outside.write_text('Preserve outside fixture\n', encoding='utf-8')
        self.link(path, outside)
        before = outside.read_bytes()
        with self.assertRaises(PolicyError):
            trace.emit('synthetic.event', {'sequence': 1})
        self.assertEqual(outside.read_bytes(), before)

    def test_init_rejects_existing_individual_log_symlink(self):
        outside = self.root / 'outside.txt'
        outside.write_text('Preserve outside fixture\n', encoding='utf-8')
        path = self.root / 'events.jsonl'
        self.link(path, outside)
        with self.assertRaises(PolicyError):
            Trace(path, 'synthetic-run')
        self.assertEqual(outside.read_text(encoding='utf-8'), 'Preserve outside fixture\n')

    def test_init_rejects_linked_parent_before_creating_outside_directory(self):
        outside = self.root / 'outside'
        outside.mkdir()
        parent = self.root / 'linked-logs'
        self.link(parent, outside, directory=True)
        with self.assertRaises(PolicyError):
            Trace(parent / 'nested/events.jsonl', 'synthetic-run')
        self.assertFalse((outside / 'nested').exists())

    def test_parallel_threads_preserve_every_complete_jsonl_event(self):
        path = self.root / 'trace/events.jsonl'
        trace = Trace(path, 'synthetic-run')
        count, per_thread = 8, 40
        def append(worker):
            for sequence in range(per_thread):
                trace.emit('synthetic.parallel', {'worker': worker, 'sequence': sequence})
        with ThreadPoolExecutor(max_workers=count) as pool:
            list(pool.map(append, range(count)))
        lines = path.read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(lines), count * per_thread)
        events = [json.loads(line) for line in lines]
        self.assertEqual({event['trace_id'] for event in events}, {trace.trace_id})
        self.assertEqual({(event['payload']['worker'], event['payload']['sequence']) for event in events},
                         {(worker, sequence) for worker in range(count) for sequence in range(per_thread)})


if __name__ == '__main__': unittest.main()
