"""Transactional coarse workflow state. No inference, SDK, or process termination."""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import time
from typing import Any, Callable
import uuid


STAGES = ('prepare', 'generate', 'verify', 'report')
STATES = ('pending', 'ready', 'running', 'paused', 'blocked', 'failed', 'cancelled', 'completed', 'succeeded')
_ID = re.compile(r'[a-f0-9]{32}')


class WorkflowError(ValueError):
    """Invalid state, exhausted budget, or unsafe local state."""


class BusyError(WorkflowError):
    """A project owner or a registered child may still be running."""


def _birth(pid: int) -> tuple[str, str | None]:
    """Return a stable process creation identity, without guessing on access errors."""
    if os.name == 'nt':
        from ctypes import wintypes
        kernel = getattr(ctypes, 'WinDLL')('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        kernel.GetProcessTimes.restype = wintypes.BOOL
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ('dead' if getattr(ctypes, 'get_last_error')() == 87 else 'unknown'), None
        try:
            created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
            code = wintypes.DWORD()
            if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                          ctypes.byref(system), ctypes.byref(user)):
                return 'unknown', None
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return 'unknown', None
            if code.value != 259:
                return 'dead', None
            return 'alive', str((created.dwHighDateTime << 32) | created.dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    if os.path.isdir('/proc'):
        try:
            fields = Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()
            if fields[0] == 'Z':
                return 'dead', None
            return 'alive', fields[19]
        except FileNotFoundError:
            return 'dead', None
        except (OSError, IndexError):
            return 'unknown', None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return 'dead', None
    except OSError:
        pass
    return 'unknown', None


def process_identity(pid: int) -> str | None:
    return _birth(pid)[1]


def process_probe(pid: int, birth: str) -> str:
    state, current = _birth(pid)
    return 'dead' if current is not None and current != birth else state


def _safe(path: Path, *, file: bool = False) -> None:
    """Reject links, Windows reparse points, and multiply linked control files."""
    for item in reversed((path, *path.parents)):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise WorkflowError('linked or reparse workflow path rejected')
        if item == path and file:
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise WorkflowError('workflow control file must be regular with one link')
        elif not stat.S_ISDIR(info.st_mode):
            raise WorkflowError('workflow ancestor must be a directory')


def _json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    except (TypeError, ValueError) as error:
        raise WorkflowError('workflow data must be finite JSON') from error


class Store:
    """One SQLite state file and one project slot shared by all workflow IDs.

    identity(pid) returns creation identity or None. probe(pid, identity) returns
    alive/dead/unknown. Tests can inject both without inspecting real processes.
    """

    def __init__(self, root: Path, *, identity: Callable[[int], str | None] = process_identity,
                 probe: Callable[[int, str], str] = process_probe, pid: int | None = None,
                 read_only: bool = False):
        self.root = Path(os.path.abspath(root))
        self.path = self.root / 'state.sqlite'
        self._identity, self._probe = identity, probe
        self._pid = os.getpid() if pid is None else pid
        self._read_only = read_only
        _safe(self.root)
        if read_only:
            _safe(self.path, file=True)
            if not self.path.is_file():
                raise WorkflowError('workflow state missing')
            return
        self.root.mkdir(parents=True, exist_ok=True)
        _safe(self.root)
        if not self.path.exists():
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
        with self._transaction() as db:
            schema = '''
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY, spec TEXT NOT NULL, state TEXT NOT NULL,
                    control TEXT, requests_used INTEGER NOT NULL DEFAULT 0,
                    time_spent_s REAL NOT NULL DEFAULT 0, time_reserved_s REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS owners (
                    slot INTEGER PRIMARY KEY CHECK(slot=1), token TEXT UNIQUE NOT NULL,
                    workflow_id TEXT NOT NULL, pid INTEGER NOT NULL, birth TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS children (
                    token TEXT NOT NULL, pid INTEGER NOT NULL, birth TEXT NOT NULL,
                    PRIMARY KEY(token,pid));
                CREATE TABLE IF NOT EXISTS launches (token TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS attempts (
                    id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, stage TEXT NOT NULL,
                    number INTEGER NOT NULL, state TEXT NOT NULL, output TEXT,
                    retryable INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(workflow_id,stage,number));
                CREATE TABLE IF NOT EXISTS requests (
                    workflow_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                    PRIMARY KEY(workflow_id,sequence));
                CREATE TABLE IF NOT EXISTS request_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL, record TEXT NOT NULL,
                    UNIQUE(workflow_id,sequence,record));
            '''
            for statement in schema.split(';'):
                if statement.strip():
                    db.execute(statement)

    @contextmanager
    def _transaction(self, *, read_only=False):
        if self._read_only and not read_only:
            raise WorkflowError('read-only workflow store cannot be modified')
        _safe(self.root)
        for suffix in ('', '-journal', '-wal', '-shm'):
            _safe(Path(str(self.path) + suffix), file=True)
        if read_only:
            # Flow uses rollback journals. Refuse WAL before SQLite can create
            # shared-memory sidecars; immutable=1 would incorrectly ignore locks.
            with self.path.open('rb') as stream:
                header = stream.read(20)
            if header[:16] != b'SQLite format 3\x00' or header[18:20] != b'\x01\x01':
                raise WorkflowError('workflow database format unsupported for read-only inspection')
        try:
            db = sqlite3.connect(self.path.as_uri() + '?mode=ro' if read_only else self.path,
                                 uri=read_only, timeout=5, isolation_level=None)
        except sqlite3.Error as error:
            if not read_only:
                raise
            raise WorkflowError('workflow database unavailable: ' + getattr(error, 'sqlite_errorname', 'SQLITE_ERROR')) from None
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA busy_timeout=5000')
            if read_only:
                db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN' if read_only else 'BEGIN IMMEDIATE')
            yield db
            db.commit()
        except sqlite3.Error as error:
            db.rollback()
            if not read_only:
                raise
            raise WorkflowError('workflow database unavailable: ' + getattr(error, 'sqlite_errorname', 'SQLITE_ERROR')) from None
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _workflow(self, db, workflow_id):
        if not isinstance(workflow_id, str) or not _ID.fullmatch(workflow_id):
            raise WorkflowError('invalid workflow ID')
        _safe(self.root / workflow_id)
        row = db.execute('SELECT * FROM workflows WHERE id=?', (workflow_id,)).fetchone()
        if row is None:
            raise WorkflowError('workflow not found')
        return row

    def _owner(self, db, token):
        row = db.execute('SELECT * FROM owners WHERE token=?', (token,)).fetchone()
        if row is None:
            raise WorkflowError('workflow ownership lost')
        if row['pid'] != self._pid or self._identity(self._pid) != row['birth']:
            raise WorkflowError('workflow owner identity changed')
        return row

    def create(self, spec: dict) -> str:
        if not isinstance(spec, dict):
            raise WorkflowError('workflow spec must be an object')
        timeout, requests = spec.get('timeout_s', 600), spec.get('max_requests', 80)
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            raise WorkflowError('timeout_s must be between one and 3600')
        if type(requests) is not int or not 1 <= requests <= 80:
            raise WorkflowError('max_requests must be between one and eighty')
        encoded = _json(dict(spec, timeout_s=timeout, max_requests=requests))
        workflow_id = uuid.uuid4().hex
        with self._transaction() as db:
            folder = self.root / workflow_id
            _safe(folder)
            folder.mkdir(exist_ok=False)
            db.execute('INSERT INTO workflows(id,spec,state) VALUES(?,?,?)',
                       (workflow_id, encoded, 'pending'))
        return workflow_id

    def get(self, workflow_id: str) -> dict:
        with self._transaction(read_only=True) as db:
            row = self._workflow(db, workflow_id)
            result = dict(row)
            result['spec'] = json.loads(row['spec'])
            attempts = [dict(r) for r in db.execute(
                'SELECT * FROM attempts WHERE workflow_id=? ORDER BY rowid', (workflow_id,))]
            for attempt in attempts:
                attempt['output'] = json.loads(attempt['output']) if attempt['output'] is not None else None
                attempt['retryable'] = bool(attempt['retryable'])
            result['attempts'] = attempts
            result['stages'] = {}
            for stage in STAGES:
                history = [a for a in attempts if a['stage'] == stage]
                last = history[-1] if history else {}
                result['stages'][stage] = {'state': last.get('state', 'pending'),
                    'attempts': len(history), 'output': last.get('output'),
                    'retryable': last.get('retryable', False)}
            result['requests'] = []
            for reserved in db.execute('SELECT sequence FROM requests WHERE workflow_id=? ORDER BY sequence',
                                       (workflow_id,)):
                sequence = reserved['sequence']
                records = [json.loads(r['record']) for r in db.execute(
                    'SELECT record FROM request_records WHERE workflow_id=? AND sequence=? ORDER BY id',
                    (workflow_id, sequence))]
                result['requests'].append({'sequence': sequence, 'records': records,
                                           'state': 'recorded' if records else 'unknown'})
            owner = db.execute('SELECT * FROM owners WHERE workflow_id=?', (workflow_id,)).fetchone()
            result['owner_pid'] = owner['pid'] if owner else None
            result['children'] = [dict(r) for r in db.execute(
                'SELECT pid,birth FROM children WHERE token=?', (owner['token'],))] if owner else []
            result['launch_pending'] = bool(owner and db.execute(
                'SELECT 1 FROM launches WHERE token=?', (owner['token'],)).fetchone())
            return result

    def list_workflows(self, *, limit=20, state=None):
        if type(limit) is not int or not 1 <= limit <= 100 or (state is not None and state not in STATES):
            raise WorkflowError('workflow list requires limit 1..100 and a known state')
        with self._transaction(read_only=True) as db:
            rows = db.execute('SELECT id,state,control,requests_used,time_spent_s,time_reserved_s '
                              'FROM workflows WHERE (? IS NULL OR state=?) ORDER BY rowid DESC LIMIT ?',
                              (state, state, limit + 1)).fetchall()
            items = []
            for row in rows[:limit]:
                if not _ID.fullmatch(row['id']):
                    raise WorkflowError('invalid stored workflow ID')
                item = dict(row)
                item['integrity'] = 'not_checked'
                items.append(item)
            return {'workflows': items, 'has_more': len(rows) > limit, 'limit': limit,
                    'state_filter': state, 'order': 'newest_created_first', 'read_only': True}

    def _recover(self, db, owner):
        if self._probe(owner['pid'], owner['birth']) != 'dead':
            raise BusyError('project owner is alive or its identity cannot be checked')
        if db.execute('SELECT 1 FROM launches WHERE token=?', (owner['token'],)).fetchone():
            raise BusyError('unresolved process launch blocks recovery')
        for child in db.execute('SELECT * FROM children WHERE token=?', (owner['token'],)):
            if self._probe(child['pid'], child['birth']) != 'dead':
                raise BusyError('registered workflow child is alive or cannot be checked')
        db.execute('UPDATE workflows SET time_spent_s=time_spent_s+time_reserved_s, '
                   'time_reserved_s=0,state=CASE WHEN control=\'cancel\' THEN \'cancelled\' ELSE \'paused\' END '
                   'WHERE id=?', (owner['workflow_id'],))
        db.execute("UPDATE attempts SET state='interrupted',retryable=1,output=? "
                   "WHERE workflow_id=? AND state='running'",
                   (_json({'reason': 'owner_lost'}), owner['workflow_id']))
        db.execute('DELETE FROM children WHERE token=?', (owner['token'],))
        db.execute('DELETE FROM owners WHERE token=?', (owner['token'],))

    def acquire(self, workflow_id: str) -> str:
        birth = self._identity(self._pid)
        if not isinstance(birth, str) or not birth:
            raise WorkflowError('cannot establish owner process creation identity')
        with self._transaction() as db:
            workflow = self._workflow(db, workflow_id)
            if workflow['state'] in ('cancelled', 'completed', 'succeeded') or workflow['control'] == 'cancel':
                raise WorkflowError('terminal workflow cannot be acquired')
            previous = db.execute('SELECT * FROM owners WHERE slot=1').fetchone()
            if previous:
                self._recover(db, previous)
            token = uuid.uuid4().hex
            db.execute('INSERT INTO owners VALUES(1,?,?,?,?)', (token, workflow_id, self._pid, birth))
            db.execute("UPDATE workflows SET state='running',control=NULL WHERE id=?", (workflow_id,))
            return token

    def owner_workflow(self, owner: str) -> str:
        with self._transaction() as db:
            return self._owner(db, owner)['workflow_id']

    def release(self, owner: str, state: str):
        if state not in ('pending', 'ready', 'running', 'paused', 'blocked', 'failed', 'cancelled', 'completed', 'succeeded'):
            raise WorkflowError('invalid workflow state')
        with self._transaction() as db:
            row = self._owner(db, owner)
            if db.execute('SELECT 1 FROM launches WHERE token=?', (owner,)).fetchone():
                raise BusyError('unresolved process launch blocks release')
            if db.execute('SELECT 1 FROM children WHERE token=?', (owner,)).fetchone():
                raise BusyError('registered child must be observed exited before releasing ownership')
            workflow = self._workflow(db, row['workflow_id'])
            if workflow['control'] == 'cancel':
                state = 'cancelled'
            elif workflow['control'] == 'pause' and state not in ('completed', 'succeeded'):
                state = 'paused'
            db.execute('UPDATE workflows SET state=?,time_spent_s=time_spent_s+time_reserved_s,'
                       'time_reserved_s=0 WHERE id=?', (state, row['workflow_id']))
            db.execute("UPDATE attempts SET state='interrupted',retryable=1 WHERE workflow_id=? AND state='running'",
                       (row['workflow_id'],))
            db.execute('DELETE FROM owners WHERE token=?', (owner,))

    def begin_stage(self, owner: str, name: str) -> str:
        if name not in STAGES:
            raise WorkflowError('invalid workflow stage')
        with self._transaction() as db:
            row = self._owner(db, owner)
            workflow = self._workflow(db, row['workflow_id'])
            if workflow['control']:
                raise WorkflowError('workflow control requested')
            history = db.execute('SELECT * FROM attempts WHERE workflow_id=? AND stage=? ORDER BY number',
                                 (row['workflow_id'], name)).fetchall()
            if history and (history[-1]['state'] == 'running' or history[-1]['state'] == 'succeeded'
                            or not history[-1]['retryable']):
                raise WorkflowError('stage is running, complete, or not retryable')
            if len(history) >= 2:
                raise WorkflowError('stage attempt limit exhausted')
            if db.execute("SELECT 1 FROM attempts WHERE workflow_id=? AND state='running'",
                          (row['workflow_id'],)).fetchone():
                raise WorkflowError('another stage is running')
            attempt = uuid.uuid4().hex
            db.execute('INSERT INTO attempts(id,workflow_id,stage,number,state) VALUES(?,?,?,?,?)',
                       (attempt, row['workflow_id'], name, len(history) + 1, 'running'))
            return attempt

    def finish_stage(self, owner: str, name: str, state: str, output: Any, retryable: bool = False):
        if name not in STAGES or state not in ('succeeded', 'failed', 'interrupted') or type(retryable) is not bool:
            raise WorkflowError('invalid stage result')
        encoded = _json(output)
        with self._transaction() as db:
            row = self._owner(db, owner)
            changed = db.execute('UPDATE attempts SET state=?,output=?,retryable=? '
                                 "WHERE workflow_id=? AND stage=? AND state='running'",
                                 (state, encoded, int(retryable and state != 'succeeded'), row['workflow_id'], name))
            if changed.rowcount != 1:
                raise WorkflowError('stage has no running attempt')

    def reserve_request(self, owner: str) -> int:
        with self._transaction() as db:
            row = self._owner(db, owner)
            workflow = self._workflow(db, row['workflow_id'])
            spec = json.loads(workflow['spec'])
            if workflow['control'] or workflow['time_spent_s'] >= spec['timeout_s']:
                raise WorkflowError('workflow stopped or active time exhausted')
            if workflow['requests_used'] >= spec['max_requests']:
                raise WorkflowError('request budget exhausted')
            sequence = workflow['requests_used'] + 1
            db.execute('INSERT INTO requests(workflow_id,sequence) VALUES(?,?)', (row['workflow_id'], sequence))
            db.execute('UPDATE workflows SET requests_used=requests_used+1 WHERE id=?', (row['workflow_id'],))
            return int(sequence)

    def record_requests(self, owner: str, records):
        records = list(records)
        encoded = [(r.get('sequence') if isinstance(r, dict) else None, _json(r)) for r in records]
        with self._transaction() as db:
            row = self._owner(db, owner)
            for sequence, record in encoded:
                if type(sequence) is not int or not db.execute(
                    'SELECT 1 FROM requests WHERE sequence=? AND workflow_id=?', (sequence, row['workflow_id'])).fetchone():
                    raise WorkflowError('request result has no owned reservation')
                db.execute('INSERT OR IGNORE INTO request_records(workflow_id,sequence,record) VALUES(?,?,?)',
                           (row['workflow_id'], sequence, record))

    def signal(self, workflow_id: str, control: str):
        if control not in ('pause', 'cancel'):
            raise WorkflowError('invalid workflow control')
        with self._transaction() as db:
            workflow = self._workflow(db, workflow_id)
            # Cancel is sticky; a later pause cannot revive a cancelled workflow.
            if workflow['control'] == 'cancel' or workflow['state'] in ('completed', 'succeeded', 'cancelled'):
                return
            db.execute('UPDATE workflows SET control=? WHERE id=?', (control, workflow_id))
            if not db.execute('SELECT 1 FROM owners WHERE workflow_id=?', (workflow_id,)).fetchone():
                db.execute('UPDATE workflows SET state=? WHERE id=?',
                           ('paused' if control == 'pause' else 'cancelled', workflow_id))

    def arm_launch(self, owner: str):
        """Persist uncertainty before spawning; unresolved launches block replay."""
        with self._transaction() as db:
            self._owner(db, owner)
            if db.execute('SELECT 1 FROM launches WHERE token=?', (owner,)).fetchone():
                raise BusyError('owner already has an unresolved process launch')
            db.execute('INSERT INTO launches(token) VALUES(?)', (owner,))

    def clear_launch(self, owner: str):
        """Resolve an intent only when the caller knows no child can remain."""
        with self._transaction() as db:
            self._owner(db, owner)
            db.execute('DELETE FROM launches WHERE token=?', (owner,))

    def register_child(self, owner: str, pid: int):
        if type(pid) is not int or pid <= 0:
            raise WorkflowError('invalid child PID')
        birth = self._identity(pid)
        if not birth:
            raise WorkflowError('cannot establish child process creation identity')
        with self._transaction() as db:
            self._owner(db, owner)
            existing = db.execute('SELECT birth FROM children WHERE token=? AND pid=?', (owner, pid)).fetchone()
            if existing and existing['birth'] != birth:
                raise WorkflowError('registered child PID changed identity')
            db.execute('INSERT OR IGNORE INTO children VALUES(?,?,?)', (owner, pid, birth))
            db.execute('DELETE FROM launches WHERE token=?', (owner,))

    def clear_child(self, owner: str, pid: int):
        with self._transaction() as db:
            self._owner(db, owner)
            db.execute('DELETE FROM children WHERE token=? AND pid=?', (owner, pid))

    def charge_active(self, owner: str, elapsed_s: float):
        """Charge measured admission work before entering an active reservation."""
        if type(elapsed_s) not in (int, float):
            raise WorkflowError('active elapsed time must be finite and nonnegative')
        try:
            elapsed = float(elapsed_s)
        except OverflowError as error:
            raise WorkflowError('active elapsed time must be finite and nonnegative') from error
        if not math.isfinite(elapsed) or elapsed < 0:
            raise WorkflowError('active elapsed time must be finite and nonnegative')
        self._time_update(owner, elapsed, None, begin=True)

    def _time_status(self, owner: str) -> dict:
        with self._transaction() as db:
            row = self._owner(db, owner)
            return dict(self._workflow(db, row['workflow_id']))

    def _time_update(self, owner: str, elapsed: float, quantum: float | None, *, begin=False) -> dict:
        with self._transaction() as db:
            row = self._owner(db, owner)
            workflow = self._workflow(db, row['workflow_id'])
            timeout = json.loads(workflow['spec'])['timeout_s']
            reserved = workflow['time_reserved_s']
            if begin and reserved:
                raise WorkflowError('owner already has an active time reservation')
            valid = elapsed == 0 or elapsed < reserved
            # A live owner can measure a scheduling overrun; retain that measured
            # time even when its lease expired. Recovery has only the persisted
            # reservation and conservatively forfeits that amount instead.
            spent = min(float(timeout), workflow['time_spent_s'] + elapsed)
            reservation = min(quantum, max(0., timeout - spent)) if quantum is not None and valid and not workflow['control'] else 0.
            db.execute('UPDATE workflows SET time_spent_s=?,time_reserved_s=? WHERE id=?',
                       (spent, reservation, row['workflow_id']))
            return {'valid': valid, 'control': workflow['control'], 'time_spent_s': spent,
                    'time_reserved_s': reservation, 'remaining_s': max(0., timeout - spent)}


class PersistentRequests:
    """RequestBudget adapter: commit each reservation before forwarding a request."""

    def __init__(self, store: Store, owner: str):
        self.store, self.owner = store, owner
        self.workflow_id = store.owner_workflow(owner)
        self.max_requests = store.get(self.workflow_id)['spec']['max_requests']

    @property
    def used(self) -> int:
        return self.store.get(self.workflow_id)['requests_used']

    def reserve(self) -> int:
        return self.store.reserve_request(self.owner)


class ActiveBudget:
    """Measure active execution with renewable, conservatively forfeited reservations."""

    def __init__(self, store: Store, owner: str, clock=time.monotonic, heartbeat_s=5, quantum_s=30):
        if (not callable(clock) or type(heartbeat_s) not in (int, float)
                or type(quantum_s) not in (int, float)
                or not math.isfinite(heartbeat_s) or not math.isfinite(quantum_s)
                or not 0 < heartbeat_s < quantum_s):
            raise WorkflowError('invalid active budget heartbeat or reservation')
        self.store, self.owner, self._clock = store, owner, clock
        self.workflow_id = store.owner_workflow(owner)
        spec = store.get(self.workflow_id)['spec']
        self.timeout_s, self.max_requests = spec['timeout_s'], spec['max_requests']
        self._heartbeat_s, self._quantum_s = heartbeat_s, quantum_s
        self.cancel_event = threading.Event()
        self._stop, self._lock = threading.Event(), threading.RLock()
        self._cancel_path: Path | None = None
        self._thread = None
        self._active = False
        self._last = self._spent = self._reserved = 0.
        self._clock_high = None
        self._requests_high = 0

    def _now(self):
        value = self._clock()
        if type(value) not in (int, float) or not math.isfinite(value):
            raise WorkflowError('active budget clock must be finite')
        self._clock_high = float(value) if self._clock_high is None else max(self._clock_high, float(value))
        return self._clock_high

    def set_cancel_path(self, path: Path):
        path = Path(os.path.abspath(path))
        try:
            path.relative_to(self.store.root / self.workflow_id)
        except ValueError as error:
            raise WorkflowError('cancel path must belong to the workflow') from error
        _safe(path, file=True)
        with self._lock:
            self._cancel_path = path
            if self.cancel_event.is_set():
                self._cancel()

    def _cancel(self):
        self.cancel_event.set()
        if self._cancel_path is not None:
            try:
                _safe(self._cancel_path, file=True)
                fd = os.open(self._cancel_path, os.O_WRONLY | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise WorkflowError('unsafe cancellation file')
                    os.write(fd, b'cancel\n')
                finally:
                    os.close(fd)
            except (OSError, WorkflowError):
                pass  # The in-process cancellation remains authoritative on write failure.

    def __enter__(self):
        with self._lock:
            if self._active or self._thread is not None:
                raise WorkflowError('active budget cannot be entered twice')
            self._last = self._now()
            try:
                state = self.store._time_update(self.owner, 0., self._quantum_s, begin=True)
            except (OSError, sqlite3.Error, ValueError):
                self._cancel()
                raise
            self._spent, self._reserved = state['time_spent_s'], state['time_reserved_s']
            self._active = True
            if state['control'] or not self._reserved:
                self._cancel()
        def refresh():
            while not self._stop.wait(self._heartbeat_s):
                with self._lock:
                    self._tick()
        self._thread = threading.Thread(target=refresh, name='workflow-budget', daemon=True)
        self._thread.start()
        return self

    def _tick(self, *, settle=False):
        if not self._active:
            return
        try:
            now = max(self._last, self._now())
            elapsed = now - self._last
            # Once expired, a heartbeat must not quietly create a new lease.
            quantum = None if settle or self.cancel_event.is_set() else self._quantum_s
            state = self.store._time_update(self.owner, elapsed, quantum)
            self._last, self._spent, self._reserved = now, state['time_spent_s'], state['time_reserved_s']
            if not state['valid'] or state['control'] or not state['remaining_s']:
                self._cancel()
        except (OSError, sqlite3.Error, ValueError):
            self._cancel()

    def remaining_s(self) -> float:
        with self._lock:
            if not self._active or self.cancel_event.is_set():
                return 0.
            try:
                elapsed = max(0., self._now() - self._last)
                current = self.store._time_status(self.owner)
                if current['control'] or elapsed >= self._reserved:
                    self._cancel()
                    return 0.
                return max(0., self.timeout_s - self._spent - elapsed)
            except (OSError, sqlite3.Error, ValueError):
                self._cancel()
                return 0.

    def total_remaining_s(self) -> float:
        return self.remaining_s()

    def snapshot(self, requests_used: int) -> dict:
        if type(requests_used) is not int or not 0 <= requests_used <= self.max_requests:
            raise WorkflowError('reserved requests outside workflow limit')
        remaining = self.remaining_s()
        with self._lock:
            self._requests_high = max(self._requests_high, requests_used)
            requests_used = self._requests_high
        elapsed = self.timeout_s - remaining
        fraction = max(elapsed / self.timeout_s, requests_used / self.max_requests)
        return {'phase': 'finalize' if fraction >= .75 else 'stabilize' if fraction >= .5 else 'build',
                'elapsed_s': elapsed, 'remaining_s': remaining, 'requests_used': requests_used,
                'requests_remaining': self.max_requests - requests_used,
                'time_fraction': elapsed / self.timeout_s, 'request_fraction': requests_used / self.max_requests}

    def __exit__(self, *_):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._heartbeat_s + 1)
        with self._lock:
            self._tick(settle=True)
            self._active = False
