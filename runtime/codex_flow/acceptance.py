"""Opt-in, owner-selected acceptance checks in the official command sandbox.

Checker code is data on the host. It is frozen before generation and executed only
by `codex sandbox`; successful receipts attest the selected checks, not all quality.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import subprocess
import sys
import threading
import time
import uuid

from .contracts import PolicyError, inside
from .telemetry import Trace, write_json

MAX_REPORT = 65536
MAX_OUTPUT = 1048576
MAX_FILES = 2048
MAX_INPUT_BYTES = 67108864
RESERVED = {'.git', '.codex-flow', '.home', '.tmp'}


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PolicyError('duplicate acceptance JSON key')
        value[key] = item
    return value


def _nonfinite(_):
    raise PolicyError('nonfinite acceptance JSON')


def _json(raw):
    try:
        return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_object, parse_constant=_nonfinite)
    except RecursionError:
        raise PolicyError('acceptance JSON nesting limit exceeded') from None


def _file(path: Path, limit: int) -> bytes:
    inside(path.parent, path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
        raise PolicyError('acceptance file boundary refused')
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise PolicyError('acceptance file too large')
    return value


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise PolicyError('acceptance paths must be relative POSIX paths')
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ('.', '..') or p in RESERVED for p in path.parts) or not path.parts:
        raise PolicyError('acceptance input path refused')
    return path.as_posix()


@dataclass(frozen=True)
class Contract:
    path: Path
    checker: Path
    raw: bytes
    checker_raw: bytes
    inputs: tuple[str, ...]
    min_checks: int
    timeout_s: int

    def summary(self):
        return {'configured': True, 'contract_sha256': _sha(self.raw),
                'checker_sha256': _sha(self.checker_raw), 'min_checks': self.min_checks,
                'timeout_s': self.timeout_s, 'input_roots': list(self.inputs)}


def load_contract(path: Path) -> Contract:
    path = inside(path.absolute().parent, path.absolute())
    raw = _file(path, MAX_REPORT)
    data = _json(raw)
    fields = {'schema', 'checker', 'inputs', 'min_checks', 'timeout_s'}
    if not isinstance(data, dict) or set(data) != fields or type(data['schema']) is not int or data['schema'] != 1:
        raise PolicyError('invalid acceptance contract schema')
    for name, maximum in (('min_checks', 1000), ('timeout_s', 300)):
        if type(data[name]) is not int or not 1 <= data[name] <= maximum:
            raise PolicyError('invalid acceptance bound: ' + name)
    names = data['inputs']
    if not isinstance(names, list) or not 1 <= len(names) <= 64:
        raise PolicyError('acceptance inputs required')
    inputs = tuple(_relative(name) for name in names)
    if len(set(inputs)) != len(inputs):
        raise PolicyError('duplicate acceptance input')
    checker_name = _relative(data['checker'])
    checker = inside(path.parent, path.parent / checker_name)
    if checker.suffix != '.py':
        raise PolicyError('acceptance checker must be a self-contained Python file')
    return Contract(path, checker, raw, _file(checker, 262144), inputs, data['min_checks'], data['timeout_s'])


@dataclass(frozen=True)
class Prepared:
    root: Path
    contract: Contract

    def unchanged(self):
        c = self.contract
        return (_file(c.path, MAX_REPORT) == c.raw and _file(c.checker, 262144) == c.checker_raw
                and _file(self.root / 'contract.json', MAX_REPORT) == c.raw
                and _file(self.root / 'checker.py', 262144) == c.checker_raw)


def prepare(workspace: Path, contract: Contract) -> Prepared:
    folder = inside(workspace, workspace / '.codex-flow/acceptance' / uuid.uuid4().hex)
    folder.mkdir(parents=True, exist_ok=False)
    for name, raw in (('contract.json', contract.raw), ('checker.py', contract.checker_raw)):
        with (folder / name).open('xb') as stream:
            stream.write(raw)
    result = Prepared(folder, contract)
    if not result.unchanged():
        raise PolicyError('acceptance inputs changed during preparation')
    return result


def inventory(workspace: Path, names: tuple[str, ...]):
    result: dict[str, str] = {}
    total = visited = 0
    for name in names:
        root = inside(workspace, workspace / name)
        todo = [root]
        while todo:
            visited += 1
            if visited > MAX_FILES * 2:
                raise PolicyError('acceptance inventory too large')
            path = inside(workspace, todo.pop())
            info = path.stat()
            if stat.S_ISDIR(info.st_mode):
                for child in path.iterdir():
                    if len(todo) + len(result) >= MAX_FILES:
                        raise PolicyError('acceptance inventory too large')
                    todo.append(child)
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise PolicyError('acceptance input boundary refused')
            key = path.relative_to(workspace).as_posix()
            if key in result:
                continue
            total += info.st_size
            if total > MAX_INPUT_BYTES or len(result) >= MAX_FILES:
                raise PolicyError('acceptance inventory too large')
            result[key] = _sha(_file(path, MAX_INPUT_BYTES))
    if not result:
        raise PolicyError('acceptance input inventory is empty')
    return result


def protected_paths(workspace: Path, paths):
    result = []
    for path in paths:
        target = inside(path.absolute().parent, path.absolute())
        if not target.exists() or target == workspace or target in workspace.parents:
            raise PolicyError('protected paths must exist outside the workspace ancestry')
        if target not in result:
            result.append(target)
    return tuple(result)


def sandbox_command(exe, workspace, prepared, scratch, report, nonce, denied):
    rules = {str(workspace).replace('\\', '/'): 'read',
             str(prepared.root).replace('\\', '/'): 'read', str(scratch).replace('\\', '/'): 'write'}
    for path in (*denied, workspace / '.codex-flow/native-state', Path.home() / '.codex', Path.home() / '.agents'):
        if path.exists():
            rules[str(path.resolve()).replace('\\', '/')] = 'deny'
    entries = ','.join(json.dumps(k) + '=' + json.dumps(v) for k, v in rules.items())
    profile = 'permissions.flow_acceptance={extends=":workspace",filesystem={' + entries + '},network={enabled=false}}'
    return [exe, 'sandbox', '-P', 'flow_acceptance', '--cd', str(scratch), '-c', profile,
            '-c', 'windows.sandbox="elevated"', '--', str(Path(sys.executable).resolve()), '-I', '-B',
            str(prepared.root / 'checker.py'), '--workspace', str(workspace), '--report', str(report), '--nonce', nonce]


def sandbox_environment(scratch):
    excluded = ('API_KEY', 'TOKEN', 'SECRET', 'AUTH', 'CODEX_', 'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP')
    env = {k: v for k, v in os.environ.items() if not any(word in k.upper() for word in excluded)}
    home, temp = scratch / 'home', scratch / 'tmp'
    home.mkdir()
    temp.mkdir()
    env.update(HOME=str(home), USERPROFILE=str(home), TEMP=str(temp), TMP=str(temp),
               XDG_CACHE_HOME=str(home / '.cache'), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    return env


def require_backend():
    if os.name != 'nt':
        raise PolicyError('acceptance requires the reviewed Windows Codex sandbox')


def capture(command, env, scratch, deadline, cancel_file, control_file):
    from .native import terminate_tree
    proc = subprocess.Popen(command, cwd=scratch, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.DEVNULL, shell=False, start_new_session=os.name != 'nt')
    try:
        write_json(control_file, {'pid': proc.pid, 'status': 'verifying'})
    except BaseException:
        terminate_tree(proc)
        raise
    lock = threading.Lock()
    captures = {}
    overflow = threading.Event()
    def drain(name, stream):
        digest, size, failed = hashlib.sha256(), 0, False
        try:
            while chunk := stream.read(65536):
                digest.update(chunk)
                size += len(chunk)
                if size > MAX_OUTPUT:
                    overflow.set()
        except (OSError, ValueError):
            failed = True
        finally:
            with lock:
                captures[name] = {'bytes': size, 'sha256': digest.hexdigest(), 'error': failed}
    threads = [threading.Thread(target=drain, args=(name, stream), daemon=True)
               for name, stream in (('stdout', proc.stdout), ('stderr', proc.stderr))]
    for thread in threads:
        thread.start()
    reason = None
    try:
        while proc.poll() is None:
            if cancel_file.exists():
                reason = 'cancelled'
            elif time.monotonic() >= deadline:
                reason = 'timed_out'
            elif overflow.is_set():
                reason = 'output_limit'
            if reason:
                terminate_tree(proc)
                break
            time.sleep(.05)
    except BaseException:
        terminate_tree(proc)
        raise
    for thread in threads:
        thread.join(timeout=min(.5, max(0., deadline - time.monotonic())))
    with lock:
        complete = (set(captures) == {'stdout', 'stderr'} and not any(t.is_alive() for t in threads)
                    and not any(row['error'] for row in captures.values()))
        return {'exit_code': proc.poll(), 'stop_reason': reason, 'capture_complete': complete,
                'sdk_root_exit_observed': proc.poll() is not None, 'capture': dict(captures),
                'output_limit_exceeded': overflow.is_set()}


def assess_report(raw, nonce, minimum):
    data = _json(raw)
    if (not isinstance(data, dict) or set(data) != {'schema', 'nonce', 'checks'}
            or type(data['schema']) is not int or data['schema'] != 1 or data['nonce'] != nonce):
        raise PolicyError('invalid acceptance report binding')
    checks = data['checks']
    if not isinstance(checks, list) or not minimum <= len(checks) <= 1000:
        raise PolicyError('insufficient acceptance checks')
    seen = set()
    for row in checks:
        if (not isinstance(row, dict) or set(row) != {'id', 'status'} or not isinstance(row['id'], str)
                or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}', row['id']) or row['id'] in seen
                or row['status'] not in ('passed', 'failed', 'skipped')):
            raise PolicyError('invalid acceptance check')
        seen.add(row['id'])
    return {'checks_run': len(checks), 'checks_passed': sum(r['status'] == 'passed' for r in checks),
            'checks_failed': sum(r['status'] == 'failed' for r in checks),
            'checks_skipped': sum(r['status'] == 'skipped' for r in checks)}


def verify(exe, workspace: Path, prepared: Prepared, run_dir: Path, budget, denied=()):
    if (run_dir / 'acceptance.json').exists() or (run_dir / 'acceptance.json').is_symlink():
        raise PolicyError('existing acceptance receipt must be preserved')
    started = time.monotonic()
    contract = prepared.contract
    result = {'schema': 1, 'status': 'blocked', 'accepted': False, **contract.summary(),
              'model_calls': 0, 'network_enabled': False, 'checker_executed_on_host': False,
              'scope': 'owner-selected checks and declared input inventory',
              'descendant_termination': 'best_effort_not_independently_attested'}
    trace = Trace(run_dir / 'events.jsonl', run_dir.name, task_id='acceptance')
    trace.emit('acceptance.start', contract.summary(), actor='acceptance', model=None)
    try:
        if budget.remaining_s() <= 0:
            result['reason'] = 'deadline_exhausted'
            return result
        if (run_dir / 'cancel.request').exists():
            result.update(status='cancelled', reason='cancelled')
            return result
        if not prepared.unchanged():
            raise PolicyError('acceptance contract or checker changed')
        before = inventory(workspace, contract.inputs)
        scratch = inside(prepared.root, prepared.root / 'scratch')
        scratch.mkdir(exist_ok=False)
        report = scratch / 'report.json'
        nonce = secrets.token_hex(16)
        command = sandbox_command(exe, workspace, prepared, scratch, report, nonce, denied)
        deadline = time.monotonic() + min(contract.timeout_s, budget.remaining_s())
        if (run_dir / 'cancel.request').exists():
            result.update(status='cancelled', reason='cancelled')
            return result
        if budget.remaining_s() <= 0:
            result['reason'] = 'deadline_exhausted'
            return result
        require_backend()
        execution = capture(command, sandbox_environment(scratch), scratch, deadline,
                            run_dir / 'cancel.request', run_dir / 'control.json')
        result.update(execution)
        after = inventory(workspace, contract.inputs)
        inventory_path = inside(run_dir, run_dir / 'acceptance-inputs.json')
        if inventory_path.exists():
            raise PolicyError('existing acceptance inventory must be preserved')
        write_json(inventory_path, {'schema': 1, 'before': before, 'after': after})
        result.update(input_files_checked=len(before), input_inventory_sha256=_sha(_file(inventory_path, 2097152)),
                      inputs_unchanged=before == after, checker_unchanged=prepared.unchanged())
        if not result['inputs_unchanged'] or not result['checker_unchanged']:
            raise PolicyError('acceptance input or checker drift')
        if execution['stop_reason']:
            result.update(status=execution['stop_reason'], reason=execution['stop_reason'])
            return result
        if budget.remaining_s() <= 0 or time.monotonic() > deadline:
            result.update(status='timed_out', reason='deadline_exhausted')
            return result
        if (execution['exit_code'] != 0 or not execution['capture_complete']
                or not execution['sdk_root_exit_observed'] or execution['output_limit_exceeded']):
            result.update(status='failed', reason='sandbox_execution_not_successful')
            return result
        raw = _file(report, MAX_REPORT)
        result.update(assess_report(raw, nonce, contract.min_checks), report_sha256=_sha(raw))
        if (run_dir / 'cancel.request').exists():
            result.update(status='cancelled', reason='cancelled')
            return result
        if budget.remaining_s() <= 0 or time.monotonic() > deadline:
            result.update(status='timed_out', reason='deadline_exhausted')
            return result
        passed = result['checks_failed'] == 0 and result['checks_skipped'] == 0
        result.update(status='passed' if passed else 'failed', accepted=passed,
                      reason='all_selected_checks_passed' if passed else 'checks_failed_or_skipped')
    except KeyboardInterrupt:
        result.update(status='cancelled', accepted=False, reason='cancelled')
    except (OSError, ValueError, TypeError):
        result.update(status='blocked', accepted=False, reason='acceptance_evidence_invalid')
    finally:
        result['wall_clock_s'] = round(time.monotonic() - started, 3)
        trace.emit('acceptance.end', {k: result.get(k) for k in ('status', 'accepted', 'reason', 'checks_run',
                   'checks_failed', 'checks_skipped', 'input_inventory_sha256', 'report_sha256', 'wall_clock_s')},
                   actor='acceptance', model=None)
        write_json(run_dir / 'acceptance.json', result)
    return result


def apply_result(result, acceptance):
    result['native_status'] = result['status']
    result['acceptance'] = acceptance or {'status': 'not_configured', 'accepted': False}
    result['accepted'] = bool(acceptance and acceptance.get('accepted') is True
                              and acceptance.get('status') == 'passed'
                              and result['native_status'] == 'completed_unverified')
    if result['native_status'] == 'completed_unverified' and acceptance:
        result['status'] = 'completed_verified' if result['accepted'] else 'verification_failed'
    return result
