"""Bounded metadata observer for the official CLI's subscription transport.

The native CLI supplies authentication and enforces its sandbox. This observer
does not open credential files, modify existing tool/history items, retry, or
select providers. Optional controller guidance is appended to compatible input.
"""
from __future__ import annotations

import copy
from collections import Counter
import hashlib
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import secrets
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


UPSTREAM = "https://chatgpt.com/backend-api/codex"
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
ALLOWED = {"gpt-6.1-sol": {"xhigh", "medium", "high"}, "gpt-6-luna": {"medium"}}


class RequestBudget:
    def __init__(self, max_requests=80):
        if type(max_requests) is not int or not 1 <= max_requests <= 80:
            raise ValueError("request budget must be between one and eighty")
        self.max_requests = max_requests
        self._used = 0
        self._lock = threading.Lock()

    def reserve(self):
        with self._lock:
            if self._used >= self.max_requests:
                raise ValueError("request budget exhausted")
            self._used += 1
            return self._used

    @property
    def used(self):
        with self._lock:
            return self._used


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _number(value):
    return type(value) is int and 0 <= value <= 2**63 - 1

def _input_metadata(document):
    """Source-owned shape labels only, never content, IDs or field values."""
    value=document.get('input')
    known={'message','reasoning','additional_tools','function_call','function_call_output','custom_tool_call',
           'custom_tool_call_output','local_shell_call','local_shell_call_output','compaction'}
    kinds=Counter()
    if isinstance(value,list):
        for item in value:
            kind=item.get('type','message' if 'role' in item else None) if isinstance(item,dict) else None
            kinds[kind if isinstance(kind,str) and kind in known else 'other']+=1
    def label(item):
        return 'null' if item is None else 'string' if isinstance(item,str) else 'array' if isinstance(item,list) else 'object' if isinstance(item,dict) else 'other'
    return {'input_type':label(value),'item_types':dict(kinds),
            'stateful_field_types':{key:label(document[key]) for key in ('previous_response_id','conversation') if key in document}}


class _Validation(ValueError):
    """Only source-owned fixed categories are eligible for diagnostics."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)

class _ControlRejected(_Validation):
    """A fixed execution-control reason, never an upstream/raw error."""


def _failure_category(error):
    """Fixed type labels only; never persist exception messages or payloads."""
    if isinstance(error, _ControlRejected): return 'control'
    if isinstance(error, _Validation): return 'validation'
    if isinstance(error, urllib.error.HTTPError): return 'http_error'
    if isinstance(error, http.client.IncompleteRead): return 'incomplete_read'
    if isinstance(error, TimeoutError): return 'timeout'
    if isinstance(error, ssl.SSLError): return 'tls_error'
    if isinstance(error, ConnectionResetError): return 'connection_reset'
    if isinstance(error, ConnectionError): return 'connection_error'
    if isinstance(error, http.client.HTTPException): return 'http_protocol_error'
    if isinstance(error, OSError): return 'io_error'
    if isinstance(error, ValueError): return 'stream_state_error'
    return 'unexpected_error'


def _transient_before_completion(error, phase):
    """Only source-known failures, before any buffered response is delivered."""
    if phase not in ('upstream_open', 'body_read') or isinstance(error, _Validation):
        return False
    if isinstance(error, urllib.error.HTTPError):
        return error.code in (500, 502, 503, 504)
    if isinstance(error, urllib.error.URLError):
        error = error.reason
    return isinstance(error, (TimeoutError, ConnectionResetError, ConnectionAbortedError,
                              http.client.IncompleteRead))


def _stateless_retry_input(document):
    return (document.get('store') is False and isinstance(document.get('input'), list)
            and not any(key in document for key in ('previous_response_id', 'conversation', 'background')))


def _mime(value):
    mime = value.partition(";")[0].strip().lower() if isinstance(value, str) else ""
    return mime if mime in {"text/event-stream", "application/json", "text/html", "text/plain", "application/octet-stream"} else "other"


def _encoding(value):
    encoding = value.strip().lower() if isinstance(value, str) else "other"
    return encoding if encoding in {"identity", "gzip", "br", "deflate", ""} else "other"


class _ResponseFrames:
    """Incremental SSE framing; only a complete terminal frame proves success."""
    def __init__(self) -> None:
        self.pending = b''
        self.data: list[bytes] = []
        self.offset = 0
        self.completed: dict[str, Any] | None = None
        self.completed_end: int | None = None
        self.swallow_lf = False

    def feed(self, chunk: bytes, *, eof=False) -> None:
        self.pending += chunk
        if self.swallow_lf and self.pending:
            if self.pending.startswith(b'\n'):
                self.pending = self.pending[1:]
                self.offset += 1
            self.swallow_lf = False
        while self.pending:
            ends = [n for n in (self.pending.find(b'\r'), self.pending.find(b'\n')) if n >= 0]
            if not ends:
                break
            end = min(ends)
            size = 2 if self.pending[end:end+2] == b'\r\n' else 1
            if self.pending[end:] == b'\r':
                self.swallow_lf = True
            line, self.pending = self.pending[:end], self.pending[end+size:]
            if self.offset == 0:
                line = line.removeprefix(b'\xef\xbb\xbf')
            self.offset += end + size
            if line == b'':
                self.consume()
            elif line.startswith(b'data:'):
                self.data.append(line[5:].removeprefix(b' '))

    def consume(self) -> None:
        if not self.data:
            return
        raw = b'\n'.join(self.data)
        self.data.clear()
        if raw == b'[DONE]':
            return
        try:
            event = json.loads(raw.decode('utf-8'))
        except UnicodeError:
            raise _Validation('response_utf8') from None
        except (ValueError, TypeError):
            raise _Validation('sse_event_json') from None
        if not isinstance(event, dict):
            raise _Validation('sse_event_schema')
        kind = event.get('type')
        if kind in ('response.failed', 'response.incomplete', 'error'):
            raise _Validation({'response.failed':'sse_response_failed',
                               'response.incomplete':'sse_response_incomplete', 'error':'sse_error'}[kind])
        if kind != 'response.completed':
            return
        if self.completed is not None:
            raise _Validation('sse_duplicate_completion')
        response = event.get('response')
        if not isinstance(response, dict):
            raise _Validation('sse_completion_schema')
        if (response.get('status', 'completed') != 'completed' or response.get('error') is not None
                or response.get('incomplete_details') is not None):
            raise _Validation('sse_completion_state')
        model = response.get('model')
        if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9._:/-]{1,128}', model):
            model = None
        raw_usage = response.get('usage')
        usage: dict[str, Any] = {}
        if isinstance(raw_usage, dict):
            for key in ('input_tokens', 'output_tokens', 'total_tokens'):
                if _number(raw_usage.get(key)):
                    usage[key] = raw_usage[key]
            for key, field in (('input_tokens_details', 'cached_tokens'),
                               ('output_tokens_details', 'reasoning_tokens')):
                nested = raw_usage.get(key)
                if isinstance(nested, dict) and _number(nested.get(field)):
                    usage[key] = {field: nested[field]}
        usage_status = 'known' if all(k in usage for k in ('input_tokens','output_tokens','total_tokens')) else ('missing' if not usage else 'incomplete')
        self.completed = {'actual_model':model, 'usage':usage or None, 'usage_status':usage_status}
        self.completed_end = self.offset


def _completed_metadata(body, content_type):
    try:
        body.decode('utf-8-sig')  # Comments/event fields must also be valid UTF-8.
    except UnicodeError:
        raise _Validation('response_utf8') from None
    sniff = body.removeprefix(b'\xef\xbb\xbf').lstrip()
    if _mime(content_type) != 'text/event-stream' and not sniff.startswith((b'data:', b'event:', b':')):
        raise _Validation('response_content_type')
    frames = _ResponseFrames()
    frames.feed(body, eof=True)
    if frames.completed is None:
        raise _Validation('sse_incomplete')
    return frames.completed


def _read_inference(response, content_type, check_control, updates):
    """Buffer bounded bytes through model completion, never through an HTTP tail."""
    body = bytearray()
    frames = _ResponseFrames()
    incremental = callable(getattr(response, 'read1', None))
    read = response.read1 if incremental else response.read
    updates.update(semantic_completion_observed=False, http_eof_observed=False,
                   response_read_completed=False, read_termination=None)
    while True:
        check_control()
        updates['response_read_completed'] = False
        try:
            chunk = read(min(16384, MAX_RESPONSE_BYTES + 1 - len(body)) if incremental else MAX_RESPONSE_BYTES + 1)
        except http.client.IncompleteRead as error:
            # The HTTP framing may break after a complete SSE terminal. Inspect
            # only already-received bounded bytes; never retry or invent usage.
            chunk = error.partial
            if not isinstance(chunk, bytes) or len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                raise
            body.extend(chunk)
            updates['upstream_bytes_received'] = len(body)
            frames.feed(chunk)
            if frames.completed is None:
                raise
            updates['tail_failure_category'] = 'incomplete_read'
            updates['read_termination'] = 'completed_before_http_error'
        else:
            updates['response_read_completed'] = True
            body.extend(chunk)
            updates['upstream_bytes_received'] = len(body)
            if len(body) > MAX_RESPONSE_BYTES:
                updates['response_bytes'] = len(body)
                raise _Validation('response_size_limit')
            frames.feed(chunk, eof=not chunk)
            if not chunk and frames.completed is None:
                updates.update(http_eof_observed=True, read_termination='http_eof', response_bytes=len(body))
                return bytes(body)  # The caller still requires valid completion.
        check_control()
        if frames.completed is not None:
            assert frames.completed_end is not None
            body = body[:frames.completed_end]
            _completed_metadata(bytes(body), content_type)
            updates.update(semantic_completion_observed=True, response_bytes=len(body))
            if updates['read_termination'] is None:
                updates['read_termination'] = 'response_completed'
            return bytes(body)
        if not incremental:
            updates.update(read_termination='buffered_fallback', response_bytes=len(body))
            return bytes(body)


class SubscriptionGateway:
    def __init__(self, budget: RequestBudget | None = None, opener=None, trace=None,
                 *, execution_budget=None, guidance=False, cancel=None, transient_recovery=False):
        if type(guidance) is not bool:raise ValueError('guidance must be boolean')
        if type(transient_recovery) is not bool:raise ValueError('transient_recovery must be boolean')
        if transient_recovery and guidance:raise ValueError('recovery requires unchanged inference inputs')
        self.budget = budget if budget is not None else RequestBudget()
        self.execution_budget = execution_budget
        self.guidance = guidance
        self.transient_recovery = transient_recovery
        self.external_cancel = cancel
        self._cancelled = threading.Event()
        self._stop_reason = 'cancelled'
        self._control_rejections:Counter[str] = Counter()
        self.opener = opener if opener is not None else urllib.request.build_opener(_NoRedirect())
        self.trace = trace
        self.nonce = secrets.token_urlsafe(32)
        self._lock = threading.Lock()
        self._records:list[dict[str,Any]] = []
        self._responses:dict[int,Any] = {}
        self._active = self._peak = self._models_gets = 0
        self._started = False
        self._closed = False
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={"poll_interval": .05}, daemon=True)

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self._server.server_port}/backend-api/codex"

    def __enter__(self):
        if self._started or self._closed:
            raise RuntimeError("gateway context cannot be reused")
        self._started = True
        self._thread.start()
        return self

    def __exit__(self, *args):
        with self._lock:
            already_closed = self._closed
            self._closed = True
            responses = list(self._responses.values())
        # Abort owned upstream streams before waiting on the listener. Closing a
        # buffered file alone may wait for its reader lock; socket shutdown first
        # wakes urllib's blocked read immediately.
        for response in responses:
            self._abort_response(response)
        if self._started and not already_closed:
            self._server.shutdown()
            self._thread.join(5)
        self._server.server_close()

    def cancel(self,reason='cancelled'):
        """Stop new requests and wake registered readers; never signal processes."""
        if reason not in ('cancelled','deadline_exhausted'):raise ValueError('invalid stop reason')
        self._stop_reason=reason
        self._cancelled.set()
        with self._lock:responses=list(self._responses.values())
        for response in responses:self._abort_response(response)

    def _check_control(self):
        if self._cancelled.is_set():raise _ControlRejected(self._stop_reason)
        if self.external_cancel is not None and self.external_cancel.is_set():
            raise _ControlRejected('cancelled')
        if self.execution_budget is not None and self.execution_budget.remaining_s()<=0:
            raise _ControlRejected('deadline_exhausted')
        if self._closed:raise _ControlRejected('cancelled')

    def _open_timeout(self):
        self._check_control()
        remaining=self.execution_budget.remaining_s() if self.execution_budget is not None else 120
        if remaining<=0:raise _ControlRejected('deadline_exhausted')
        return min(120,remaining)

    @staticmethod
    def _abort_response(response):
        fp = getattr(response, "fp", None)
        raw = getattr(fp, "raw", None)
        sock = getattr(raw, "_sock", None) or getattr(fp, "_sock", None)
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except (OSError, AttributeError):
                pass
        try:
            response.close()
        except Exception:
            pass

    def _register_response(self, response):
        with self._lock:
            closed = self._closed or self._cancelled.is_set()
            if not closed:
                self._responses[id(response)] = response
        if closed:
            self._abort_response(response)
            raise _ControlRejected(self._stop_reason)

    def _unregister_response(self, response):
        with self._lock:
            self._responses.pop(id(response), None)

    def _begin(self, model, effort, headers):
        with self._lock:
            self._check_control()
            try:sequence = self.budget.reserve()
            except ValueError:raise _ControlRejected('request_budget_exhausted') from None
        record = {"sequence": sequence, "model": model, "effort": effort,
                  "status": "pending", "actual_model": None, "usage": None,
                  "semantic_completion_observed": False,
                  "duration_s": None, "http_status": None, "reason": None,
                  "response_content_type": None, "response_encoding": None, "response_bytes": None}
        if self.execution_budget is not None:
            record['execution_budget']=self.execution_budget.snapshot(self.budget.used)
        record['guidance_status']='disabled'
        record['upstream_open_s']=None
        record['upstream_body_read_s']=None
        record['response_buffered']=True
        record['response_read_completed']=None
        for header, field in (("Session_id", "session_sha256"),
                              ("Conversation_id", "conversation_sha256"),
                              ("X-Request-ID", "request_sha256")):
            value = headers.get(header)
            if value:
                record[field] = hashlib.sha256(value.encode("utf-8")).hexdigest()
        with self._lock:
            self._active += 1
            self._peak = max(self._peak, self._active)
            self._records.append(record)
        return record

    def _finish(self, record, updates):
        with self._lock:
            record.update(updates)
            self._active -= 1
            safe = copy.deepcopy(record)
        if self.trace is not None:
            try:
                self.trace.emit("subscription.request", safe)
            except Exception:
                pass  # Diagnostics cannot change execution or leak raw failures.

    def summary(self):
        with self._lock:
            records = copy.deepcopy(self._records)
            active, peak, gets = self._active, self._peak, self._models_gets
            rejections=dict(self._control_rejections)
        aggregate = None
        if records and not active and all(r["status"] == "completed" and r["usage"] is not None
                                         and all(k in r["usage"] for k in ("input_tokens", "output_tokens", "total_tokens"))
                                         for r in records):
            aggregate = {key: sum(r["usage"][key] for r in records)
                         for key in ("input_tokens", "output_tokens", "total_tokens")}
            for nested, key in (("input_tokens_details", "cached_tokens"),
                                ("output_tokens_details", "reasoning_tokens")):
                aggregate[key] = (sum(r["usage"][nested][key] for r in records)
                                  if all(key in r["usage"].get(nested, {}) for r in records) else None)
        return {"request_count": len(records), "completed_requests": sum(r["status"] == "completed" for r in records),
                "active_requests": active, "peak_concurrent_requests": peak, "models_gets": gets,
                "requests": records, "aggregate_usage": aggregate,
                "actual_models": sorted({r["actual_model"] for r in records if r["actual_model"]}),
                "budget_used": self.budget.used, "budget_max_requests": self.budget.max_requests,
                "control_rejections":rejections,
                "budget_guidance":{"enabled":self.guidance,
                    "applied_requests":sum(r.get('guidance_status')=='applied' for r in records),
                    "statuses":dict(Counter(r.get('guidance_status','disabled') for r in records))},
                "transient_recovery":{"enabled":self.transient_recovery,
                    "retry_eligible_failures":sum(r.get('retry_eligible') is True for r in records),
                    "gateway_replays":0,
                    "scope":"native HTTP retry only; every new upstream attempt reserves the shared budget; no exactly-once backend claim"},
                "initial_header_open_cancellation":"bounded by remaining timeout; no response handle exists until open returns",
                "agent_count": None, "agent_count_limitation": "requests do not identify agents"}

    def _handler(self):
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.forward(False)

            def do_POST(self):
                self.forward(True)

            def discard_rejected_body(self, consumed):
                """Avoid Windows RST on normal rejected POSTs without a slow-body wait.

                No parsing, forwarding or credential use happens here. Ambiguous
                framing and oversized declarations are closed without draining.
                """
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or self.headers.get("Transfer-Encoding"):
                    return
                try:
                    length = int(lengths[0])
                except ValueError:
                    return
                if not 0 <= length <= MAX_REQUEST_BYTES:
                    return
                remaining = max(0, length - consumed)
                deadline = time.monotonic() + .25
                previous_timeout = self.connection.gettimeout()
                try:
                    while remaining:
                        available = deadline - time.monotonic()
                        if available <= 0:
                            break
                        self.connection.settimeout(min(.05, available))
                        block = self.rfile.read1(min(16384, remaining))
                        if not block:
                            break
                        remaining -= len(block)
                except OSError:
                    pass  # Body timeout/disconnect cannot authorize forwarding.
                finally:
                    try:
                        self.connection.settimeout(previous_timeout)
                    except OSError:
                        pass  # The client may have already closed this socket.

            def respond(self, status, body, content_type="application/json"):
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

            def forward(self, inference):
                record = None
                started = time.monotonic()
                updates = {"status": "failed", "http_status": None}
                failure_stage = "request_validation"
                failure_phase = "request_validation"
                response = None
                request_bytes_read = 0
                reply_status, reply_body, reply_type = 502, b'{"error":{"type":"subscription_transport_rejected"}}', "application/json"
                try:
                    with owner._lock:
                        owner._check_control()
                    if not hmac.compare_digest(self.headers.get("X-Codex-Flow-Token", ""), owner.nonce):
                        raise ValueError("invalid capability")
                    route = urllib.parse.urlsplit(self.path)
                    expected = "/backend-api/codex/" + ("responses" if inference else "models")
                    if route.path != expected or route.netloc or route.scheme or route.fragment:
                        raise ValueError("unsupported route")
                    if inference and route.query:
                        raise ValueError("inference query forbidden")
                    if self.headers.get("Upgrade") or self.headers.get("Transfer-Encoding"):
                        raise ValueError("unsupported transport")
                    auth = self.headers.get("Authorization", "")
                    if not auth.startswith("Bearer ") or not re.fullmatch(r"[A-Za-z0-9._~+/-]+={0,2}", auth[7:]) or auth[7:].lower().startswith("sk-"):
                        raise ValueError("subscription auth required")
                    data = None
                    if inference:
                        if self.headers.get("Content-Encoding", "identity") not in ("identity", ""):
                            raise ValueError("compressed request forbidden")
                        lengths = self.headers.get_all("Content-Length", [])
                        if len(lengths) != 1:
                            raise ValueError("invalid body length")
                        length = int(lengths[0])
                        if not 0 < length <= MAX_REQUEST_BYTES:
                            raise ValueError("body limit")
                        self.connection.settimeout(min(15,owner._open_timeout()))
                        data = self.rfile.read(length)
                        request_bytes_read = len(data)
                        if len(data) != length:
                            raise ValueError("incomplete body")
                        document = json.loads(data)
                        if not isinstance(document, dict):
                            raise ValueError("invalid request object")
                        # Native HTTP retries can also follow a local disconnect.
                        # Therefore every admitted recovery-mode POST must be
                        # stateless, not just those later returning a 503.
                        if owner.transient_recovery and not _stateless_retry_input(document):
                            raise ValueError("stateful recovery input forbidden")
                        model = document.get("model")
                        reasoning = document.get("reasoning")
                        effort = reasoning.get("effort") if isinstance(reasoning, dict) else None
                        if not isinstance(model, str) or model not in ALLOWED or effort not in ALLOWED[model]:
                            raise ValueError("unapproved model effort")
                        record = owner._begin(model, effort, self.headers)
                        if owner.transient_recovery:
                            record['payload_fingerprint'] = hmac.new(owner.nonce.encode('ascii'), data,
                                                                      hashlib.sha256).hexdigest()
                            record['retry_eligible'] = False
                        if owner.guidance:record['input_schema']=_input_metadata(document)
                        if owner.guidance and owner.execution_budget is not None:
                            from .budget import append_budget_guidance
                            try:
                                updated,reason=append_budget_guidance(document,record['execution_budget'])
                                if updated is not None:
                                    encoded=json.dumps(updated,ensure_ascii=False,separators=(',',':')).encode('utf-8')
                                    if len(encoded)<=MAX_REQUEST_BYTES:data=encoded
                                    else:reason='size_limit'
                            except (TypeError,ValueError,UnicodeError,OverflowError):
                                reason='serialization_incompatible'
                            record['guidance_status']=reason
                    else:
                        with owner._lock:
                            owner._check_control()
                            owner._models_gets += 1
                    # Never forward a local nonce, arbitrary client headers, or proxy auth.
                    headers = {name: self.headers[name] for name in
                               ("Authorization", "ChatGPT-Account-ID", "OpenAI-Beta", "User-Agent", "Originator",
                                "Session_id", "Conversation_id", "Version") if self.headers.get(name)}
                    headers["Accept-Encoding"] = "identity"
                    if inference:
                        headers.update({"Content-Type": "application/json", "Accept": "text/event-stream"})
                    upstream = UPSTREAM + ("/responses" if inference else "/models")
                    if not inference and route.query:
                        upstream += "?" + route.query
                    request = urllib.request.Request(upstream, data=data, headers=headers,
                                                     method="POST" if inference else "GET")
                    with owner._lock:
                        owner._check_control()
                    failure_stage = "upstream_open_error"
                    failure_phase = "upstream_open"
                    opened=time.monotonic()
                    with owner.opener.open(request, timeout=owner._open_timeout()) as response:
                        updates['upstream_open_s']=round(time.monotonic()-opened,6)
                        owner._register_response(response)
                        owner._check_control()
                        status = response.status
                        updates["http_status"] = status
                        final_url = getattr(response, "geturl", lambda: upstream)()
                        if final_url != upstream or not 200 <= status < 300:
                            raise _Validation("upstream_route_status")
                        content_type = response.headers.get("Content-Type", "application/json")
                        encoding = response.headers.get("Content-Encoding", "identity")
                        updates.update(response_content_type=_mime(content_type), response_encoding=_encoding(encoding))
                        if encoding not in ("identity", ""):
                            raise _Validation("response_encoding")
                        failure_stage = "upstream_read_error"
                        failure_phase = "body_read"
                        read_started=time.monotonic()
                        updates['response_read_completed']=False
                        try:
                            if inference:
                                body = _read_inference(response, content_type, owner._check_control, updates)
                            else:
                                body = response.read(MAX_RESPONSE_BYTES + 1)
                                updates['response_read_completed']=True
                        finally:
                            updates['upstream_body_read_s']=round(time.monotonic()-read_started,6)
                        owner._check_control()
                        updates["response_bytes"] = len(body)
                        failure_phase = "response_validation"
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise _Validation("response_size_limit")
                        if inference:
                            updates.update(_completed_metadata(body, content_type))
                            content_type = "text/event-stream"
                        failure_phase = "response_close"
                    # A context-manager close failure must not count as delivered
                    # completion or forward a response body under an error status.
                    if inference:
                        updates["status"] = "completed"
                        updates["reason"] = "completed"
                    reply_status, reply_body, reply_type = status, body, content_type
                except Exception as error:
                    if not isinstance(error,_ControlRejected):
                        try:owner._check_control()
                        except _ControlRejected as stopped:error=stopped
                    terminal_cleanup = (inference and failure_phase == 'response_close'
                                        and updates.get('semantic_completion_observed') is True
                                        and not isinstance(error, _Validation))
                    if terminal_cleanup:
                        updates.update(status='completed', reason='completed',
                                       cleanup_failure_category=_failure_category(error))
                        reply_status, reply_body, reply_type = status, body, content_type
                    elif inference:
                        self.discard_rejected_body(request_bytes_read)
                    if not terminal_cleanup:
                        if failure_phase == 'body_read':
                            updates['read_termination'] = 'control' if isinstance(error, _ControlRejected) else 'read_error'
                        if isinstance(error, urllib.error.HTTPError):
                            updates["http_status"] = error.code
                        updates["reason"] = (error.code if isinstance(error, _Validation) else
                                             "upstream_http_error" if isinstance(error, urllib.error.HTTPError) else failure_stage)
                        updates['status']='failed'
                        updates['failure_phase']=failure_phase
                        updates['failure_category']=_failure_category(error)
                        if isinstance(error,http.client.IncompleteRead) and isinstance(error.partial,bytes):
                            updates['partial_response_bytes']=len(error.partial)
                        # Fixed errors only; no exception text, partial content or credentials.
                        reply_status = 403 if isinstance(error, ValueError) else 502
                        if owner.transient_recovery:
                            retryable = inference and record is not None and _transient_before_completion(error, failure_phase)
                            updates['retry_eligible'] = retryable
                            # Do not pass an upstream 401 into native auth-refresh
                            # recovery. Denial stays nonretryable; original status
                            # remains in metadata without exposing its body.
                            reply_status = 503 if retryable else (403 if isinstance(error, urllib.error.HTTPError)
                                                                 and error.code in (401, 403) else 400)
                        reply_body=b'{"error":{"type":"subscription_transport_rejected"}}'
                        if isinstance(error,_ControlRejected):
                            with owner._lock:owner._control_rejections[error.code]+=1
                            reply_status=(400 if owner.transient_recovery else
                                          {'request_budget_exhausted':429,'deadline_exhausted':408,'cancelled':503}[error.code])
                            reply_body=json.dumps({'error':{'type':error.code}}).encode('ascii')
                finally:
                    if response is not None:
                        owner._unregister_response(response)
                    if record is not None:
                        updates["duration_s"] = round(time.monotonic() - started, 6)
                        owner._finish(record, updates)
                self.respond(reply_status, reply_body, reply_type)
        return Handler
