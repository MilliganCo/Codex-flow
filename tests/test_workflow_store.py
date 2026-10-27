"""Offline durable state, crash recovery, and active budget boundary tests."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from codex_flow.workflow_store import (ActiveBudget, BusyError, PersistentRequests,
                                       Store, WorkflowError, process_identity, process_probe)


class Clock:
    def __init__(self):
        self.value = 100.

    def __call__(self):
        return self.value


class Processes:
    def __init__(self):
        self.identities = {101: 'born-one', 102: 'born-two', 201: 'child-one'}
        self.states = {}

    def identity(self, pid):
        return self.identities.get(pid)

    def probe(self, pid, birth):
        if pid in self.states:
            return self.states[pid]
        current = self.identities.get(pid)
        return 'dead' if current != birth else 'alive'


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '.codex-flow' / 'workflows'
        self.processes = Processes()
        self.store = self.make_store()

    def make_store(self, pid=101):
        return Store(self.root, identity=self.processes.identity,
                     probe=self.processes.probe, pid=pid)

    def create(self, **overrides):
        return self.store.create(dict({'timeout_s': 100, 'max_requests': 3}, **overrides))


class WorkflowStoreTests(StoreTestCase):

    def test_creation_persists_frozen_spec_and_pending_stages(self):
        spec = {'timeout_s': 100, 'max_requests': 3, 'task': {'text': 'original'}}
        workflow = self.store.create(spec)
        spec['task']['text'] = 'changed'
        current = self.make_store().get(workflow)
        self.assertEqual(current['spec']['task']['text'], 'original')
        self.assertEqual(current['state'], 'pending')
        self.assertTrue((self.root / workflow).is_dir())
        self.assertEqual(list(current['stages']), ['prepare', 'generate', 'verify', 'report'])
        self.assertTrue(all(s['state'] == 'pending' for s in current['stages'].values()))

    def test_terminal_attempts_are_immutable_and_only_two_attempts_allowed(self):
        workflow = self.create()
        owner = self.store.acquire(workflow)
        first = self.store.begin_stage(owner, 'generate')
        self.store.finish_stage(owner, 'generate', 'failed', {'evidence': 'first'}, retryable=True)
        second = self.store.begin_stage(owner, 'generate')
        self.assertNotEqual(first, second)
        self.store.finish_stage(owner, 'generate', 'failed', {'evidence': 'second'}, retryable=True)
        with self.assertRaisesRegex(WorkflowError, 'attempt limit'):
            self.store.begin_stage(owner, 'generate')
        with self.assertRaisesRegex(WorkflowError, 'no running'):
            self.store.finish_stage(owner, 'generate', 'succeeded', {'overwrite': True})
        row = self.store.get(workflow)
        self.assertEqual([a['output'] for a in row['attempts']], [{'evidence': 'first'}, {'evidence': 'second'}])
        self.assertEqual(row['stages']['generate']['attempts'], 2)
        self.assertEqual(row['stages']['generate']['output'], {'evidence': 'second'})

    def test_success_and_nonretryable_failure_cannot_restart(self):
        workflow = self.create()
        owner = self.store.acquire(workflow)
        for stage, state in [('prepare', 'succeeded'), ('generate', 'failed')]:
            self.store.begin_stage(owner, stage)
            self.store.finish_stage(owner, stage, state, {'state': state})
            with self.assertRaises(WorkflowError):
                self.store.begin_stage(owner, stage)

    def test_one_project_owner_blocks_other_workflows_and_unknown_owner(self):
        one, two = self.create(), self.create()
        owner = self.store.acquire(one)
        contender = self.make_store(102)
        with self.assertRaises(BusyError):
            contender.acquire(two)
        self.processes.states[101] = 'unknown'
        with self.assertRaises(BusyError):
            contender.acquire(two)
        self.assertEqual(self.store.owner_workflow(owner), one)

    def test_simultaneous_acquire_has_one_winner(self):
        one, two = self.create(), self.create()
        contender = self.make_store(102)
        def acquire(args):
            store, workflow = args
            try:
                return store.acquire(workflow)
            except BusyError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            winners = list(pool.map(acquire, [(self.store, one), (contender, two)]))
        self.assertEqual(sum(token is not None for token in winners), 1)

    def test_pid_reuse_recovers_original_owner_and_interrupted_stage(self):
        workflow = self.create()
        owner = self.store.acquire(workflow)
        self.store.begin_stage(owner, 'generate')
        self.store.reserve_request(owner)
        self.processes.identities[101] = 'reused-pid'
        contender = self.make_store(102)
        resumed = contender.acquire(workflow)
        current = contender.get(workflow)
        self.assertEqual(current['stages']['generate']['state'], 'interrupted')
        self.assertTrue(current['stages']['generate']['retryable'])
        self.assertEqual(current['requests_used'], 1)
        self.assertEqual(current['requests'][0]['state'], 'unknown')
        contender.begin_stage(resumed, 'generate')
        with self.assertRaises(WorkflowError):
            self.store.reserve_request(owner)

    def test_children_block_recovery_until_every_identity_is_proved_dead(self):
        workflow = self.create()
        owner = self.store.acquire(workflow)
        self.store.register_child(owner, 201)
        self.processes.states[101] = 'dead'
        contender = self.make_store(102)
        for state in ('alive', 'unknown'):
            self.processes.states[201] = state
            with self.subTest(state=state), self.assertRaises(BusyError):
                contender.acquire(workflow)
        self.processes.states[201] = 'dead'
        resumed = contender.acquire(workflow)
        self.assertEqual(contender.owner_workflow(resumed), workflow)
        self.assertEqual(contender.get(workflow)['children'], [])

    def test_registered_child_prevents_release_until_controller_confirms_exit(self):
        workflow = self.create()
        owner = self.store.acquire(workflow)
        self.store.register_child(owner, 201)
        with self.assertRaises(BusyError):
            self.store.release(owner, 'paused')
        self.store.clear_child(owner, 201)
        self.store.release(owner, 'paused')
        self.assertEqual(self.store.get(workflow)['state'], 'paused')

    def test_unresolved_launch_blocks_release_and_dead_owner_recovery(self):
        workflow = self.create()
        owner = self.store.acquire(workflow)
        self.store.arm_launch(owner)
        self.assertTrue(self.store.get(workflow)['launch_pending'])
        with self.assertRaisesRegex(BusyError, 'launch blocks release'):
            self.store.release(owner, 'paused')
        self.processes.states[101] = 'dead'
        contender = self.make_store(102)
        with self.assertRaisesRegex(BusyError, 'launch blocks recovery'):
            contender.acquire(workflow)
        self.assertTrue(contender.get(workflow)['launch_pending'])

    def test_registered_identity_atomically_resolves_launch_then_allows_dead_recovery(self):
        workflow = self.create()
        owner = self.store.acquire(workflow)
        self.store.arm_launch(owner)
        self.store.register_child(owner, 201)
        current = self.store.get(workflow)
        self.assertFalse(current['launch_pending'])
        self.assertEqual(current['children'], [{'pid': 201, 'birth': 'child-one'}])
        self.processes.states[101] = 'dead'
        contender = self.make_store(102)
        with self.assertRaises(BusyError):
            contender.acquire(workflow)
        self.processes.states[201] = 'dead'
        resumed = contender.acquire(workflow)
        self.assertEqual(contender.owner_workflow(resumed), workflow)
        self.assertFalse(contender.get(workflow)['launch_pending'])

    def test_launch_intent_cannot_be_duplicated_and_known_missing_spawn_can_clear(self):
        workflow = self.create()
        owner = self.store.acquire(workflow)
        self.store.arm_launch(owner)
        with self.assertRaisesRegex(BusyError, 'already has'):
            self.store.arm_launch(owner)
        self.store.clear_launch(owner)
        self.store.clear_launch(owner)  # Normal exit hooks can safely be idempotent.
        self.assertFalse(self.store.get(workflow)['launch_pending'])
        self.store.arm_launch(owner)
        self.store.register_child(owner, 201)
        self.store.clear_child(owner, 201)
        self.store.clear_launch(owner)
        self.store.release(owner, 'paused')
        self.assertFalse(self.store.get(workflow)['launch_pending'])

    def test_request_reservations_are_atomic_cumulative_and_results_append_only(self):
        workflow = self.create()
        owner = self.store.acquire(workflow)
        budget = PersistentRequests(self.store, owner)
        with ThreadPoolExecutor(max_workers=3) as pool:
            sequences = list(pool.map(lambda _: budget.reserve(), range(3)))
        self.assertEqual(len(set(sequences)), 3)
        self.assertEqual(budget.used, 3)
        with self.assertRaisesRegex(WorkflowError, 'exhausted'):
            budget.reserve()
        record = {'sequence': min(sequences), 'status': 'failed'}
        self.store.record_requests(owner, [record, record])
        self.store.record_requests(owner, [dict(record, status='complete')])
        self.store.release(owner, 'paused')
        resumed = self.store.acquire(workflow)
        self.assertEqual(PersistentRequests(self.store, resumed).used, 3)
        row = self.store.get(workflow)
        self.assertEqual(len(row['requests'][0]['records']), 2)
        self.assertEqual(sum(r['state'] == 'unknown' for r in row['requests']), 2)
        with self.assertRaises(WorkflowError):
            self.store.record_requests(resumed, [{'sequence': 99999}])

    def test_sequences_are_cumulative_within_workflow_and_start_at_one_for_new_workflow(self):
        one, two = self.create(), self.create()
        owner = self.store.acquire(one)
        first = self.store.reserve_request(owner)
        self.store.release(owner, 'paused')
        owner = self.store.acquire(two)
        self.assertEqual(first, 1)
        self.assertEqual(self.store.reserve_request(owner), 1)
        self.assertEqual(self.store.get(two)['requests_used'], 1)

    def test_cancel_is_sticky_and_completed_workflows_are_terminal(self):
        workflow = self.create()
        owner = self.store.acquire(workflow)
        self.store.signal(workflow, 'cancel')
        self.store.signal(workflow, 'pause')
        with self.assertRaises(WorkflowError):
            self.store.reserve_request(owner)
        self.store.release(owner, 'failed')
        self.assertEqual(self.store.get(workflow)['state'], 'cancelled')
        with self.assertRaises(WorkflowError):
            self.store.acquire(workflow)
        completed = self.create()
        owner = self.store.acquire(completed)
        self.store.release(owner, 'completed')
        with self.assertRaises(WorkflowError):
            self.store.acquire(completed)

    def test_hardlinked_database_and_cancel_control_file_are_rejected(self):
        workflow = self.create()
        owner = self.store.acquire(workflow)
        budget = ActiveBudget(self.store, owner)
        control = self.root / workflow / 'cancel'
        control.write_text('original')
        os.link(control, self.root / workflow / 'second-link')
        with self.assertRaises(WorkflowError):
            budget.set_cancel_path(control)
        os.link(self.store.path, self.root / 'other.sqlite')
        with self.assertRaises(WorkflowError):
            self.store.get(workflow)

    def test_linked_workflow_directory_is_rejected(self):
        workflow = self.create()
        folder = self.root / workflow
        folder.rmdir()
        target = Path(self.temp.name) / 'outside'
        target.mkdir()
        try:
            folder.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest('creating symlinks requires Windows developer mode or permission')
        with self.assertRaises(WorkflowError):
            self.store.get(workflow)

    def test_real_process_identity_distinguishes_reused_birth(self):
        birth = process_identity(os.getpid())
        self.assertIsInstance(birth, str)
        self.assertEqual(process_probe(os.getpid(), birth), 'alive')
        self.assertEqual(process_probe(os.getpid(), birth + '-different'), 'dead')


class ActiveBudgetTests(StoreTestCase):
    def budget(self, **kwargs):
        workflow = self.create()
        owner = self.store.acquire(workflow)
        clock = Clock()
        budget = ActiveBudget(self.store, owner, clock=clock, **kwargs)
        return workflow, owner, clock, budget

    def test_active_time_reserves_30_seconds_but_returns_global_remaining(self):
        workflow, owner, clock, budget = self.budget()
        with budget:
            self.assertEqual(self.store.get(workflow)['time_reserved_s'], 30.)
            self.assertEqual(budget.remaining_s(), 100.)
            clock.value += 5
            with budget._lock:
                budget._tick()
            self.assertEqual(self.store.get(workflow)['time_spent_s'], 5.)
            self.assertEqual(budget.remaining_s(), 95.)
            self.assertEqual(budget.snapshot(2)['phase'], 'stabilize')
            clock.value += 7
        current = self.store.get(workflow)
        self.assertEqual(current['time_spent_s'], 12.)
        self.assertEqual(current['time_reserved_s'], 0.)
        self.store.release(owner, 'paused')

    def test_pause_and_downtime_do_not_charge_active_time(self):
        workflow, owner, clock, budget = self.budget()
        with budget:
            clock.value += 8
            self.store.signal(workflow, 'pause')
            self.assertEqual(budget.remaining_s(), 0.)
        self.store.release(owner, 'paused')
        clock.value += 5000
        resumed = self.store.acquire(workflow)
        with ActiveBudget(self.store, resumed, clock=clock) as next_budget:
            self.assertEqual(next_budget.remaining_s(), 92.)
            clock.value += 2
        self.assertEqual(self.store.get(workflow)['time_spent_s'], 10.)

    def test_crashed_owner_forfeits_reservation_without_refunding_or_downtime_charge(self):
        workflow, owner, clock, budget = self.budget()
        budget.__enter__()
        # Simulated abrupt process death: no context exit or refund transaction.
        budget._stop.set()
        budget._thread.join(timeout=2)
        self.processes.states[101] = 'dead'
        clock.value += 5000
        contender = self.make_store(102)
        resumed = contender.acquire(workflow)
        current = contender.get(workflow)
        self.assertEqual(current['time_spent_s'], 30.)
        self.assertEqual(current['time_reserved_s'], 0.)
        with ActiveBudget(contender, resumed, clock=clock) as next_budget:
            self.assertEqual(next_budget.remaining_s(), 70.)

    def test_expired_lease_cancels_and_does_not_silently_renew(self):
        workflow, owner, clock, budget = self.budget()
        with budget:
            clock.value += 31
            self.assertEqual(budget.remaining_s(), 0.)
            with budget._lock:
                budget._tick()
            self.assertTrue(budget.cancel_event.is_set())
            self.assertEqual(self.store.get(workflow)['time_reserved_s'], 0.)
        self.assertEqual(self.store.get(workflow)['time_spent_s'], 31.)

    def test_control_is_observed_and_writes_only_owned_cancel_path(self):
        workflow, owner, clock, budget = self.budget()
        with self.assertRaises(WorkflowError):
            budget.set_cancel_path(Path(self.temp.name) / 'foreign-cancel')
        control = self.root / workflow / 'cancel'
        budget.set_cancel_path(control)
        with budget:
            clock.value += 3
            self.store.signal(workflow, 'cancel')
            with budget._lock:
                budget._tick()
            self.assertTrue(budget.cancel_event.is_set())
            self.assertTrue(control.is_file())
            self.assertEqual(budget.remaining_s(), 0.)
        self.assertEqual(self.store.get(workflow)['time_spent_s'], 3.)

    def test_clock_rollback_cannot_restore_time_and_ledger_failure_fails_closed(self):
        workflow, owner, clock, budget = self.budget()
        with budget:
            clock.value += 10
            self.assertEqual(budget.remaining_s(), 90.)
            clock.value -= 8
            self.assertEqual(budget.remaining_s(), 90.)
            with patch.object(self.store, '_time_update', side_effect=sqlite3.OperationalError('unavailable')):
                with budget._lock:
                    budget._tick()
                self.assertEqual(budget.remaining_s(), 0.)
                self.assertTrue(budget.cancel_event.is_set())
        self.assertEqual(self.store.get(workflow)['time_spent_s'], 10.)

    def test_ownership_loss_fails_closed_even_when_new_owner_uses_same_pid(self):
        workflow, owner, clock, budget = self.budget()
        with budget:
            self.store.release(owner, 'paused')
            replacement = self.store.acquire(workflow)
            self.assertEqual(budget.remaining_s(), 0.)
            self.assertTrue(budget.cancel_event.is_set())
            self.assertEqual(self.store.owner_workflow(replacement), workflow)

    def test_second_active_budget_cannot_replace_existing_reservation(self):
        workflow, owner, clock, budget = self.budget()
        with budget:
            duplicate = ActiveBudget(self.store, owner, clock=clock)
            with self.assertRaisesRegex(WorkflowError, 'already has'):
                duplicate.__enter__()
            self.assertTrue(duplicate.cancel_event.is_set())
            self.assertEqual(self.store.get(workflow)['time_reserved_s'], 30.)

    def test_snapshot_does_not_restore_stale_request_usage(self):
        workflow, owner, clock, budget = self.budget()
        with budget:
            before = budget.snapshot(2)
            self.assertEqual(budget.snapshot(1), before)

    def test_admission_charge_persists_and_is_not_double_charged_by_refund(self):
        workflow, owner, clock, budget = self.budget()
        self.store.charge_active(owner, 7.5)
        with budget:
            self.assertEqual(budget.remaining_s(), 92.5)
            clock.value += 2.5
        current = self.store.get(workflow)
        self.assertEqual(current['time_spent_s'], 10.)
        self.assertEqual(current['time_reserved_s'], 0.)
        self.assertEqual(current['requests_used'], 0)
        self.store.release(owner, 'paused')
        clock.value += 5000
        resumed = self.store.acquire(workflow)
        self.store.charge_active(resumed, 4)
        with ActiveBudget(self.store, resumed, clock=clock) as next_budget:
            self.assertEqual(next_budget.remaining_s(), 86.)
        self.assertEqual(self.store.get(workflow)['time_spent_s'], 14.)

    def test_admission_charge_rejects_invalid_elapsed_and_active_reservation(self):
        workflow, owner, clock, budget = self.budget()
        for elapsed in [True, False, -1, float('nan'), float('inf'), -float('inf'), '1', None, 10**1000]:
            with self.subTest(elapsed=elapsed), self.assertRaises(WorkflowError):
                self.store.charge_active(owner, elapsed)
        self.assertEqual(self.store.get(workflow)['time_spent_s'], 0.)
        with budget:
            with self.assertRaisesRegex(WorkflowError, 'already has'):
                self.store.charge_active(owner, 4)
            self.assertEqual(self.store.get(workflow)['time_spent_s'], 0.)

    def test_admission_charge_clamps_to_remaining_total_budget(self):
        workflow, owner, clock, budget = self.budget()
        self.store.charge_active(owner, 150)
        self.assertEqual(self.store.get(workflow)['time_spent_s'], 100.)
        with budget:
            self.assertEqual(budget.remaining_s(), 0.)
            self.assertTrue(budget.cancel_event.is_set())


if __name__ == '__main__':
    unittest.main()
