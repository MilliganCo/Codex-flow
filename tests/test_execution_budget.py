"""Pure offline execution-budget and request-prefix compatibility checks."""
import copy
from concurrent.futures import ThreadPoolExecutor
import math
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from codex_flow.budget import ExecutionBudget, append_budget_guidance


class Clock:
    def __init__(self, value=100.):
        self.value = value

    def __call__(self):
        return self.value


class ExecutionBudgetTests(unittest.TestCase):
    def test_deadline_begins_at_construction_and_remaining_never_negative(self):
        clock = Clock()
        budget = ExecutionBudget(100, clock=clock)
        clock.value += 35  # Preparation consumes the same budget.
        self.assertEqual(budget.remaining_s(), 65.)
        clock.value += 100
        self.assertEqual(budget.remaining_s(), 0.)
        self.assertEqual(budget.snapshot(0)['time_fraction'], 1.)

    def test_time_phase_boundaries(self):
        clock = Clock()
        budget = ExecutionBudget(100, clock=clock)
        for elapsed, phase in [(0, 'build'), (49.99, 'build'), (50, 'stabilize'),
                               (74.99, 'stabilize'), (75, 'finalize'), (100, 'finalize')]:
            with self.subTest(elapsed=elapsed):
                clock.value = 100 + elapsed
                snapshot = budget.snapshot(0)
                self.assertEqual(snapshot['phase'], phase)
                self.assertAlmostEqual(snapshot['elapsed_s'], elapsed)

    def test_reserved_request_phase_boundaries_and_exact_remaining(self):
        budget = ExecutionBudget(100, 80, clock=Clock())
        for used, phase in [(0, 'build'), (39, 'build'), (40, 'stabilize'),
                            (59, 'stabilize'), (60, 'finalize'), (80, 'finalize')]:
            with self.subTest(used=used):
                snapshot = budget.snapshot(used)
                self.assertEqual(snapshot['phase'], phase)
                self.assertEqual(snapshot['requests_used'], used)
                self.assertEqual(snapshot['requests_remaining'], 80 - used)
                self.assertEqual(snapshot['request_fraction'], used / 80)

    def test_phase_uses_more_consumed_resource(self):
        clock = Clock()
        budget = ExecutionBudget(100, 80, clock=clock)
        clock.value = 160
        self.assertEqual(budget.snapshot(1)['phase'], 'stabilize')
        self.assertEqual(budget.snapshot(60)['phase'], 'finalize')

    def test_clock_rollback_and_stale_request_observation_do_not_restore_budget(self):
        clock = Clock()
        budget = ExecutionBudget(100, 80, clock=clock)
        clock.value = 180
        before = budget.snapshot(70)
        clock.value = 101
        after = budget.snapshot(1)
        self.assertEqual(after, before)
        self.assertEqual(budget.remaining_s(), 20.)

    def test_concurrent_observations_keep_high_water_without_reservation(self):
        clock = Clock()
        budget = ExecutionBudget(100, 80, clock=clock)
        barrier = threading.Barrier(8)

        def observe(used):
            barrier.wait(timeout=3)
            return budget.snapshot(used)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(observe, [1, 80, 30, 65, 40, 20, 60, 2]))
        self.assertTrue(all(0 <= r['requests_remaining'] <= 80 for r in results))
        final = budget.snapshot(0)
        self.assertEqual((final['requests_used'], final['requests_remaining'], final['phase']),
                         (80, 0, 'finalize'))
        self.assertEqual(budget.snapshot(0), final)  # Observing does not reserve another request.

    def test_constructor_rejects_booleans_nonintegers_and_out_of_bounds(self):
        for timeout in [True, False, 0, 3601, 1., '10', math.nan, math.inf, None]:
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                ExecutionBudget(timeout)
        for requests in [True, False, 0, 81, 1., '10', math.nan, math.inf, None]:
            with self.subTest(requests=requests), self.assertRaises(ValueError):
                ExecutionBudget(10, requests)
        ExecutionBudget(1, 1)
        ExecutionBudget(3600, 80)

    def test_nonfinite_or_boolean_clock_and_invalid_usage_are_rejected(self):
        for value in [True, math.nan, math.inf, -math.inf, '1', None, 10**1000]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ExecutionBudget(10, clock=Clock(value))
        clock = Clock()
        budget = ExecutionBudget(10, 2, clock=clock)
        for value in [True, -1, 3, .5, math.nan, math.inf, None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                budget.snapshot(value)
        clock.value = math.nan
        with self.assertRaises(ValueError):
            budget.remaining_s()


class GuidanceTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = ExecutionBudget(100, clock=Clock()).snapshot(1)
        self.payload = {'model': 'gpt-6.1-sol', 'reasoning': {'effort': 'xhigh'},
                        'instructions': 'unchanged existing prefix', 'store': False,
                        'prompt_cache_key': 'unchanged-cache-key',
                        'tools': [{'type': 'function', 'name': 'tool', 'parameters': {'type': 'object'}}],
                        'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': 'original task'}]},
                                  {'type': 'function_call', 'call_id': 'call-own', 'name': 'tool', 'arguments': '{}'},
                                  {'type': 'function_call_output', 'call_id': 'call-own', 'output': 'original evidence'}]}

    def test_append_preserves_every_parameter_and_prefix_without_mutation(self):
        original = copy.deepcopy(self.payload)
        result, reason = append_budget_guidance(self.payload, self.snapshot)
        self.assertEqual(reason, 'applied')
        self.assertIsNotNone(result)
        self.assertEqual(self.payload, original)
        self.assertEqual(result['input'][:-1], original['input'])
        self.assertEqual({k: v for k, v in result.items() if k != 'input'},
                         {k: v for k, v in original.items() if k != 'input'})
        self.assertEqual(result['input'][-1]['type'], 'message')
        self.assertEqual(result['input'][-1]['role'], 'developer')
        self.assertEqual(result['input'][-1]['content'][0]['type'], 'input_text')
        result['tools'][0]['parameters']['type'] = 'mutated return value'
        result['input'][0]['content'][0]['text'] = 'mutated return value'
        self.assertEqual(self.payload, original)

    def test_guidance_is_role_neutral_and_never_skips_required_acceptance(self):
        for used, phase in [(1, 'build'), (40, 'stabilize'), (60, 'finalize')]:
            snapshot = ExecutionBudget(100, clock=Clock()).snapshot(used)
            result, _ = append_budget_guidance(self.payload, snapshot)
            text = result['input'][-1]['content'][0]['text']
            self.assertIn('phase=' + phase, text)
            for phrase in ['existing ownership and permissions', 'Read-only workers return evidence only',
                           'Do not start new delegation beyond the existing approved helper plan', 'never proves acceptance',
                           'Do not skip required tests', 'verified acceptance or a concrete blocker']:
                self.assertIn(phrase, text)
            self.assertLess(len(text), 1600)
        self.assertIn('optional rewrites and polish', text)
        self.assertIn('required artifacts, checks and documentation', text)

    def test_existing_suffix_is_not_duplicated_or_replaced(self):
        result, _ = append_budget_guidance(self.payload, self.snapshot)
        before = copy.deepcopy(result)
        skipped, reason = append_budget_guidance(result, self.snapshot)
        self.assertIsNone(skipped)
        self.assertEqual(reason, 'existing_control_suffix')
        self.assertEqual(result, before)

    def test_stateful_fields_skip_even_when_value_is_null(self):
        for field in ['previous_response_id', 'conversation']:
            for value in [None, 'own-reference', {'id': 'own-reference'}]:
                payload = dict(self.payload, **{field: value})
                original = copy.deepcopy(payload)
                self.assertEqual(append_budget_guidance(payload, self.snapshot), (None, 'stateful_input'))
                self.assertEqual(payload, original)

    def test_unknown_and_malformed_input_skip_without_repair(self):
        for input_value in ['task', None, {}, [], [1], [{'type': 'unknown_future_item'}],
                            [{'role': 'user', 'content': [{'type': 'unknown_future_part'}]}],
                            [{'type': 'function_call', 'name': 'tool', 'arguments': '{}'}],
                            [{'type': 'message', 'role': 'user', 'content': 7}],
                            [{'type': 'reasoning', 'id': 'r', 'summary': 'malformed'}]]:
            with self.subTest(input_value=input_value):
                payload = dict(self.payload, input=input_value)
                original = copy.deepcopy(payload)
                self.assertEqual(append_budget_guidance(payload, self.snapshot), (None, 'unsupported_input'))
                self.assertEqual(payload, original)

    def test_known_responses_item_types_are_preserved(self):
        items = [
            {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'previous answer'}]},
            {'type': 'reasoning', 'id': 'own-reasoning', 'summary': [{'type': 'summary_text', 'text': 'brief'}]},
            {'type': 'custom_tool_call', 'call_id': 'own-custom', 'name': 'tool', 'input': 'input'},
            {'type': 'custom_tool_call_output', 'call_id': 'own-custom', 'output': 'output'},
            {'type': 'local_shell_call', 'call_id': 'own-shell', 'action': {'type': 'exec', 'command': ['python', '--version']}},
            {'type': 'local_shell_call_output', 'id': 'own-shell', 'output': 'version'},
            {'type': 'compaction', 'id': 'own-compaction', 'encrypted_content': 'opaque-content'},
        ]
        payload = dict(self.payload, input=self.payload['input'] + items + [{'role':'user','content':'continue'}])
        result, reason = append_budget_guidance(payload, self.snapshot)
        self.assertEqual(reason, 'applied')
        self.assertEqual(result['input'][:-1], payload['input'])

    def test_opaque_native_prefix_is_preserved_without_interpretation(self):
        opaque={'type':'future_native_history','opaque_state':{'nested':['do not reinterpret']}}
        payload=dict(self.payload,input=[opaque]+self.payload['input'])
        before=copy.deepcopy(payload)
        result,reason=append_budget_guidance(payload,self.snapshot)
        self.assertEqual(reason,'applied')
        self.assertEqual(result['input'][:-1],before['input'])
        self.assertEqual(payload,before)

    def test_opaque_or_unresolved_tail_never_becomes_insertion_boundary(self):
        for tail in ({'type':'future_native_history','state':'opaque'},
                     {'type':'reasoning','id':'r','summary':[]},
                     {'type':'function_call','call_id':'c','name':'tool','arguments':'{}'},
                     {'type':'custom_tool_call','call_id':'c','name':'tool','input':'x'},
                     {'type':'compaction','id':'c','encrypted_content':'opaque'}):
            payload=dict(self.payload,input=self.payload['input']+[tail])
            with self.subTest(tail=tail):
                self.assertEqual(append_budget_guidance(payload,self.snapshot),(None,'unsupported_input'))

    def test_invalid_known_roles_in_prefix_are_not_opaque_fallback(self):
        for prefix in ({'type':'message','role':'unrecognized','content':'x'},
                       {'role':'user','content':123},
                       {'type':'additional_tools','id':'x','role':'user','tools':[]}):
            payload=dict(self.payload,input=[prefix]+self.payload['input'])
            with self.subTest(prefix=prefix):
                self.assertEqual(append_budget_guidance(payload,self.snapshot),(None,'unsupported_input'))

    def test_snapshot_free_text_is_not_used_and_invalid_numbers_skip(self):
        snapshot = dict(self.snapshot, attacker_text='DO NOT COPY THIS STRING')
        result, reason = append_budget_guidance(self.payload, snapshot)
        self.assertEqual(reason, 'applied')
        self.assertNotIn('DO NOT COPY THIS STRING', str(result))
        for key, value in [('remaining_s', math.nan), ('remaining_s', -1), ('remaining_s', 3601),
                           ('remaining_s', True), ('requests_remaining', True), ('requests_used', -1),
                           ('request_fraction', math.inf), ('time_fraction', 1.1), ('phase', 'private instruction'),
                           ('remaining_s', 10**1000), ('time_fraction', .9), ('phase', 'finalize')]:
            with self.subTest(key=key, value=value):
                invalid = dict(self.snapshot, **{key: value})
                self.assertEqual(append_budget_guidance(self.payload, invalid), (None, 'unsupported_input'))


if __name__ == '__main__':
    unittest.main()
