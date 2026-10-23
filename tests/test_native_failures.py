"""Offline regressions for input cancellation and native delegation evidence."""
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from codex_flow import native, benchmark
from codex_flow.config import Config


class Input:
    def write(self, text): pass
    def close(self): pass


class BrokenInput(Input):
    def write(self, text): raise BrokenPipeError('synthetic closed stdin')


class BlockedInput(Input):
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
    def write(self, text):
        self.started.set()
        if not self.release.wait(3): raise TimeoutError('test writer was not stopped')
        raise BrokenPipeError('synthetic killed writer')


class Process:
    pid = 1234
    def __init__(self, stdin, events=()):
        self.stdin = stdin
        self.stdout = io.StringIO(''.join(json.dumps(event) + '\n' for event in events))
        self.stderr = io.StringIO('')
        self.returncode = None
    def poll(self): return self.returncode
    def wait(self, timeout=None):
        if self.returncode is None: self.returncode = 0
        return self.returncode


class NativeFailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='flow-native-failure-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def invoke(self, process, *, parallel=False, cancel=None):
        def terminate(proc):
            proc.returncode = -9
            if isinstance(proc.stdin, BlockedInput): proc.stdin.release.set()
        with patch.object(native, 'subscription'), patch.object(native.subprocess, 'Popen', return_value=process), \
             patch.object(native, 'terminate_tree', side_effect=terminate) as stop:
            result = native._run('fake-codex', self.root, Config(timeout_s=1), 'synthetic prompt',
                                 self.root / 'run', parallel=parallel, cancel=cancel)
        return result, stop

    def test_broken_stdin_is_typed_failure_and_terminates_process(self):
        process = Process(BrokenInput())
        result, stop = self.invoke(process)
        stop.assert_called_once_with(process)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error_category'], 'stdin_write_failed')
        self.assertEqual(result['native_exit_code'], -9)
        self.assertTrue(result['stdin_writer_stopped'])

    def test_blocked_stdin_respects_deadline_and_writer_unblocks_after_cleanup(self):
        stdin = BlockedInput()
        process = Process(stdin)
        started = time.monotonic()
        result, stop = self.invoke(process)
        self.assertLess(time.monotonic() - started, 2.5)
        self.assertTrue(stdin.started.is_set())
        stop.assert_called_once_with(process)
        self.assertEqual(result['status'], 'timed_out')
        self.assertTrue(result['stdin_writer_stopped'])

    def test_blocked_stdin_respects_cancel_without_waiting_for_deadline(self):
        stdin, cancel = BlockedInput(), threading.Event()
        process = Process(stdin)
        def request_cancel():
            if stdin.started.wait(1): cancel.set()
        requester = threading.Thread(target=request_cancel, daemon=True)
        requester.start()
        started = time.monotonic()
        result, stop = self.invoke(process, cancel=cancel)
        requester.join(1)
        self.assertLess(time.monotonic() - started, 1)
        stop.assert_called_once_with(process)
        self.assertEqual(result['status'], 'cancelled')
        self.assertTrue(result['stdin_writer_stopped'])

    def test_only_completed_native_spawn_identifies_child(self):
        child = 'synthetic-native-child-id'
        events = [{'type': 'item.completed', 'item': {'type': 'collab_tool_call', 'tool': 'spawn_agent',
                  'status': 'completed', 'receiver_thread_ids': [child]}},
                  {'type': 'turn.completed', 'usage': {}}]
        result, _ = self.invoke(Process(Input(), events), parallel=True)
        self.assertEqual(result['native_child_count'], 1)
        self.assertEqual(result['agent_count'], 2)
        self.assertEqual(result['delegation_evidence'], 'native_completed_spawn')
        self.assertNotIn(child, json.dumps(result))
        self.assertTrue(benchmark.delegation_evidence(result, Config())['multi_agent_verified'])

    def test_failed_spawn_and_wait_target_leave_child_identity_unknown(self):
        events = [{'type': 'item.completed', 'item': {'type': 'collab_tool_call', 'tool': 'spawn_agent',
                   'status': 'failed', 'receiver_thread_ids': ['synthetic-failed-child']}},
                  {'type': 'item.completed', 'item': {'type': 'collab_tool_call', 'tool': 'wait_agent',
                   'status': 'completed', 'receiver_thread_ids': ['synthetic-wait-target']}},
                  {'type': 'turn.completed', 'usage': {}}]
        result, _ = self.invoke(Process(Input(), events), parallel=True)
        self.assertIsNone(result['native_child_ids'])
        self.assertIsNone(result['native_child_count'])
        self.assertIsNone(result['agent_count'])
        self.assertFalse(benchmark.delegation_evidence(result, Config())['multi_agent_verified'])


class DelegationAccountingTests(unittest.TestCase):
    def test_failed_profile_request_does_not_verify_profile_or_agent(self):
        metrics = {'subscription': {'requests': [{'model': 'gpt-6.1-sol', 'effort': 'medium',
                   'status': 'failed', 'actual_model': None, 'usage': None}]}}
        result = benchmark.delegation_evidence(metrics, Config())
        self.assertFalse(result['multi_agent_verified'])
        self.assertFalse(result['observed_role_profile'])
        self.assertIsNone(result['multi_agent_evidence'])

    def test_completed_profile_response_is_separate_from_agent_evidence(self):
        metrics = {'subscription': {'requests': [{'model': 'gpt-6.1-sol', 'effort': 'medium',
                   'status': 'completed', 'actual_model': 'gpt-6.1-sol'}]}}
        result = benchmark.delegation_evidence(metrics, Config())
        self.assertTrue(result['observed_role_profile'])
        self.assertFalse(result['multi_agent_verified'])
        self.assertIsNone(result['multi_agent_evidence'])
        self.assertEqual(result['observed_role_profiles'][0]['requested_effort'], 'medium')

    def test_confirmed_native_child_ids_verify_delegation_without_inventing_model(self):
        result = benchmark.delegation_evidence({'native_child_ids': ['hashed-id'],
                                              'delegation_evidence': 'native_completed_spawn'}, Config())
        self.assertTrue(result['multi_agent_verified'])
        self.assertFalse(result['observed_role_profile'])
        self.assertEqual(result['multi_agent_evidence'], ['hashed-id'])


if __name__ == '__main__': unittest.main()
