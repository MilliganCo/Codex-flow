"""Strict 429 inspection, cooldown and accounting; synthetic/loopback only."""
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'runtime'))
from codex_flow.subscription import SubscriptionGateway, RequestBudget, UPSTREAM, _retry_delay
from codex_flow.budget import ExecutionBudget
import test_subscription as fixture
import test_transient_recovery as recovery_fixture

FailureOpener = recovery_fixture.FailureOpener


def error_body(kind='rate_limit_error', code='slow_down'):
    return json.dumps({'error': {'type': kind, 'code': code,
                                'message': 'DO_NOT_PERSIST_PROVIDER_MESSAGE', 'param': None}}).encode()


def http_error(body=None, *, status=429, mime='application/json', length=True, retry_after='0', encoding=None):
    body = error_body() if body is None else body
    headers = Message()
    headers['Content-Type'] = mime
    if length:
        headers['Content-Length'] = str(len(body))
    if retry_after is not None:
        headers['Retry-After'] = retry_after
    if encoding:
        headers['Content-Encoding'] = encoding
    return urllib.error.HTTPError(UPSTREAM+'/responses', status, 'private diagnostic', headers, io.BytesIO(body))


class RateLimitTests(unittest.TestCase):
    call = fixture.SubscriptionTests.call
    document = recovery_fixture.RecoveryTests.document

    def setUp(self):
        self.jitter = patch('codex_flow.subscription.secrets.randbelow', return_value=0)
        self.jitter.start()
        self.addCleanup(self.jitter.stop)

    def test_known_temporary_limit_allows_one_separate_resend_and_preserves_null_usage(self):
        opener = FailureOpener(http_error(), once=True)
        with SubscriptionGateway(opener=opener, transient_recovery=True, budget=RequestBudget(2)) as gateway:
            self.assertEqual(self.call(gateway, self.document())[0], 503)
            self.assertEqual(len(opener.requests), 1)
            self.assertEqual(self.call(gateway, self.document())[0], 200)
            summary = gateway.summary()
        first, second = summary['requests']
        self.assertEqual(first['http_status'], 429)
        self.assertEqual(first['http_error_kind'], 'temporary_rate_limit')
        self.assertTrue(first['retry_eligible'])
        self.assertIsNone(first['usage'])
        self.assertEqual(first['payload_fingerprint'], second['payload_fingerprint'])
        self.assertEqual(summary['budget_used'], 2)
        self.assertEqual(summary['active_requests'], 0)
        self.assertIsNone(summary['aggregate_usage'])
        self.assertNotIn('DO_NOT_PERSIST_PROVIDER_MESSAGE', json.dumps(summary))
        self.assertNotIn('private diagnostic', json.dumps(summary))

    def test_exact_type_code_pairs_only(self):
        for kind in ('rate_limit_error', 'tokens', 'requests'):
            with self.subTest(kind=kind), SubscriptionGateway(
                    opener=FailureOpener(http_error(error_body(kind, 'rate_limit_exceeded'))),
                    transient_recovery=True) as gateway:
                self.assertEqual(self.call(gateway, self.document())[0], 503)
                self.assertTrue(gateway.summary()['requests'][0]['retry_eligible'])

    def test_quota_and_unknown_combinations_are_never_retried(self):
        cases = [('rate_limit_error', 'insufficient_quota'), ('usage_limit_reached', 'slow_down'),
                 ('credit_balance_exhausted', None), ('tokens', 'slow_down'),
                 ('invalid_request_error', 'rate_limit_exceeded'), ('rate_limit_error', 'unknown')]
        for kind, code in cases:
            opener = FailureOpener(http_error(error_body(kind, code)))
            with self.subTest(kind=kind, code=code), SubscriptionGateway(
                    opener=opener, transient_recovery=True) as gateway:
                self.assertEqual(self.call(gateway, self.document())[0], 400)
                self.assertFalse(gateway.summary()['requests'][0]['retry_eligible'])
            self.assertEqual(len(opener.requests), 1)

    def test_malformed_ambiguous_encoded_and_wrong_mime_bodies_fail_closed(self):
        bodies = [b'{"error":{"type":"rate_limit_error","code":"insufficient_quota","code":"slow_down"}}',
                  b'{"error":{"type":"rate_limit_error","code":"slow_down","message":NaN}}',
                  b'{"error":{"type":"rate_limit_error","code":"slow_down","unexpected":1}}',
                  b'{"error":[]}', b'not JSON', b'\xff', b'{"error":']
        errors = [http_error(body) for body in bodies]
        errors += [http_error(mime='text/html'), http_error(encoding='gzip')]
        for error in errors:
            with self.subTest(body_size=error.headers.get('Content-Length')), SubscriptionGateway(
                    opener=FailureOpener(error), transient_recovery=True) as gateway:
                self.assertEqual(self.call(gateway, self.document())[0], 400)
                self.assertFalse(gateway.summary()['requests'][0]['retry_eligible'])

    def test_complete_body_and_4096_byte_boundary(self):
        prefix = error_body()
        cases = [(4095, False, 503), (4096, True, 503), (4096, False, 400), (4097, False, 400),
                 (4097, True, 400)]
        for size, length, status in cases:
            error = http_error(prefix + b' '*(size-len(prefix)), length=length)
            with self.subTest(size=size, length=length), SubscriptionGateway(
                    opener=FailureOpener(error), transient_recovery=True) as gateway:
                self.assertEqual(self.call(gateway, self.document())[0], status)
                row = gateway.summary()['requests'][0]
                self.assertLessEqual(row.get('http_error_bytes_inspected', 0), 4096)
                self.assertEqual(gateway.summary()['active_requests'], 0)

    def test_duplicate_invalid_and_oversized_content_lengths_are_unknown(self):
        for value in ('duplicate', 'bad', 'oversized', 'truncated'):
            error = http_error()
            if value == 'duplicate': error.headers['Content-Length'] = error.headers['Content-Length']
            else:
                del error.headers['Content-Length']
                error.headers['Content-Length'] = {'bad':'bad', 'oversized':'4097',
                                                   'truncated':'4000'}[value]
            with self.subTest(value=value), SubscriptionGateway(
                    opener=FailureOpener(error), transient_recovery=True) as gateway:
                self.assertEqual(self.call(gateway, self.document())[0], 400)
                self.assertFalse(gateway.summary()['requests'][0]['retry_eligible'])

    def test_retry_after_parser_never_clamps_server_delay(self):
        for text, expected, source in [('0', 0., 'server'), ('60', 60., 'server'),
                                       ('61', 61., 'too_long'), ('-1', None, 'invalid'),
                                       ('0.5', None, 'invalid'), ('NaN', None, 'invalid')]:
            headers = Message(); headers['Retry-After'] = text
            self.assertEqual(_retry_delay(headers, 1800000000), (expected, source))
        headers = Message(); headers['Retry-After'] = formatdate(1800000060, usegmt=True)
        self.assertEqual(_retry_delay(headers, 1800000000), (60., 'server'))
        headers['Retry-After'] = '0'
        self.assertEqual(_retry_delay(headers, 1800000000), (None, 'invalid'))
        self.assertEqual(_retry_delay(Message(), 1800000000), (1., 'fallback'))

    def test_long_invalid_or_unaffordable_delays_defer_without_retry(self):
        for header in ('61', '0.5', 'NaN', '60'):
            with self.subTest(header=header), SubscriptionGateway(
                    opener=FailureOpener(http_error(retry_after=header)), transient_recovery=True,
                    execution_budget=ExecutionBudget(1)) as gateway:
                self.assertEqual(self.call(gateway, self.document())[0], 400)
                row = gateway.summary()['requests'][0]
                self.assertTrue(row['retry_deferred'])
                self.assertFalse(row['retry_eligible'])
                self.assertEqual(gateway.budget.used, 1)

    def test_server_minimum_delay_is_waited_and_counted_once(self):
        opener = FailureOpener(http_error(retry_after='1'))
        started = time.monotonic()
        with SubscriptionGateway(opener=opener, transient_recovery=True) as gateway:
            self.assertEqual(self.call(gateway, self.document())[0], 503)
            row = gateway.summary()['requests'][0]
        self.assertGreaterEqual(time.monotonic()-started, 1.)
        self.assertGreaterEqual(row['retry_wait_s'], 1.)
        self.assertGreaterEqual(row['duration_s'], row['retry_wait_s'])
        self.assertEqual(len(opener.requests), 1)

    def test_cancellation_during_cooldown_becomes_normal_control_response(self):
        error = http_error(retry_after='20')
        opener = FailureOpener(error)
        with SubscriptionGateway(opener=opener, transient_recovery=True) as gateway, ThreadPoolExecutor(1) as pool:
            future = pool.submit(self.call, gateway, self.document())
            deadline = time.monotonic()+2
            while not error.fp.closed and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertTrue(error.fp.closed)
            gateway.cancel()
            self.assertEqual(future.result(timeout=2)[0], 400)
            summary = gateway.summary()
        self.assertEqual(summary['budget_used'], 1)
        self.assertEqual(summary['active_requests'], 0)
        self.assertEqual(summary['control_rejections'], {'cancelled':1})
        self.assertFalse(summary['requests'][0]['retry_eligible'])
        self.assertEqual(summary['requests'][0]['failure_category'], 'control')

    def test_stalled_nested_http_error_socket_is_bounded_and_closed(self):
        release = threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(429)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length','100')
                self.end_headers(); self.wfile.write(b'{'); self.wfile.flush()
                release.wait(timeout=3)
        server = ThreadingHTTPServer(('127.0.0.1',0),Handler); server.daemon_threads=True
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        local = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        class Opener:
            def open(self, request, timeout):
                clone=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/',data=request.data,method='POST')
                return local.open(clone,timeout=timeout)
        try:
            started=time.monotonic()
            with SubscriptionGateway(opener=Opener(),transient_recovery=True) as gateway:
                self.assertEqual(self.call(gateway,self.document())[0],400)
                self.assertLess(time.monotonic()-started,1.5)
                self.assertEqual(gateway.summary()['active_requests'],0)
                self.assertEqual(gateway._responses,{})
        finally:
            release.set();server.shutdown();server.server_close();thread.join(timeout=2)

    def test_default_mode_does_not_inspect_or_retry_429(self):
        error=http_error()
        with SubscriptionGateway(opener=FailureOpener(error)) as gateway:
            self.assertEqual(self.call(gateway,self.document())[0],502)
            row=gateway.summary()['requests'][0]
        self.assertNotIn('http_error_kind',row)
        self.assertEqual(gateway.budget.used,1)

    def test_http_cleanup_error_after_valid_completion_never_waits_or_retracts_result(self):
        class Cleanup(fixture.Response):
            def __exit__(self, *_):
                raise http_error(status=503,retry_after='60')
        started=time.monotonic()
        with SubscriptionGateway(opener=fixture.Opener(Cleanup()),transient_recovery=True) as gateway:
            self.assertEqual(self.call(gateway,self.document())[0],200)
            row=gateway.summary()['requests'][0]
        self.assertLess(time.monotonic()-started,1.)
        self.assertTrue(row['semantic_completion_observed'])
        self.assertEqual(row['status'],'completed')
        self.assertEqual(row['cleanup_failure_category'],'http_error')
        self.assertNotIn('retry_wait_s',row)
        self.assertFalse(row['retry_eligible'])


if __name__ == '__main__':
    unittest.main()
