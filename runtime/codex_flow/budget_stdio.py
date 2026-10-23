"""Fixed-path, readonly MCP stdio budget status; no model/provider integration."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Any, Callable, TextIO
import uuid

from .budget import _valid_snapshot
from .contracts import PolicyError, inside

MAX_LINE = 65536
MAX_STATUS = 16384
BUDGET_KEYS = {'phase', 'elapsed_s', 'remaining_s', 'requests_used', 'requests_remaining', 'time_fraction', 'request_fraction'}
UTC = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)')
POLICY = {
    'build': 'Build the smallest runnable acceptance slice; maintain required checks and documentation.',
    'stabilize': 'Stabilize existing acceptance; defer optional rewrites and polish; fix demonstrated defects within your scope.',
    'finalize': 'Finalize required artifacts, checks and documentation; defer optional rewrites and polish.',
}
TOOL = {'name': 'status', 'description': 'Read current controller execution budget and ownership-preserving phase guidance.',
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
        'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False}}


def unavailable(reason: str) -> dict[str, Any]:
    return {'status': 'unavailable', 'reason': reason, 'budget': None}


def reject_constant(_value: str) -> Any:
    raise ValueError('Nonfinite JSON constant')


def ordinary(info) -> bool:
    return stat.S_ISREG(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400 and info.st_nlink == 1


class BudgetStdio:
    def __init__(self, root: Path, status_file: Path, audit_dir: Path, *, clock: Callable[[], float] = time.time):
        if not status_file.is_absolute() or not audit_dir.is_absolute():
            raise PolicyError('Fixed status and audit paths must be absolute')
        root = inside(root, root)
        if not root.is_dir():
            raise PolicyError('Workspace must already exist')
        self.base = inside(root, root / '.codex-flow')
        self.status_file = inside(self.base, status_file)
        self.audit_dir = inside(self.base, audit_dir)
        if not self.audit_dir.is_dir():
            raise PolicyError('Controller must precreate the audit directory')
        self.audit_file = self.audit_dir / (uuid.uuid4().hex + '.jsonl')
        self._audit_created = False
        self.clock = clock

    def _read(self) -> dict[str, Any]:
        try:
            inside(self.base, self.status_file)
            if not ordinary(self.status_file.lstat()):
                return unavailable('status_path_rejected')
            flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
            with os.fdopen(os.open(self.status_file, flags), 'rb') as stream:
                if not ordinary(os.fstat(stream.fileno())):
                    return unavailable('status_path_rejected')
                raw = stream.read(MAX_STATUS + 1)
            inside(self.base, self.status_file)
        except PolicyError:
            return unavailable('status_path_rejected')
        except FileNotFoundError:
            return unavailable('status_missing')
        except OSError:
            return unavailable('status_unreadable')
        if len(raw) > MAX_STATUS:
            return unavailable('status_oversize')
        try:
            value = json.loads(raw.decode('utf-8'), parse_constant=reject_constant)
            if (not isinstance(value, dict) or set(value) != {'schema', 'observed_utc', 'budget'}
                    or type(value['schema']) is not int or value['schema'] != 1
                    or not isinstance(value['observed_utc'], str) or not UTC.fullmatch(value['observed_utc'])
                    or not isinstance(value['budget'], dict) or set(value['budget']) != BUDGET_KEYS
                    or not _valid_snapshot(value['budget'])):
                return unavailable('status_invalid')
            observed = datetime.fromisoformat(value['observed_utc'].replace('Z', '+00:00')).timestamp()
            now = self.clock()
            if type(now) not in (int, float) or not math.isfinite(now):
                return unavailable('clock_invalid')
            age = now - observed
        except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
            return unavailable('status_invalid')
        if age < -1.:
            return unavailable('status_future')
        if age > 10.:
            return unavailable('status_stale')
        budget = value['budget']
        guidance = ('Honor existing ownership and permissions. Read-only workers return evidence only; never write files or delegate. '
                    'Do not start delegation beyond the existing approved helper plan. ' + POLICY[budget['phase']]
                    + ' This phase never proves acceptance. Do not skip required tests. Stop only on verified acceptance or a concrete blocker within your assigned task.')
        return {'status': 'ok', 'budget': budget, 'sample_age_s': round(max(0., age), 6), 'guidance': guidance}

    def _audit(self, result: dict[str, Any]) -> None:
        inside(self.base, self.audit_dir)
        inside(self.audit_dir, self.audit_file)
        budget = result.get('budget') or {}
        record = {'timestamp': datetime.now(timezone.utc).isoformat(), 'result': result['status'],
                  'phase': budget.get('phase'), 'requests_used': budget.get('requests_used')}
        raw = (json.dumps(record, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
        if len(raw) > 512:
            raise ValueError('Audit record limit')
        flags = os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
        flags |= os.O_APPEND if self._audit_created else os.O_CREAT | os.O_EXCL
        with os.fdopen(os.open(self.audit_file, flags, 0o600), 'wb') as stream:
            if not ordinary(os.fstat(stream.fileno())):
                raise ValueError('Audit file rejected')
            stream.write(raw)
        self._audit_created = True

    def status(self) -> dict[str, Any]:
        result = self._read()
        try:
            self._audit(result)
        except (OSError, ValueError):
            return unavailable('audit_unavailable')
        return result

    @staticmethod
    def error(identity: Any, code: int, message: str) -> dict[str, Any]:
        return {'jsonrpc': '2.0', 'id': identity, 'error': {'code': code, 'message': message}}

    def handle(self, request: Any) -> dict[str, Any] | None:
        if not isinstance(request, dict) or request.get('jsonrpc') != '2.0':
            return self.error(None, -32600, 'Invalid Request')
        if 'id' not in request:
            return None  # Notifications never read status or write audit records.
        identity = request['id']
        if identity is not None and (type(identity) not in (str, int) or isinstance(identity, str) and len(identity) > 256):
            return self.error(None, -32600, 'Invalid Request')
        method = request.get('method')
        if not isinstance(method, str):
            return self.error(None, -32600, 'Invalid Request')
        if method not in {'initialize', 'ping', 'tools/list', 'tools/call'}:
            return self.error(identity, -32601, 'Method not found')
        params = request.get('params', {})
        if not isinstance(params, dict):
            return self.error(identity, -32602, 'Invalid params')
        result: dict[str, Any]
        if method == 'initialize':
            version = params.get('protocolVersion')
            try:
                if (set(params) - {'protocolVersion', 'capabilities', 'clientInfo', '_meta'}
                        or any(key in params and not isinstance(params[key], dict) for key in ('capabilities', 'clientInfo', '_meta'))
                        or not isinstance(version, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', version)):
                    raise ValueError('Protocol date required')
                date.fromisoformat(version)
            except ValueError:
                return self.error(identity, -32602, 'Invalid params')
            result = {'protocolVersion': version, 'capabilities': {'tools': {'listChanged': False}},
                      'serverInfo': {'name': 'codex-flow-budget', 'version': '1'}}
        elif method in {'ping', 'tools/list'}:
            allowed = {'_meta', 'cursor'} if method == 'tools/list' else {'_meta'}
            if (set(params) - allowed or '_meta' in params and not isinstance(params['_meta'], dict)
                    or 'cursor' in params and params['cursor'] is not None):
                return self.error(identity, -32602, 'Invalid params')
            result = {} if method == 'ping' else {'tools': [TOOL]}
        else:
            if (set(params) - {'name', 'arguments', '_meta'} or params.get('name') != 'status'
                    or type(params.get('arguments')) is not dict or params['arguments'] != {}
                    or '_meta' in params and not isinstance(params['_meta'], dict)):
                return self.error(identity, -32602, 'Invalid params')
            status = self.status()
            result = {'content': [{'type': 'text', 'text': json.dumps(status, allow_nan=False)}], 'isError': status['status'] != 'ok'}
        return {'jsonrpc': '2.0', 'id': identity, 'result': result}

    def serve(self, source: TextIO, output: TextIO) -> None:
        while True:
            line = source.readline(MAX_LINE + 1)
            if not line:
                return
            oversized = len(line) > MAX_LINE
            try:
                if oversized:
                    raise ValueError('Frame limit')
                response = self.handle(json.loads(line, parse_constant=reject_constant))
            except (ValueError, RecursionError):
                response = self.error(None, -32700, 'Parse error')
            if response is not None:
                output.write(json.dumps(response, allow_nan=False) + '\n')
                output.flush()
            if oversized:
                return  # Do not reinterpret an oversized frame's tail as another request.


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('Invalid server configuration')


def main(argv=None, *, stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    parser = Parser(add_help=False)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--status-file', type=Path, required=True)
    parser.add_argument('--audit-dir', type=Path, required=True)
    try:
        args = parser.parse_args(argv)
        BudgetStdio(args.root, args.status_file, args.audit_dir).serve(
            sys.stdin if stdin is None else stdin, sys.stdout if stdout is None else stdout)
    except (OSError, ValueError):
        return 2  # No raw paths, input bodies or exceptions on stdout/stderr.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
