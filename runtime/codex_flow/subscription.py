"""Bounded metadata observer for the official CLI's subscription transport.

The native CLI supplies authentication and enforces its sandbox. This observer
does not open credential files, modify tool payloads, retry, or select providers.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import secrets
import socket
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


class _Validation(ValueError):
    """Only source-owned fixed categories are eligible for diagnostics."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _mime(value):
    mime = value.partition(";")[0].strip().lower() if isinstance(value, str) else ""
    return mime if mime in {"text/event-stream", "application/json", "text/html", "text/plain", "application/octet-stream"} else "other"


def _encoding(value):
    encoding = value.strip().lower() if isinstance(value, str) else "other"
    return encoding if encoding in {"identity", "gzip", "br", "deflate", ""} else "other"


def _completed_metadata(body, content_type):
    if _mime(content_type) != "text/event-stream" and not body.lstrip().startswith((b"data:", b"event:")):
        raise _Validation("response_content_type")
    completed = None
    # SSE events may contain multiple data lines; output deltas are never retained.
    data = []
    def consume():
        nonlocal completed
        if not data:
            return
        raw = "\n".join(data)
        data.clear()
        if raw == "[DONE]":
            return
        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            raise _Validation("sse_event_json") from None
        if not isinstance(event, dict):
            raise _Validation("sse_event_schema")
        if event.get("type") == "response.completed":
            if completed is not None:
                raise _Validation("sse_duplicate_completion")
            response = event.get("response")
            if not isinstance(response, dict):
                raise _Validation("sse_completion_schema")
            model = response.get("model")
            if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9._:/-]{1,128}", model):
                model = None
            raw_usage = response.get("usage")
            usage = {}
            if isinstance(raw_usage, dict):
                for key in ("input_tokens", "output_tokens", "total_tokens"):
                    if _number(raw_usage.get(key)):
                        usage[key] = raw_usage[key]
                for key, field in (("input_tokens_details", "cached_tokens"),
                                   ("output_tokens_details", "reasoning_tokens")):
                    nested = raw_usage.get(key)
                    if isinstance(nested, dict) and _number(nested.get(field)):
                        usage[key] = {field: nested[field]}
            usage_status = "known" if all(k in usage for k in ("input_tokens", "output_tokens", "total_tokens")) else ("missing" if not usage else "incomplete")
            completed = {"actual_model": model, "usage": usage or None, "usage_status": usage_status}
    try:
        lines = body.decode("utf-8").splitlines()
    except UnicodeError:
        raise _Validation("response_utf8") from None
    for line in lines:
        if not line:
            consume()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    consume()
    if completed is None:
        raise _Validation("sse_incomplete")
    return completed


class SubscriptionGateway:
    def __init__(self, budget: RequestBudget | None = None, opener=None, trace=None):
        self.budget = budget if budget is not None else RequestBudget()
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
            closed = self._closed
            if not closed:
                self._responses[id(response)] = response
        if closed:
            self._abort_response(response)
            raise ValueError("gateway closed")

    def _unregister_response(self, response):
        with self._lock:
            self._responses.pop(id(response), None)

    def _begin(self, model, effort, headers):
        with self._lock:
            if self._closed:
                raise ValueError("gateway closed")
            sequence = self.budget.reserve()
        record = {"sequence": sequence, "model": model, "effort": effort,
                  "status": "pending", "actual_model": None, "usage": None,
                  "duration_s": None, "http_status": None, "reason": None,
                  "response_content_type": None, "response_encoding": None, "response_bytes": None}
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

            def respond(self, status, body, content_type="application/json"):
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

            def forward(self, inference):
                record = None
                started = time.monotonic()
                updates = {"status": "failed", "http_status": None}
                failure_stage = "request_validation"
                response = None
                reply_status, reply_body, reply_type = 502, b'{"error":{"type":"subscription_transport_rejected"}}', "application/json"
                try:
                    with owner._lock:
                        if owner._closed:
                            raise ValueError("gateway closed")
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
                        self.connection.settimeout(15)
                        data = self.rfile.read(length)
                        if len(data) != length:
                            raise ValueError("incomplete body")
                        document = json.loads(data)
                        if not isinstance(document, dict):
                            raise ValueError("invalid request object")
                        model = document.get("model")
                        reasoning = document.get("reasoning")
                        effort = reasoning.get("effort") if isinstance(reasoning, dict) else None
                        if not isinstance(model, str) or model not in ALLOWED or effort not in ALLOWED[model]:
                            raise ValueError("unapproved model effort")
                        record = owner._begin(model, effort, self.headers)
                    else:
                        with owner._lock:
                            if owner._closed:
                                raise ValueError("gateway closed")
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
                        if owner._closed:
                            raise ValueError("gateway closed")
                    failure_stage = "upstream_open_error"
                    with owner.opener.open(request, timeout=120) as response:
                        owner._register_response(response)
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
                        body = response.read(MAX_RESPONSE_BYTES + 1)
                        updates["response_bytes"] = len(body)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise _Validation("response_size_limit")
                        if inference:
                            updates.update(_completed_metadata(body, content_type))
                            updates["status"] = "completed"
                            updates["reason"] = "completed"
                            content_type = "text/event-stream"
                        reply_status, reply_body, reply_type = status, body, content_type
                except Exception as error:
                    if isinstance(error, urllib.error.HTTPError):
                        updates["http_status"] = error.code
                    updates["reason"] = (error.code if isinstance(error, _Validation) else
                                         "upstream_http_error" if isinstance(error, urllib.error.HTTPError) else failure_stage)
                    # Fixed errors only; request, upstream bodies, and exception text are never logged.
                    reply_status = 403 if isinstance(error, ValueError) else 502
                finally:
                    if response is not None:
                        owner._unregister_response(response)
                    if record is not None:
                        updates["duration_s"] = round(time.monotonic() - started, 6)
                        owner._finish(record, updates)
                self.respond(reply_status, reply_body, reply_type)
        return Handler
