"""Loopback-only subscription observer checks; fake upstream, synthetic auth."""
from concurrent.futures import ThreadPoolExecutor
import copy
from email.message import Message
import io
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
from codex_flow.subscription import (SubscriptionGateway, RequestBudget, UPSTREAM,
                                    MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, _NoRedirect,
                                    _completed_metadata, _Validation)
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def sse(model="gpt-6.1-sol", usage=None, complete=True):
    if usage is None:
        usage = {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13,
                 "input_tokens_details": {"cached_tokens": 2},
                 "output_tokens_details": {"reasoning_tokens": 1}}
    event = {"type": "response.completed" if complete else "response.output_text.delta",
             "response": {"model": model, "usage": usage}, "delta": "private generated text"}
    return ("data: " + json.dumps(event) + "\n\n").encode()


class Response:
    def __init__(self, body=None, *, url=UPSTREAM + "/responses", status=200, content_type="text/event-stream"):
        self.body = sse() if body is None else body
        self.url, self.status = url, status
        self.headers = {"Content-Type": content_type}
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit): return self.body[:limit]
    def geturl(self): return self.url
    def close(self): pass


class Opener:
    def __init__(self, response=None, delay=0):
        self.response = response or Response()
        self.requests = []
        self.lock = threading.Lock()
        self.delay = delay
    def open(self, request, timeout):
        with self.lock:
            self.requests.append(request)
        if self.delay: time.sleep(self.delay)
        return copy.copy(self.response)


class Trace:
    def __init__(self): self.events = []
    def emit(self, kind, payload): self.events.append((kind, payload))


class SubscriptionTests(unittest.TestCase):
    def call(self, gateway, document=None, *, path="/responses", method="POST", headers=None, raw=None):
        if document is None:
            document = {"model": "gpt-6.1-sol", "reasoning": {"effort": "xhigh"},
                        "input": "private prompt", "tools": [{"type": "function", "name": "safe_tool"}]}
        h = {"Authorization": "Bearer synthetic-subscription-token", "X-Codex-Flow-Token": gateway.nonce,
             "Content-Type": "application/json"}
        if headers: h.update(headers)
        data = (raw if raw is not None else json.dumps(document).encode()) if method == "POST" else None
        request = urllib.request.Request(gateway.base_url + path, data=data, headers=h, method=method)
        try:
            with LOCAL.open(request, timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def test_success_preserves_tools_exact_payload_and_observes_actual_model_usage(self):
        opener, trace = Opener(), Trace()
        document = {"model": "gpt-6.1-sol", "reasoning": {"effort": "high"},
                    "tools": [{"type": "function", "name": "tool", "parameters": {}}], "input": "private prompt"}
        with SubscriptionGateway(opener=opener, trace=trace) as gateway:
            self.assertEqual(self.call(gateway, document)[0], 200)
            summary = gateway.summary()
        self.assertEqual(json.loads(opener.requests[0].data), document)
        self.assertEqual(opener.requests[0].full_url, UPSTREAM + "/responses")
        self.assertEqual(summary["actual_models"], ["gpt-6.1-sol"])
        self.assertEqual(summary["aggregate_usage"]["total_tokens"], 13)
        self.assertEqual(summary["aggregate_usage"]["cached_tokens"], 2)
        self.assertIsNone(summary["agent_count"])
        self.assertEqual(trace.events[0][0], "subscription.request")
        self.assertNotIn("private prompt", json.dumps(trace.events))

    def test_explicit_sse_mislabeled_json_is_accepted_and_forwarded_as_sse(self):
        self.assertEqual(_completed_metadata(b"event: response.completed\n" + sse(), "application/json")["actual_model"], "gpt-6.1-sol")
        opener = Opener(Response(sse(), content_type="application/json; charset=utf-8"))
        with SubscriptionGateway(opener=opener) as gateway:
            request = urllib.request.Request(gateway.base_url + "/responses",
                data=json.dumps({"model": "gpt-6.1-sol", "reasoning": {"effort": "xhigh"}}).encode(),
                headers={"Authorization": "Bearer synthetic-token", "X-Codex-Flow-Token": gateway.nonce})
            with LOCAL.open(request, timeout=5) as response:
                self.assertEqual(response.headers.get_content_type(), "text/event-stream")
                self.assertEqual(response.read(), sse())
            record = gateway.summary()["requests"][0]
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["reason"], "completed")
        self.assertEqual(record["response_content_type"], "application/json")
        self.assertEqual(record["response_encoding"], "identity")
        self.assertEqual(record["response_bytes"], len(sse()))

    def test_html_or_json_body_is_not_sse_even_if_mislabeled(self):
        for body in (b"<html>private upstream error</html>", b'{"error":"private upstream error"}'):
            with self.subTest(body=body), SubscriptionGateway(opener=Opener(Response(body, content_type="application/json"))) as gateway:
                status, reply = self.call(gateway)
                record = gateway.summary()["requests"][0]
                self.assertEqual(status, 403)
                self.assertEqual(record["reason"], "response_content_type")
                self.assertEqual(record["response_bytes"], len(body))
                self.assertNotIn("private", json.dumps(record) + reply.decode())

    def test_sse_failures_have_source_owned_schema_categories(self):
        cases = ((b"data: private malformed JSON\n\n", "sse_event_json"),
                 (b"data: []\n\n", "sse_event_schema"),
                 (b'data: {"type":"response.completed","response":[]}\n\n', "sse_completion_schema"),
                 (sse() + sse(), "sse_duplicate_completion"),
                 (sse(complete=False), "sse_incomplete"),
                 (b"data: \xff\n\n", "response_utf8"))
        for body, code in cases:
            with self.subTest(code=code), self.assertRaises(_Validation) as error:
                _completed_metadata(body, "text/event-stream")
            self.assertEqual(error.exception.code, code)

    def test_response_encoding_and_size_categories_are_recorded_safely(self):
        encoded = Response()
        encoded.headers["Content-Encoding"] = "gzip"
        for response, code in ((encoded, "response_encoding"),
                               (Response(b"x" * (MAX_RESPONSE_BYTES + 1)), "response_size_limit")):
            with self.subTest(code=code), SubscriptionGateway(opener=Opener(response)) as gateway:
                self.call(gateway)
                record = gateway.summary()["requests"][0]
                self.assertEqual(record["reason"], code)
                self.assertIsNone(gateway.summary()["aggregate_usage"])

    def test_nonce_subscription_bearer_routes_and_api_auth_fail_closed(self):
        opener = Opener()
        with SubscriptionGateway(opener=opener) as gateway:
            for headers in ({"X-Codex-Flow-Token": ""}, {"Authorization": ""}, {"Authorization": "Bearer sk-proj-synthetic"},
                            {"Authorization": "Bearer  sk-proj-synthetic"}):
                with self.subTest(headers=headers): self.assertEqual(self.call(gateway, headers=headers)[0], 403)
            for path in ("/responses?elsewhere=1", "/../../other", "/other"):
                with self.subTest(path=path): self.assertEqual(self.call(gateway, path=path)[0], 403)
            self.assertEqual(gateway.summary()["request_count"], 0)
        self.assertEqual(opener.requests, [])

    def test_unauthorized_body_is_consumed_before_error_reply_without_forwarding(self):
        opener = Opener()
        gateway = SubscriptionGateway(opener=opener)
        handler = object.__new__(gateway._handler())
        body = b"discard-only synthetic request body" * 100
        handler.headers = Message()
        handler.headers["Content-Length"] = str(len(body))
        handler.headers["X-Codex-Flow-Token"] = ""
        handler.path = "/backend-api/codex/responses"
        handler.connection = Mock()
        handler.connection.gettimeout.return_value = None
        handler.rfile = io.BytesIO(body)
        replies = []
        handler.respond = lambda status, data, mime: replies.append((status, handler.rfile.tell()))
        try:
            handler.forward(True)
        finally:
            gateway.__exit__(None, None, None)
        self.assertEqual(replies, [(403, len(body))])
        self.assertEqual(opener.requests, [])
        self.assertEqual(gateway.budget.used, 0)

    def test_loopback_unauthorized_inflight_body_returns_403_without_forwarding(self):
        opener = Opener()
        with SubscriptionGateway(opener=opener) as gateway:
            for _ in range(20):
                self.assertEqual(self.call(gateway, raw=b"x" * 65536,
                                           headers={"X-Codex-Flow-Token": ""})[0], 403)
            self.assertEqual(gateway.budget.used, 0)
        self.assertEqual(opener.requests, [])

    def test_incomplete_unauthorized_body_has_bounded_wait_and_no_forwarding(self):
        opener = Opener()
        with SubscriptionGateway(opener=opener) as gateway:
            started = time.monotonic()
            status, _ = self.call(gateway, raw=b"x", headers={"X-Codex-Flow-Token": "", "Content-Length": "1024"})
            self.assertEqual(status, 403)
            self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(opener.requests, [])

    def test_model_effort_allowlist(self):
        opener = Opener()
        with SubscriptionGateway(opener=opener) as gateway:
            for model, effort in (("gpt-6.1-sol", "xhigh"), ("gpt-6.1-sol", "high"),
                                  ("gpt-6.1-sol", "medium"), ("gpt-6-luna", "medium")):
                self.assertEqual(self.call(gateway, {"model": model, "reasoning": {"effort": effort}})[0], 200)
            for model, effort in (("gpt-6-luna", "max"), ("other/model", "xhigh"), ("gpt-6.1-sol", "low")):
                self.assertEqual(self.call(gateway, {"model": model, "reasoning": {"effort": effort}})[0], 403)
        self.assertEqual(len(opener.requests), 4)

    def test_request_budget_is_thread_safe_and_no_extra_upstream_retry(self):
        budget = RequestBudget(2)
        opener = Opener(delay=.05)
        with SubscriptionGateway(budget, opener=opener) as gateway:
            with ThreadPoolExecutor(max_workers=4) as pool:
                statuses = list(pool.map(lambda _: self.call(gateway)[0], range(4)))
            self.assertEqual(sorted(statuses), [200, 200, 429, 429])
            summary = gateway.summary()
        self.assertEqual((budget.used, len(opener.requests)), (2, 2))
        self.assertEqual(summary["peak_concurrent_requests"], 2)
        self.assertEqual(summary["active_requests"], 0)
        self.assertEqual(summary["aggregate_usage"]["total_tokens"], 26)

    def test_budget_constructor_bounds_and_reservation_failure(self):
        for invalid in (0, 81, True, 1.5):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError): RequestBudget(invalid)
        budget = RequestBudget(1)
        self.assertEqual(budget.reserve(), 1)
        with self.assertRaises(ValueError): budget.reserve()

    def test_models_get_is_fixed_upstream_and_does_not_consume_post_budget(self):
        opener = Opener(Response(b'{"data":[]}', url=UPSTREAM + "/models?client_version=test", content_type="application/json"))
        with SubscriptionGateway(opener=opener) as gateway:
            self.assertEqual(self.call(gateway, path="/models?client_version=test", method="GET")[0], 200)
            summary = gateway.summary()
        self.assertEqual((summary["budget_used"], summary["models_gets"]), (0, 1))

    def test_request_and_response_size_limits(self):
        opener = Opener()
        with SubscriptionGateway(opener=opener) as gateway:
            self.assertEqual(self.call(gateway, raw=b"x", headers={"Content-Length": str(MAX_REQUEST_BYTES + 1)})[0], 403)
        self.assertEqual(opener.requests, [])
        with SubscriptionGateway(opener=Opener(Response(b"x" * (MAX_RESPONSE_BYTES + 1)))) as gateway:
            self.assertEqual(self.call(gateway)[0], 403)
            self.assertIsNone(gateway.summary()["aggregate_usage"])

    def test_redirects_never_followed_or_accepted(self):
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://other.invalid"))
        with SubscriptionGateway(opener=Opener(Response(url="https://other.invalid/responses"))) as gateway:
            self.assertEqual(self.call(gateway)[0], 403)
            self.assertEqual(gateway.summary()["requests"][0]["status"], "failed")

    def test_incomplete_stream_or_missing_usage_keeps_aggregate_unknown(self):
        for response in (Response(sse(complete=False)), Response(sse(usage={})), Response(sse(usage={"input_tokens": 3}))):
            with self.subTest(response=response), SubscriptionGateway(opener=Opener(response)) as gateway:
                self.call(gateway)
                self.assertIsNone(gateway.summary()["aggregate_usage"])

    def test_usage_rejects_negative_boolean_and_unbounded_values(self):
        bad_usage = {"input_tokens": -1, "output_tokens": True, "total_tokens": 2**64,
                     "input_tokens_details": {"cached_tokens": "private output"}}
        with SubscriptionGateway(opener=Opener(Response(sse(usage=bad_usage)))) as gateway:
            self.assertEqual(self.call(gateway)[0], 200)
            self.assertIsNone(gateway.summary()["requests"][0]["usage"])
            self.assertIsNone(gateway.summary()["aggregate_usage"])

    def test_session_metadata_hashed_and_secrets_never_in_logs_or_errors(self):
        trace = Trace()
        with SubscriptionGateway(opener=Opener(), trace=trace) as gateway:
            self.call(gateway, headers={"Session_id": "private-session", "Conversation_id": "private-conversation",
                                        "X-Request-ID": "private-request"})
            safe = json.dumps((gateway.summary(), trace.events))
        for forbidden in ("private-session", "private-conversation", "private-request", "private prompt",
                          "private generated text", "synthetic-subscription-token", gateway.nonce):
            self.assertNotIn(forbidden, safe)
        self.assertEqual(len(trace.events[0][1]["session_sha256"]), 64)

    def test_upstream_failure_is_sanitized_without_retry(self):
        class Failing:
            calls = 0
            def open(self, *a, **k):
                self.calls += 1
                raise urllib.error.HTTPError(UPSTREAM, 429, "private remote error", {}, io.BytesIO(b"private auth body"))
        opener, trace = Failing(), Trace()
        with SubscriptionGateway(opener=opener, trace=trace) as gateway:
            status, body = self.call(gateway)
            safe = json.dumps((gateway.summary(), trace.events)) + body.decode()
        self.assertEqual(status, 502)
        self.assertEqual(opener.calls, 1)
        self.assertNotIn("private", safe)
        self.assertEqual(trace.events[0][1]["http_status"], 429)

    def test_server_closes_after_context(self):
        with SubscriptionGateway(opener=Opener()) as gateway:
            url = gateway.base_url
        with self.assertRaises(urllib.error.URLError):
            LOCAL.open(url + "/models", timeout=.5)

    def test_context_exit_aborts_owned_blocking_upstream_read_promptly(self):
        class Blocking(Response):
            def __init__(self):
                super().__init__()
                self.reading, self.released, self.closed = threading.Event(), threading.Event(), threading.Event()
                self.shutdown_calls = 0
                self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=self))
            def shutdown(self, how):
                self.shutdown_calls += 1
                self.released.set()
            def read(self, limit):
                self.reading.set()
                if not self.released.wait(3):
                    raise TimeoutError("fake reader not interrupted")
                raise OSError("fake stream closed")
            def close(self):
                self.closed.set()
                self.released.set()
        response = Blocking()
        class BlockingOpener:
            def open(self, *args, **kwargs): return response
        gateway = SubscriptionGateway(opener=BlockingOpener())
        gateway.__enter__()
        result = []
        worker = threading.Thread(target=lambda: result.append(self.call(gateway)), daemon=True)
        worker.start()
        try:
            self.assertTrue(response.reading.wait(1), "handler never entered the blocking upstream read")
            started = time.monotonic()
            gateway.__exit__(None, None, None)
            self.assertLess(time.monotonic() - started, 1)
            worker.join(1)
            self.assertFalse(worker.is_alive())
            self.assertTrue(response.closed.is_set())
            self.assertEqual(response.shutdown_calls, 1)
            self.assertEqual(gateway.summary()["active_requests"], 0)
            self.assertIsNone(gateway.summary()["aggregate_usage"])
            self.assertEqual(result[0][0], 503)
        finally:
            response.released.set()
            gateway.__exit__(None, None, None)

    def test_closed_gateway_rejects_late_registration_and_budget_reservation(self):
        gateway = SubscriptionGateway(opener=Opener())
        gateway.__exit__(None, None, None)
        response = Response()
        with self.assertRaisesRegex(ValueError, "cancelled"):
            gateway._register_response(response)
        with self.assertRaisesRegex(ValueError, "cancelled"):
            gateway._begin("gpt-6.1-sol", "xhigh", {})
        self.assertEqual(gateway.budget.used, 0)


if __name__ == "__main__": unittest.main()
