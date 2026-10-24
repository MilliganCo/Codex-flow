"""Synthetic SSE faults and real loopback HTTP framing; never external inference."""
from contextlib import contextmanager
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
import unittest
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
from codex_flow.budget import ExecutionBudget
from codex_flow.subscription import (
    MAX_RESPONSE_BYTES, UPSTREAM, RequestBudget, SubscriptionGateway,
    _completed_metadata, _Validation,
)
import test_subscription as fixture


PRIVATE = "synthetic-private-stream-context"
USAGE = {"input_tokens": 11, "output_tokens": 4, "total_tokens": 15}
FIXED_TERMINATIONS = {
    "response_completed", "http_eof", "read_error", "control",
    "validation_error", "buffered_fallback", "response_size_limit",
    "completed_before_http_error",
}


def frame(kind="response.completed", *, newline=b"\n", response=None, multiline=False):
    document = {"type": kind, "response": (
        {"model": "gpt-6.1-sol", "status": "completed", "usage": dict(USAGE)}
        if response is None else response
    )}
    text = json.dumps(document, ensure_ascii=False, indent=2 if multiline else None)
    return newline.join(b"data: " + line.encode("utf-8") for line in text.splitlines()) + newline * 2


class StreamResponse:
    """read1 exposes bounded chunks; read is forbidden to catch whole-body buffering."""
    status = 200

    def __init__(self, body, *, chunk_size=17, tail=None, after_read=None,
                 content_type="text/event-stream", close_error=None):
        self.body = body
        self.chunk_size = chunk_size
        self.tail = tail
        self.after_read = after_read
        self.headers = {"Content-Type": content_type}
        self.close_error = close_error
        self.offset = 0
        self.read1_calls = 0
        self.read_calls = 0
        self.limits = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True
        if self.close_error is not None:
            raise self.close_error

    def geturl(self):
        return UPSTREAM + "/responses"

    def read(self, limit):
        self.read_calls += 1
        raise AssertionError("Incremental response must use read1")

    def read1(self, limit):
        self.read1_calls += 1
        self.limits.append(limit)
        if self.offset == len(self.body):
            if self.tail is not None:
                raise self.tail
            return b""
        end = min(len(self.body), self.offset + min(limit, self.chunk_size))
        block = self.body[self.offset:end]
        self.offset = end
        if self.after_read is not None:
            self.after_read()
        return block

    def close(self):
        self.closed = True


class CountingOpener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def open(self, request, timeout):
        if request.full_url != UPSTREAM + "/responses":
            raise AssertionError("Only the fixed synthetic upstream route is allowed")
        self.requests.append(request)
        return self.response


class LegacyResponse:
    """Existing simple fake contract: read returns one body, and has no read1."""
    status = 200
    headers = {"Content-Type": "text/event-stream"}

    def __init__(self, body):
        self.body = body
        self.read_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def geturl(self):
        return UPSTREAM + "/responses"

    def read(self, limit):
        self.read_calls += 1
        if self.read_calls != 1:
            raise AssertionError("Legacy fallback must not repeat a non-consuming read")
        return self.body[:limit]

    def close(self):
        pass


@contextmanager
def chunked_upstream(body, *, hold_open):
    """Send a proper data chunk, intentionally omit the HTTP terminating 0 chunk."""
    release = threading.Event()
    sent = threading.Event()
    errors = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                self.wfile.write(f"{len(body):X}\r\n".encode("ascii") + body + b"\r\n")
                self.wfile.flush()
                sent.set()
                if hold_open:
                    release.wait(1.5)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as error:
                errors.append(type(error).__name__)
            finally:
                self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    thread.start()
    local = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    class WrappedResponse:
        def __init__(self, response):
            self.response = response

        def __getattr__(self, name):
            return getattr(self.response, name)

        def __enter__(self):
            self.response.__enter__()
            return self

        def __exit__(self, *args):
            return self.response.__exit__(*args)

        def geturl(self):
            return UPSTREAM + "/responses"

    class LoopbackOpener:
        def __init__(self):
            self.requests = []

        def open(self, request, timeout):
            if request.full_url != UPSTREAM + "/responses":
                raise AssertionError("Unexpected fixed upstream route")
            self.requests.append(request)
            # Never send even synthetic upstream auth to a real service.
            mapped = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/responses", data=request.data,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            return WrappedResponse(local.open(mapped, timeout=min(timeout, 3)))

    try:
        yield LoopbackOpener(), sent
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(2)
        if thread.is_alive() or errors:
            raise AssertionError(f"Loopback fixture cleanup failed: {errors}")


class StreamGatewayTests(unittest.TestCase):
    call = fixture.SubscriptionTests.call

    def exercise(self, response, **kwargs):
        opener = CountingOpener(response)
        with SubscriptionGateway(opener=opener, **kwargs) as gateway:
            status, body = self.call(gateway)
            report = gateway.summary()
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(report["budget_used"], 1)
        self.assertEqual(report["request_count"], 1)
        return status, body, report, report["requests"][0]

    def assert_semantic_success(self, status, report, record):
        self.assertEqual(status, 200)
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["reason"], "completed")
        self.assertIs(record["semantic_completion_observed"], True)
        self.assertIs(record["response_read_completed"], True)
        self.assertIs(record["http_eof_observed"], False)
        self.assertEqual(record["read_termination"], "response_completed")
        self.assertEqual(report["completed_requests"], 1)
        self.assertEqual(report["aggregate_usage"]["total_tokens"], 15)
        self.assertGreaterEqual(record["upstream_body_read_s"], 0)

    def assert_private_failure(self, status, body, report, record):
        self.assertGreaterEqual(status, 400)
        self.assertEqual(record["status"], "failed")
        self.assertIs(record["semantic_completion_observed"], False)
        self.assertEqual(report["completed_requests"], 0)
        self.assertIsNone(record["usage"])
        self.assertIsNone(report["aggregate_usage"])
        self.assertIn(record["read_termination"], FIXED_TERMINATIONS)
        self.assertNotIn(PRIVATE, json.dumps(report))
        self.assertNotIn(PRIVATE.encode(), body)
        self.assertGreaterEqual(record["upstream_body_read_s"], 0)

    def test_real_chunked_completed_does_not_wait_for_eof_or_zero_chunk(self):
        terminal = frame()
        for hold_open in (True, False):
            with self.subTest(hold_open=hold_open), chunked_upstream(terminal, hold_open=hold_open) as (opener, sent):
                with SubscriptionGateway(opener=opener) as gateway:
                    started = time.monotonic()
                    status, body = self.call(gateway)
                    elapsed = time.monotonic() - started
                    report = gateway.summary()
                self.assertTrue(sent.is_set())
                self.assertLess(elapsed, .8, "Logical terminal must not wait for the 1.5 s transport tail")
                self.assertEqual(len(opener.requests), 1)
                self.assertEqual(body, terminal)
                self.assert_semantic_success(status, report, report["requests"][0])

    def test_incremental_read_preserves_prefix_and_never_reads_after_completion(self):
        prefix = b": heartbeat\n\n" + frame("response.output_text.delta") + frame()
        response = StreamResponse(prefix, tail=AssertionError("No EOF read after terminal"))
        status, body, report, record = self.exercise(response)
        self.assertEqual(body, prefix)
        self.assertEqual(response.offset, len(prefix))
        self.assertEqual(response.read_calls, 0)
        self.assertTrue(all(0 < limit <= MAX_RESPONSE_BYTES + 1 for limit in response.limits))
        self.assert_semantic_success(status, report, record)

    def test_all_newlines_bom_comments_multiline_and_split_utf8(self):
        for newline in (b"\n", b"\r\n", b"\r"):
            response_doc = {"model": "gpt-6.1-sol", "status": "completed", "usage": dict(USAGE), "output": "дерево 🌳"}
            prefix = b"\xef\xbb\xbf: heartbeat" + newline * 2 + b"event: response.completed" + newline
            body = prefix + frame(newline=newline, response=response_doc, multiline=True)
            for chunk_size in (1, 7, 4096):
                with self.subTest(newline=newline, chunk_size=chunk_size):
                    response = StreamResponse(body, chunk_size=chunk_size, content_type="application/json; charset=utf-8")
                    status, reply, report, record = self.exercise(response)
                    # A CR already ends the blank line. A not-yet-read optional LF
                    # must not cause another blocking read just to preserve CRLF.
                    valid_prefixes = (body, body[:-1]) if newline == b"\r\n" else (body,)
                    self.assertIn(reply, valid_prefixes)
                    self.assert_semantic_success(status, report, record)

    def test_invalid_utf8_in_comment_or_event_header_is_rejected_privately(self):
        for prefix in (b": " + PRIVATE.encode() + b"\xff\n\n",
                       b"event: " + PRIVATE.encode() + b"\xff\n"):
            with self.subTest(field=prefix.split(b":", 1)[0]):
                status, reply, report, record = self.exercise(StreamResponse(prefix + frame()))
                self.assert_private_failure(status, reply, report, record)
                self.assertEqual(record["reason"], "response_utf8")
                self.assertNotIn(b"\xff", reply)

    def test_legacy_response_without_read1_is_read_once(self):
        response = LegacyResponse(frame())
        status, body, report, record = self.exercise(response)
        self.assertEqual(response.read_calls, 1)
        self.assertEqual(body, response.body)
        self.assert_semantic_success(status, report, record)

    def test_context_close_failure_after_completion_is_private_cleanup_only(self):
        response = StreamResponse(frame(), close_error=OSError(PRIVATE))
        status, body, report, record = self.exercise(response)
        self.assertEqual(body, frame())
        self.assert_semantic_success(status, report, record)
        self.assertEqual(record["cleanup_failure_category"], "io_error")
        self.assertNotIn(PRIVATE, json.dumps(report))

    def test_read_error_before_any_bytes_is_failed_timed_single_attempt(self):
        for error, category in ((ConnectionResetError(PRIVATE), "connection_reset"),
                                (TimeoutError(PRIVATE), "timeout")):
            with self.subTest(category=category):
                response = StreamResponse(b"", tail=error)
                status, body, report, record = self.exercise(response)
                self.assert_private_failure(status, body, report, record)
                self.assertIs(record["response_read_completed"], False)
                self.assertIs(record["http_eof_observed"], False)
                self.assertEqual(record["failure_category"], category)

    def test_incomplete_http_read_with_full_terminal_partial_preserves_known_result(self):
        class CompletePartial(StreamResponse):
            def read1(self, limit):
                self.read1_calls += 1
                raise http.client.IncompleteRead(frame(), 99)

        response = CompletePartial(b"")
        status, body, report, record = self.exercise(response)
        self.assertEqual((status, body), (200, frame()))
        self.assertEqual(record["status"], "completed")
        self.assertIs(record["semantic_completion_observed"], True)
        self.assertIs(record["response_read_completed"], False)
        self.assertIs(record["http_eof_observed"], False)
        self.assertEqual(record["read_termination"], "completed_before_http_error")
        self.assertEqual(record["tail_failure_category"], "incomplete_read")
        self.assertEqual(report["aggregate_usage"]["total_tokens"], 15)
        self.assertEqual(response.read1_calls, 1)
        self.assertGreaterEqual(record["upstream_body_read_s"], 0)

    def test_read_error_after_partial_delta_does_not_invent_usage_or_retry(self):
        delta = frame("response.output_text.delta")
        partial_payload = delta + PRIVATE.encode()
        response = StreamResponse(delta, tail=http.client.IncompleteRead(PRIVATE.encode(), 30))
        status, body, report, record = self.exercise(response)
        self.assert_private_failure(status, body, report, record)
        self.assertIs(record["response_read_completed"], False)
        self.assertEqual(record["upstream_bytes_received"], len(partial_payload))
        self.assertIs(record["http_eof_observed"], False)
        self.assertEqual(record["failure_category"], "incomplete_read")

    def test_eof_before_complete_frame_fails_even_when_terminal_json_is_valid(self):
        for body in (frame()[:-1], frame()[:-2], frame()[:-12], frame("response.output_item.done")):
            with self.subTest(length=len(body)):
                status, reply, report, record = self.exercise(StreamResponse(body))
                self.assert_private_failure(status, reply, report, record)
                self.assertIs(record["http_eof_observed"], True)
                self.assertIs(record["response_read_completed"], True)

    def test_failed_incomplete_and_error_terminal_events_never_succeed(self):
        for kind in ("response.failed", "response.incomplete", "error"):
            with self.subTest(kind=kind):
                body = frame("response.output_text.delta") + frame(kind, response={"error": {"message": PRIVATE}})
                status, reply, report, record = self.exercise(StreamResponse(body))
                self.assert_private_failure(status, reply, report, record)

    def test_complete_event_cannot_override_failed_response_state(self):
        for field in ({"status": "failed"}, {"status": "incomplete"},
                      {"error": {"message": PRIVATE}}, {"incomplete_details": {"reason": PRIVATE}}):
            with self.subTest(field=next(iter(field))):
                response_doc = {"model": "gpt-6.1-sol", "usage": dict(USAGE)} | field
                status, reply, report, record = self.exercise(StreamResponse(frame(response=response_doc)))
                self.assert_private_failure(status, reply, report, record)

    def test_complete_missing_usage_remains_unknown(self):
        response = StreamResponse(frame(response={"model": "gpt-6.1-sol", "status": "completed", "error": None, "incomplete_details": None}))
        status, _, report, record = self.exercise(response)
        self.assertEqual(status, 200)
        self.assertIs(record["semantic_completion_observed"], True)
        self.assertIsNone(record["usage"])
        self.assertIsNone(report["aggregate_usage"])

    def test_response_size_limit_remains_bounded_without_extra_attempt(self):
        body = b": " + b"x" * MAX_RESPONSE_BYTES + b"\n\n" + frame()
        response = StreamResponse(body, chunk_size=65536)
        status, reply, report, record = self.exercise(response)
        self.assert_private_failure(status, reply, report, record)
        self.assertEqual(record["reason"], "response_size_limit")
        self.assertLessEqual(response.offset, MAX_RESPONSE_BYTES + 1)

    def test_deadline_is_checked_between_chunks_without_retry(self):
        class Clock:
            now = 0.

            def __call__(self):
                return self.now

        clock = Clock()
        budget = ExecutionBudget(1, clock=clock)
        response = StreamResponse(frame(), chunk_size=1, after_read=lambda: setattr(clock, "now", 2.))
        status, body, report, record = self.exercise(response, execution_budget=budget)
        self.assertEqual(status, 408)
        self.assertEqual(record["reason"], "deadline_exhausted")
        self.assert_private_failure(status, body, report, record)
        self.assertEqual(response.read1_calls, 1)

    def test_external_cancel_is_checked_between_chunks_without_retry(self):
        cancel = threading.Event()
        response = StreamResponse(frame(), chunk_size=1, after_read=cancel.set)
        status, body, report, record = self.exercise(response, cancel=cancel)
        self.assertEqual(status, 503)
        self.assertEqual(record["reason"], "cancelled")
        self.assert_private_failure(status, body, report, record)
        self.assertEqual(response.read1_calls, 1)

    def test_attempt_cap_is_not_refunded_after_partial_failure(self):
        opener = CountingOpener(StreamResponse(frame()[:-2]))
        with SubscriptionGateway(opener=opener, budget=RequestBudget(1)) as gateway:
            self.assertGreaterEqual(self.call(gateway)[0], 400)
            self.assertEqual(self.call(gateway)[0], 429)
            report = gateway.summary()
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(report["budget_used"], 1)
        self.assertEqual(report["completed_requests"], 0)


class CompletedMetadataFramingTests(unittest.TestCase):
    def test_complete_requires_blank_line_not_just_valid_json_at_eof(self):
        for body in (frame()[:-1], frame()[:-2]):
            with self.subTest(body_length=len(body)), self.assertRaises(_Validation):
                _completed_metadata(body, "text/event-stream")

    def test_helper_accepts_bom_comments_and_each_supported_line_ending(self):
        for newline in (b"\n", b"\r\n", b"\r"):
            body = b"\xef\xbb\xbf: keepalive" + newline * 2 + frame(newline=newline, multiline=True)
            with self.subTest(newline=newline):
                self.assertEqual(_completed_metadata(body, "application/json")["usage"], USAGE)

    def test_failure_event_after_output_cannot_be_misread_as_success(self):
        for kind in ("response.failed", "response.incomplete", "error"):
            with self.subTest(kind=kind), self.assertRaises(_Validation):
                _completed_metadata(frame("response.output_text.delta") + frame(kind), "text/event-stream")

    def test_complete_requires_consistent_response_state(self):
        for extra in ({"status": "failed"}, {"error": {"message": PRIVATE}},
                      {"incomplete_details": {"reason": PRIVATE}}):
            with self.subTest(field=next(iter(extra))), self.assertRaises(_Validation):
                _completed_metadata(frame(response={"model": "gpt-6.1-sol", "usage": USAGE} | extra), "text/event-stream")


if __name__ == "__main__":
    unittest.main()
