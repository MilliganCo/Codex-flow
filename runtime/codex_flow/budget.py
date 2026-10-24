"""Pure monotonic task budget and conservative Responses control-message helper."""
from __future__ import annotations

import copy
import math
import re
import threading
import time
import json
import os
from pathlib import Path
import stat
import uuid
from typing import Any, Callable


def _finite(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


class ExecutionBudget:
    """Observe time and authoritative reserved attempts; never reserve requests."""

    def __init__(self, timeout_s: int, max_requests: int = 80, *,
                 clock: Callable[[], float] = time.monotonic):
        if type(timeout_s) is not int or not 1 <= timeout_s <= 3600:
            raise ValueError('timeout must be an integer between one and 3600')
        if type(max_requests) is not int or not 1 <= max_requests <= 80:
            raise ValueError('request limit must be an integer between one and eighty')
        if not callable(clock):
            raise ValueError('clock must be callable')
        self.timeout_s, self.max_requests = timeout_s, max_requests
        self._clock = clock
        self._started = self._now()
        self.deadline = self._started + timeout_s
        if not math.isfinite(self.deadline):
            raise ValueError('deadline must be finite')
        self._elapsed = 0.
        self._requests_used = 0
        self._lock = threading.Lock()

    def _now(self) -> float:
        value = self._clock()
        if not _finite(value):
            raise ValueError('clock must return a finite number')
        return float(value)

    def _elapsed_locked(self) -> float:
        elapsed = self._now() - self._started
        if not math.isfinite(elapsed):
            raise ValueError('clock elapsed must be finite')
        self._elapsed = max(self._elapsed, elapsed, 0.)
        return self._elapsed

    def remaining_s(self) -> float:
        with self._lock:
            return max(0., self.timeout_s - self._elapsed_locked())

    def snapshot(self, requests_used: int) -> dict[str, Any]:
        if type(requests_used) is not int or not 0 <= requests_used <= self.max_requests:
            raise ValueError('reserved attempts must be within the request limit')
        with self._lock:
            elapsed = self._elapsed_locked()
            # A racing caller may have read an older authoritative counter.
            self._requests_used = max(self._requests_used, requests_used)
            time_fraction = min(1., elapsed / self.timeout_s)
            request_fraction = self._requests_used / self.max_requests
            fraction = max(time_fraction, request_fraction)
            phase = 'finalize' if fraction >= .75 else 'stabilize' if fraction >= .5 else 'build'
            return {'phase': phase, 'elapsed_s': elapsed,
                    'remaining_s': max(0., self.timeout_s - elapsed),
                    'requests_used': self._requests_used,
                    'requests_remaining': self.max_requests - self._requests_used,
                    'time_fraction': time_fraction, 'request_fraction': request_fraction}


class BudgetChannel:
    """Publish owned metadata for a read-only, process-local MCP status tool."""

    def __init__(self, workspace: Path, execution_budget: ExecutionBudget, request_budget):
        from .contracts import inside
        self.root = inside(workspace, workspace / '.codex-flow/budget-status' / uuid.uuid4().hex)
        self.root.mkdir(parents=True, exist_ok=False)
        self.status_file = self.root / 'status.json'
        self.audit_dir = self.root / 'calls'
        self.audit_dir.mkdir()
        # A self-hosting task can edit the original package. Host MCP imports
        # must use a pre-launch snapshot below the model's read-only boundary.
        from importlib.resources import files
        from .contracts import PolicyError
        self.runtime_root = inside(self.root, self.root / 'runtime')
        package = inside(self.root, self.runtime_root / 'codex_flow')
        package.mkdir(parents=True)
        resources = files('codex_flow')
        for name in ('__init__.py', 'budget.py', 'contracts.py', 'budget_stdio.py'):
            raw = resources.joinpath(name).read_bytes()
            if not raw or len(raw) > 65536:
                raise PolicyError('budget server snapshot input rejected')
            with inside(package, package / name).open('xb') as stream:
                stream.write(raw)
        self.execution_budget, self.request_budget = execution_budget, request_budget
        self._stop = threading.Event()
        self._thread = None
        self.publisher_failed = False

    def publish(self):
        from .contracts import inside
        from .telemetry import utc, write_json
        try:
            inside(self.root, self.status_file)
            write_json(self.status_file, {'schema': 1, 'observed_utc': utc(),
                       'budget': self.execution_budget.snapshot(self.request_budget.used)})
        except (OSError, ValueError):
            self.publisher_failed = True

    def __enter__(self):
        self.publish()
        def refresh():
            while not self._stop.wait(1):
                self.publish()
        self._thread = threading.Thread(target=refresh, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join(timeout=3)
        if self._thread.is_alive():
            self.publisher_failed = True

    def summary(self):
        from .contracts import inside
        result = {'configured': True, 'publisher_failed': self.publisher_failed,
                  'status_calls': 0, 'successful_calls': 0, 'unavailable_calls': 0,
                  'audit_valid': True, 'phases': {}}
        try:
            inside(self.root, self.audit_dir)
            files = list(self.audit_dir.iterdir())
            if len(files) > 128:
                raise ValueError('bounded audit')
            for path in files:
                inside(self.audit_dir, path)
                info = path.lstat()
                if (re.fullmatch(r'[a-f0-9]{32}\.jsonl', path.name) is None
                        or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or info.st_size > 1024 * 1024):
                    raise ValueError('invalid audit')
                flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
                with os.fdopen(os.open(path, flags), 'r', encoding='utf-8') as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise ValueError('invalid audit')
                    for line in stream:
                        if len(line) > 1024 or result['status_calls'] >= 4096:
                            raise ValueError('bounded audit')
                        row = json.loads(line)
                        if (not isinstance(row, dict) or set(row) != {'timestamp', 'result', 'phase', 'requests_used'}
                                or not isinstance(row['timestamp'], str)
                                or row['result'] not in ('ok', 'unavailable')
                                or row['phase'] not in (None, 'build', 'stabilize', 'finalize')
                                or (row['requests_used'] is not None and
                                    (type(row['requests_used']) is not int or not 0 <= row['requests_used'] <= 80))):
                            raise ValueError('invalid audit')
                        result['status_calls'] += 1
                        key = 'successful_calls' if row['result'] == 'ok' else 'unavailable_calls'
                        result[key] += 1
                        if row['phase'] is not None:
                            result['phases'][row['phase']] = result['phases'].get(row['phase'], 0) + 1
        except (OSError, ValueError, TypeError):
            result['audit_valid'] = False
        return result


_MARKER = '[Codex Flow execution budget v1]'
_POLICIES = {
    'build': 'Build the smallest runnable acceptance slice; keep required checks and documentation current.',
    'stabilize': 'Stabilize existing acceptance; defer optional rewrites and polish; fix demonstrated defects within your assigned scope.',
    'finalize': 'Finalize required artifacts, checks and documentation; defer optional rewrites and polish.',
}


def _text_parts(value: Any) -> bool:
    if isinstance(value, str):
        return True
    if not isinstance(value, list):
        return False
    for part in value:
        if not isinstance(part, dict):
            return False
        kind = part.get('type')
        if kind in ('input_text', 'output_text'):
            valid = isinstance(part.get('text'), str)
        elif kind == 'refusal':
            valid = isinstance(part.get('refusal'), str)
        elif kind == 'input_image':
            valid = any(isinstance(part.get(key), str) for key in ('image_url', 'file_id'))
        elif kind == 'input_file':
            valid = any(isinstance(part.get(key), str) for key in ('file_id', 'file_url', 'file_data'))
        else:
            valid = False
        if not valid:
            return False
    return True


def _known_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    kind = item.get('type', 'message' if 'role' in item else None)
    if kind == 'message':
        return item.get('role') in ('user', 'assistant', 'system', 'developer') and _text_parts(item.get('content'))
    if kind == 'additional_tools':
        # Observed native CLI format and documented developer tool-loading item.
        # Definitions remain opaque and unchanged; this grants no new tool.
        return (item.get('role') == 'developer' and isinstance(item.get('id'), str)
                and isinstance(item.get('tools'), list)
                and all(isinstance(tool, dict) for tool in item['tools']))
    if kind in ('function_call', 'custom_tool_call'):
        field = 'arguments' if kind == 'function_call' else 'input'
        return all(isinstance(item.get(key), str) for key in ('call_id', 'name', field))
    if kind in ('function_call_output', 'custom_tool_call_output'):
        return isinstance(item.get('call_id'), str) and _text_parts(item.get('output'))
    if kind == 'reasoning':
        summary = item.get('summary')
        return (isinstance(item.get('id'), str) and isinstance(summary, list)
                and all(isinstance(part, dict) and part.get('type') == 'summary_text'
                        and isinstance(part.get('text'), str) for part in summary))
    if kind == 'local_shell_call':
        action = item.get('action')
        return (isinstance(item.get('call_id'), str) and isinstance(action, dict)
                and action.get('type') == 'exec' and isinstance(action.get('command'), list)
                and all(isinstance(arg, str) for arg in action['command']))
    if kind == 'local_shell_call_output':
        return all(isinstance(item.get(key), str) for key in ('id', 'output'))
    if kind == 'compaction':
        return all(isinstance(item.get(key), str) for key in ('id', 'encrypted_content'))
    return False


def _control_suffix(item: dict[str, Any]) -> bool:
    content = item.get('content')
    return (item.get('type') == 'message' and item.get('role') == 'developer'
            and isinstance(content, list) and len(content) == 1
            and isinstance(content[0], dict) and content[0].get('type') == 'input_text'
            and isinstance(content[0].get('text'), str) and content[0]['text'].startswith(_MARKER + '\n'))

def _history_prefix_item(item: Any) -> bool:
    """Preserve opaque accepted native history; never reinterpret or execute it."""
    if not isinstance(item,dict):return False
    kind=item.get('type','message' if 'role' in item else None)
    if kind in ('message','additional_tools'):
        return _known_item(item)  # Invalid known role/content cannot fall through.
    return isinstance(kind,str) and re.fullmatch(r'[a-z][a-z0-9_]{0,63}',kind) is not None

def _complete_boundary(item: Any) -> bool:
    """Do not append after an unresolved call, reasoning or opaque state item."""
    if not isinstance(item,dict):return False
    kind=item.get('type','message' if 'role' in item else None)
    return kind in ('message','function_call_output','custom_tool_call_output',
                    'local_shell_call_output','additional_tools') and _known_item(item)


def _valid_snapshot(snapshot: Any) -> bool:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('phase'), str) or snapshot['phase'] not in _POLICIES:
        return False
    if not all(_finite(snapshot.get(key)) for key in ('elapsed_s', 'remaining_s', 'time_fraction', 'request_fraction')):
        return False
    if snapshot['elapsed_s'] < 0 or not 0 <= snapshot['remaining_s'] <= 3600:
        return False
    if any(not 0 <= snapshot[key] <= 1 for key in ('time_fraction', 'request_fraction')):
        return False
    used, remaining = snapshot.get('requests_used'), snapshot.get('requests_remaining')
    if type(used) is not int or type(remaining) is not int or used < 0 or remaining < 0 or not 1 <= used + remaining <= 80:
        return False
    if not math.isclose(snapshot['request_fraction'], used / (used + remaining)):
        return False
    elapsed, seconds = snapshot['elapsed_s'], snapshot['remaining_s']
    if seconds:
        if not 1 <= elapsed + seconds <= 3600 or not math.isclose(snapshot['time_fraction'], elapsed / (elapsed + seconds)):
            return False
    elif elapsed < 1 or snapshot['time_fraction'] != 1:
        return False
    fraction = max(snapshot['time_fraction'], snapshot['request_fraction'])
    expected_phase = 'finalize' if fraction >= .75 else 'stabilize' if fraction >= .5 else 'build'
    return snapshot['phase'] == expected_phase


def append_budget_guidance(payload: dict[str, Any], snapshot: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Append one known control item, or ask the caller to forward unchanged bytes."""
    if not isinstance(payload, dict):
        return None, 'unsupported_input'
    if 'previous_response_id' in payload or 'conversation' in payload:
        return None, 'stateful_input'
    items = payload.get('input')
    if (not isinstance(items,list) or not items or not _complete_boundary(items[-1])
            or not all(_history_prefix_item(item) for item in items[:-1])):
        return None, 'unsupported_input'
    if _control_suffix(items[-1]):
        return None, 'existing_control_suffix'
    if not _valid_snapshot(snapshot):
        return None, 'unsupported_input'
    phase = snapshot['phase']
    text = (f"{_MARKER}\nphase={phase}; seconds_remaining={snapshot['remaining_s']:.1f}; "
            f"requests_remaining={snapshot['requests_remaining']}; reserved_attempts={snapshot['requests_used']}. "
            'Honor existing ownership and permissions. Read-only workers return evidence or requested proposal text; never write files or delegate. '
            'Do not start new delegation beyond the existing approved helper plan. '
            + _POLICIES[phase] + ' This phase never proves acceptance. Do not skip required tests. '
            'Stop only on verified acceptance or a concrete blocker within your assigned task.')
    result = copy.deepcopy(payload)
    result['input'].append({'type': 'message', 'role': 'developer',
                            'content': [{'type': 'input_text', 'text': text}]})
    return result, 'applied'
