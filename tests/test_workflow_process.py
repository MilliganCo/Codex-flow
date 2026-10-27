"""Launch journaling before process creation; no project code is executed."""
import io
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from codex_flow import acceptance
from codex_flow.workflow import ProcessGuard
from codex_flow.workflow_store import Store, BusyError


class Observer:
    def __init__(self, events):
        self.events = events
    def before_spawn(self):
        self.events.append('arm')
    def __call__(self, pid):
        self.events.append(('register', pid))
    def finished(self, pid):
        self.events.append(('finished', pid))


class ProcessTests(unittest.TestCase):
    def test_launch_intent_precedes_spawn_and_clear_requires_observed_exit(self):
        with tempfile.TemporaryDirectory(prefix='flow-observer-') as temporary:
            root = Path(temporary).resolve()
            events = []
            class Process:
                pid = 987654321
                stdout, stderr = io.BytesIO(b''), io.BytesIO(b'')
                def poll(self):
                    return 0
            def launch(*args, **kwargs):
                events.append('spawn')
                self.assertFalse(kwargs['shell'])
                return Process()
            with patch.object(acceptance.subprocess, 'Popen', side_effect=launch):
                result = acceptance.capture(['inert'], {}, root, time.monotonic() + 5,
                                             root / 'cancel.request', root / 'control.json', Observer(events))
            self.assertTrue(result['sdk_root_exit_observed'])
            self.assertTrue(result['capture_complete'])
            self.assertEqual(events, ['arm', 'spawn', ('register', Process.pid), ('finished', Process.pid)])

    def test_uncertain_spawn_keeps_persisted_barrier(self):
        with tempfile.TemporaryDirectory(prefix='flow-uncertain-spawn-') as temporary:
            store = Store(Path(temporary).resolve())
            identity = store.create({'timeout_s': 60, 'max_requests': 2})
            owner = store.acquire(identity)
            root = store.root / identity
            guard = ProcessGuard(store, owner)
            try:
                with patch.object(acceptance.subprocess, 'Popen', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
                    acceptance.capture(['inert'], {}, root, time.monotonic() + 5,
                                       root / 'cancel.request', root / 'control.json', guard)
                self.assertTrue(store.get(identity)['launch_pending'])
                with self.assertRaises(BusyError):
                    store.release(owner, 'failed')
            finally:
                store.clear_launch(owner)
                store.release(owner, 'failed')

    def test_known_missing_executable_clears_no_child_intent(self):
        with tempfile.TemporaryDirectory(prefix='flow-missing-spawn-') as temporary:
            store = Store(Path(temporary).resolve())
            identity = store.create({'timeout_s': 60, 'max_requests': 2})
            owner = store.acquire(identity)
            root = store.root / identity
            try:
                with patch.object(acceptance.subprocess, 'Popen', side_effect=FileNotFoundError), self.assertRaises(FileNotFoundError):
                    acceptance.capture(['inert'], {}, root, time.monotonic() + 5,
                                       root / 'cancel.request', root / 'control.json', ProcessGuard(store, owner))
                self.assertFalse(store.get(identity)['launch_pending'])
                self.assertEqual(store.get(identity)['children'], [])
            finally:
                store.release(owner, 'failed')


if __name__ == '__main__':
    unittest.main()
