"""Opt-in stateless recovery contracts; loopback and synthetic upstream only."""
import copy
import http.client
import json
from pathlib import Path
import ssl
import sys
import unittest
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from codex_flow import native
from codex_flow.budget import ExecutionBudget
from codex_flow.config import Config
from codex_flow.contracts import PolicyError
from codex_flow.subscription import SubscriptionGateway, RequestBudget, UPSTREAM
import test_subscription as fixture


class FailureOpener(fixture.Opener):
    def __init__(self, error, once=False, response=None):
        super().__init__(response=response)
        self.error, self.once = error, once

    def open(self, request, timeout):
        self.requests.append(request)
        if not self.once or len(self.requests) == 1:
            raise self.error
        return copy.copy(self.response)


class RecoveryTests(unittest.TestCase):
    call = fixture.SubscriptionTests.call

    def document(self):
        return {'model': 'gpt-6.1-sol', 'reasoning': {'effort': 'xhigh'},
                'input': [{'role': 'user', 'content': 'private fixture'}], 'store': False}

    def test_default_off_and_strict_opt_in_limit(self):
        self.assertEqual(Config().native_request_retries, 0)
        for value in (-1, 2, True, 1.0, '1', None):
            with self.subTest(value=value), self.assertRaises(PolicyError):
                Config(native_request_retries=value)
        for value in (0, 1):
            command = native.argv('fake', Path('workspace'), Config(native_request_retries=value))
            options = {command[i+1].split('=', 1)[0]: json.loads(command[i+1].split('=', 1)[1])
                       for i, item in enumerate(command[:-1]) if item == '-c'}
            self.assertEqual(options['model_providers.flow_subscription.request_max_retries'], value)
            self.assertEqual(options['model_providers.flow_subscription.stream_max_retries'], 0)
            self.assertFalse(options['sandbox_workspace_write.network_access'])

    def test_all_recovery_inputs_must_be_stateless_before_reservation_or_forward(self):
        documents = []
        for field in ('previous_response_id', 'conversation', 'background'):
            documents.append({**self.document(), field: None})
        for value in (None, True, 'false', 0):
            documents.append({**self.document(), 'store': value})
        documents.append({k: v for k, v in self.document().items() if k != 'store'})
        documents.append({**self.document(), 'input': 'not a full input array'})
        opener = fixture.Opener()
        with SubscriptionGateway(opener=opener, transient_recovery=True) as gateway:
            for document in documents:
                with self.subTest(document_keys=list(document)):
                    self.assertEqual(self.call(gateway, document)[0], 400)
            self.assertEqual(gateway.budget.used, 0)
        self.assertEqual(opener.requests, [])

    def test_one_explicit_resend_preserves_bytes_and_reserves_both_attempts(self):
        opener = FailureOpener(ConnectionResetError(), once=True)
        budget = RequestBudget(2)
        with SubscriptionGateway(opener=opener, budget=budget, transient_recovery=True) as gateway:
            self.assertEqual(self.call(gateway, self.document())[0], 503)
            self.assertEqual(len(opener.requests), 1)  # Gateway itself never replays.
            self.assertEqual(self.call(gateway, self.document())[0], 200)
            summary = gateway.summary()
        self.assertEqual(budget.used, 2)
        self.assertEqual(opener.requests[0].data, opener.requests[1].data)
        first, second = summary['requests']
        self.assertTrue(first['retry_eligible'])
        self.assertIs(first['semantic_completion_observed'], False)
        self.assertIsNone(first['usage'])
        self.assertFalse(second['retry_eligible'])
        self.assertEqual(first['payload_fingerprint'], second['payload_fingerprint'])
        self.assertIsNone(summary['aggregate_usage'])
        self.assertEqual(summary['transient_recovery']['gateway_replays'], 0)
        self.assertNotIn('private fixture', json.dumps(summary))

    def test_retry_cannot_extend_request_cap_or_cancelled_deadline(self):
        opener = FailureOpener(ConnectionResetError())
        with SubscriptionGateway(opener=opener, budget=RequestBudget(1), transient_recovery=True) as gateway:
            self.assertEqual(self.call(gateway, self.document())[0], 503)
            self.assertEqual(self.call(gateway, self.document())[0], 400)
            self.assertEqual(gateway.budget.used, 1)
            self.assertEqual(gateway.summary()['control_rejections'], {'request_budget_exhausted': 1})
        clock = [0.]
        budget = ExecutionBudget(1, clock=lambda: clock[0])
        clock[0] = 2.
        with SubscriptionGateway(opener=opener, execution_budget=budget, transient_recovery=True) as gateway:
            self.assertEqual(self.call(gateway, self.document())[0], 400)
            self.assertEqual(gateway.budget.used, 0)
        self.assertEqual(len(opener.requests), 1)

    def test_auth_quota_validation_and_unknown_errors_are_not_retryable(self):
        errors = [(urllib.error.HTTPError(UPSTREAM, code, 'unrecorded', {}, None), 403)
                  for code in (401, 403)]
        errors += [(urllib.error.HTTPError(UPSTREAM, 429, 'quota', {}, None), 400),
                   (ssl.SSLError('private TLS text'), 400), (OSError('private I/O text'), 400),
                   (urllib.error.URLError('timeout text is not a typed error'), 400)]
        for error, code in errors:
            opener = FailureOpener(error)
            with self.subTest(error_type=type(error).__name__), \
                    SubscriptionGateway(opener=opener, transient_recovery=True) as gateway:
                self.assertEqual(self.call(gateway, self.document())[0], code)
                row = gateway.summary()['requests'][0]
                self.assertFalse(row['retry_eligible'])
                self.assertIsNone(row['usage'])
            self.assertEqual(len(opener.requests), 1)

    def test_only_typed_transient_failures_or_selected_5xx_get_503(self):
        errors = [TimeoutError(), ConnectionResetError(), ConnectionAbortedError(),
                  http.client.IncompleteRead(b'bounded', 1), urllib.error.URLError(TimeoutError())]
        errors += [urllib.error.HTTPError(UPSTREAM, code, 'unrecorded', {}, None) for code in (500, 502, 503, 504)]
        for error in errors:
            with self.subTest(error_type=type(error).__name__), \
                    SubscriptionGateway(opener=FailureOpener(error), transient_recovery=True) as gateway:
                self.assertEqual(self.call(gateway, self.document())[0], 503)
                self.assertTrue(gateway.summary()['requests'][0]['retry_eligible'])

    def test_partial_model_output_is_not_forwarded_on_timeout(self):
        class Partial(fixture.Response):
            calls = 0
            def read1(self, _limit):
                self.calls += 1
                if self.calls == 1:
                    return b'data: {"type":"response.output_text.delta","delta":"DO_NOT_DELIVER"}\n\n'
                raise TimeoutError()
        with SubscriptionGateway(opener=fixture.Opener(Partial()), transient_recovery=True) as gateway:
            code, raw = self.call(gateway, self.document())
            self.assertEqual(code, 503)
            self.assertNotIn(b'DO_NOT_DELIVER', raw)
            row = gateway.summary()['requests'][0]
            self.assertEqual(row['http_status'], 200)
            self.assertTrue(row['retry_eligible'])
            self.assertFalse(row['semantic_completion_observed'])
            self.assertIsNone(row['usage'])

    def test_invalid_terminal_is_not_replayed_and_valid_terminal_cleanup_is_success(self):
        invalid = fixture.Response(b'data: {"type":"response.failed","response":{"status":"failed"}}\n\n')
        with SubscriptionGateway(opener=fixture.Opener(invalid), transient_recovery=True) as gateway:
            self.assertEqual(self.call(gateway, self.document())[0], 400)
            self.assertFalse(gateway.summary()['requests'][0]['retry_eligible'])
        class CleanupFailure(fixture.Response):
            def __exit__(self, *_):
                raise TimeoutError()
        with SubscriptionGateway(opener=fixture.Opener(CleanupFailure()), transient_recovery=True) as gateway:
            self.assertEqual(self.call(gateway, self.document())[0], 200)
            row = gateway.summary()['requests'][0]
            self.assertEqual(row['status'], 'completed')
            self.assertFalse(row['retry_eligible'])

    def test_recovery_rejects_input_mutation_and_nonboolean_option(self):
        with self.assertRaises(ValueError):
            SubscriptionGateway(transient_recovery=True, guidance=True)
        with self.assertRaises(ValueError):
            SubscriptionGateway(transient_recovery=1)


if __name__ == '__main__':
    unittest.main()
