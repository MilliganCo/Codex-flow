"""Project-local prepare/generate/verify/report orchestration with durable state.

Only the native backend performs inference. Tests may inject a labelled fixture
backend through Python; no public CLI option selects or loads backend code.
"""
from __future__ import annotations
from dataclasses import asdict, replace
import hashlib
from importlib.resources import files
import json
import math
import os
from pathlib import Path
import subprocess
import time
from typing import Any

from . import acceptance, execution_contract, workflow_files as snapshots
from .config import Config
from .contracts import PolicyError, inside
from .telemetry import Trace
from .workflow_store import Store, ActiveBudget, PersistentRequests, WorkflowError, BusyError, STAGES


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(path, expected=None):
    raw = acceptance._file(path, 67108864)
    if expected is not None and digest(raw) != expected:
        raise PolicyError('workflow artifact hash changed')
    return acceptance._json(raw)


def _write(root, name, value):
    path = inside(root, root / name)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8') + b'\n'
    with path.open('xb') as stream:
        stream.write(raw)
    return digest(raw)


def _put(root, name, raw):
    path = inside(root, root / name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def _init_git(workspace):
    empty = inside(workspace, workspace / '.codex-flow/empty-git-template')
    empty.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
    process = subprocess.run(['git', '-c', 'init.templateDir=' + str(empty), '-c', 'core.hooksPath=' + str(empty),
                              '-c', 'core.fsmonitor=false', 'init', '--quiet', str(workspace)],
                             env=env, capture_output=True, timeout=15, check=False)
    if process.returncode:
        raise PolicyError('workflow Git scaffold failed')


class NativeBackend:
    kind = 'native'

    def fingerprint(self, explicit=None):
        acceptance.require_backend()
        from .native import executable
        exe = str(Path(executable(explicit)).absolute())
        checked = subprocess.run([exe, 'sandbox', '--help'], capture_output=True, timeout=15, check=False)
        if checked.returncode:
            raise PolicyError('official command sandbox unavailable')
        package = files('codex_flow')
        runtime = {p.name: digest(p.read_bytes()) for p in package.iterdir() if p.name.endswith('.py')}
        return {'executable': exe, 'executable_sha256': digest(Path(exe).read_bytes()),
                'runtime': runtime, 'backend_kind': self.kind}

    def generate(self, workspace, cfg, task, run_dir, requests, budget, execution, on_process_start):
        from .native import run
        from .cli import BASE_INSTRUCTIONS
        frozen = execution_contract.freeze(execution) if execution else None
        result = run(self.exe, workspace, replace(cfg, timeout_s=max(1, math.ceil(budget.total_remaining_s()))),
                     task, run_dir, parallel=execution is not None,
                     instructions=execution.instructions() if execution else BASE_INSTRUCTIONS,
                     request_budget=requests, execution_budget=budget, cancel=budget.cancel_event,
                     executor_mode=execution is not None, on_process_start=on_process_start)
        if execution:
            result['execution_contract'] = execution_contract.observe(execution, frozen, result,
                                      budget=budget, cancel_file=run_dir / 'cancel.request')
        return result

    def verify(self, workspace, contract, run_dir, budget, on_process_start):
        prepared = acceptance.prepare(workspace, contract)
        return acceptance.verify(self.exe, workspace, prepared, run_dir, budget,
                                 on_process_start=on_process_start)


class ProcessGuard:
    def __init__(self, store, owner):
        self.store, self.owner = store, owner

    def before_spawn(self):
        self.store.arm_launch(self.owner)

    def __call__(self, pid):
        self.store.register_child(self.owner, pid)

    def finished(self, pid):
        self.store.clear_child(self.owner, pid)
        self.store.clear_launch(self.owner)

    def spawn_missing(self):
        self.store.clear_launch(self.owner)


class Engine:
    def __init__(self, repo: Path, *, backend=None, checkpoint=None):
        self.repo = inside(repo.absolute(), repo.absolute())
        self.root = inside(self.repo, self.repo / '.codex-flow/workflows')
        self.backend = backend if backend is not None else NativeBackend()
        self.checkpoint = checkpoint
        self._store = None

    @property
    def store(self):
        if self._store is None:
            self._store = Store(self.root)
        return self._store

    def _base(self, workflow_id):
        if not isinstance(workflow_id, str) or len(workflow_id) != 32 or any(c not in '0123456789abcdef' for c in workflow_id):
            raise PolicyError('invalid workflow id')
        return inside(self.root, self.root / workflow_id)

    def inspect(self, cfg, task, acceptance_file, execution_file=None):
        if not isinstance(task, str) or not task.strip() or len(task.encode('utf-8')) > 1048576:
            raise PolicyError('workflow task required and bounded to one MiB')
        contract = acceptance.load_contract(acceptance_file)
        execution = execution_contract.load(execution_file, self.repo) if execution_file else None
        if execution:
            execution_contract.admit(execution, contract.inputs)
        source = snapshots.project_inventory(self.repo)
        return {'dry_run': True, 'stages': list(STAGES), 'external_calls': 0, 'model_calls': 0,
                'active_time_s': cfg.timeout_s, 'max_model_requests': cfg.max_model_requests,
                'seed_content_sha256': snapshots.content_hash(source), 'source_files': len(source['files']),
                'omitted': source.get('omitted', []), 'acceptance': contract.summary(),
                'execution_contract': execution.summary() if execution else {'configured': False}}

    def start(self, cfg, task, acceptance_file, execution_file=None, *, exe=None, enable=False, dry_run=False):
        admission_started = time.monotonic()
        preview = self.inspect(cfg, task, acceptance_file, execution_file)
        if dry_run:
            return preview
        if not (cfg.enabled or enable):
            raise PolicyError('workflow disabled; use --enable or project config')
        contract = acceptance.load_contract(acceptance_file)
        execution = execution_contract.load(execution_file, self.repo) if execution_file else None
        fingerprint = self.backend.fingerprint(exe)
        self.backend.exe = fingerprint.get('executable', exe)
        checker_name = acceptance._relative(json.loads(contract.raw)['checker'])
        config = asdict(cfg)
        spec = {'schema': 1, 'timeout_s': cfg.timeout_s, 'max_requests': cfg.max_model_requests,
                'config': config, 'fingerprint': fingerprint, 'backend_kind': self.backend.kind,
                'task_sha256': digest(task.encode('utf-8')), 'acceptance_sha256': digest(contract.raw),
                'checker_sha256': digest(contract.checker_raw), 'checker_name': checker_name,
                'seed_content_sha256': preview['seed_content_sha256'],
                'execution_sha256': digest(execution.raw) if execution else None}
        workflow_id = self.store.create(spec)
        base = self._base(workflow_id)
        _put(base, 'inputs/task.txt', task.encode('utf-8'))
        _put(base, 'inputs/acceptance.json', contract.raw)
        _put(base, 'inputs/' + checker_name, contract.checker_raw)
        if execution:
            _put(base, 'inputs/execution.json', execution.raw)
        _write(base, 'spec.json', spec)
        try:
            return self._execute(workflow_id, initial_active_s=time.monotonic() - admission_started)
        except BusyError:
            result = self.status(workflow_id)
            result['reason'] = ('unresolved_launch' if result['launch_pending'] else
                                'owned_process_still_registered' if result['owned_children'] else 'project_busy')
            return result

    def resume(self, workflow_id, *, enable=False, exe=None):
        admission_started = time.monotonic()
        current = self.status(workflow_id)
        if current.get('integrity') == 'failed':
            raise PolicyError('cached workflow artifacts changed')
        cfg = Config(**self.store.get(workflow_id)['spec']['config'])
        if current['state'] != 'completed' and not (cfg.enabled or enable):
            raise PolicyError('workflow resume requires --enable or frozen enabled config')
        spec = self.store.get(workflow_id)['spec']
        if self.backend.kind != spec['backend_kind']:
            raise PolicyError('workflow backend changed')
        fingerprint = self.backend.fingerprint(exe or spec['fingerprint'].get('executable'))
        if fingerprint != spec['fingerprint']:
            raise PolicyError('workflow runtime or executable changed')
        self.backend.exe = fingerprint.get('executable', exe)
        if current['state'] == 'completed':
            self._check_cached(workflow_id, self.store.get(workflow_id))
            return self.status(workflow_id)
        return self._execute(workflow_id, initial_active_s=time.monotonic() - admission_started)

    def status(self, workflow_id):
        self._base(workflow_id)
        if not (self.root / 'state.sqlite').is_file():
            raise PolicyError('workflow state missing')
        row = self.store.get(workflow_id)
        report = row['stages']['report']['output'] or {}
        integrity = 'not_complete'
        source_changed = None
        if row['state'] == 'completed':
            try:
                self._check_cached(workflow_id, row)
                integrity = 'verified'
                prepared = row['stages']['prepare']['output']
                seed_manifest = _read(self._base(workflow_id) / prepared['manifest'], prepared['manifest_sha256'])
                try:
                    source_changed = snapshots.content_hash(snapshots.project_inventory(self.repo)) != snapshots.content_hash(seed_manifest)
                except (OSError, ValueError):
                    source_changed = None
            except (OSError, ValueError, TypeError):
                integrity = 'failed'
        return {'workflow_id': workflow_id, 'state': row['state'], 'control': row['control'],
                'stages': row['stages'], 'requests_used': row['requests_used'],
                'active_time_used_s': row['time_spent_s'], 'active_time_reserved_s': row['time_reserved_s'],
                'requests_remaining': row['spec']['max_requests'] - row['requests_used'],
                'active_time_remaining_s': max(0., row['spec']['timeout_s'] - row['time_spent_s'] - row['time_reserved_s']),
                'accepted': row['state'] == 'completed' and integrity == 'verified', 'integrity': integrity, 'report': report,
                'source_changed_since_start': source_changed,
                'owner_pid': row['owner_pid'], 'launch_pending': row.get('launch_pending', False),
                'owned_children': row['children'],
                'backend_kind': row['spec']['backend_kind'], 'source_project_updated': False}

    def signal(self, workflow_id, action):
        if self.status(workflow_id)['state'] == 'completed':
            raise PolicyError('completed workflow is immutable')
        self.store.signal(workflow_id, action)
        return self.status(workflow_id)

    def _inputs(self, workflow_id, row):
        base, spec = self._base(workflow_id), row['spec']
        if _read(base / 'spec.json') != spec:
            raise PolicyError('workflow spec changed')
        task_raw = acceptance._file(base / 'inputs/task.txt', 1048576)
        if digest(task_raw) != spec['task_sha256']:
            raise PolicyError('workflow task changed')
        contract = acceptance.load_contract(base / 'inputs/acceptance.json')
        if digest(contract.raw) != spec['acceptance_sha256'] or digest(contract.checker_raw) != spec['checker_sha256']:
            raise PolicyError('workflow acceptance inputs changed')
        execution_path = base / 'inputs/execution.json'
        if spec['execution_sha256'] is not None and digest(acceptance._file(execution_path, 65536)) != spec['execution_sha256']:
            raise PolicyError('workflow execution contract changed')
        return task_raw.decode('utf-8'), contract, execution_path if spec['execution_sha256'] else None

    def _check_cached(self, workflow_id, row):
        self._inputs(workflow_id, row)
        base = self._base(workflow_id)
        for name in STAGES:
            stage = row['stages'][name]
            if stage['state'] != 'succeeded':
                continue
            out = stage['output']
            for path, expected in out.get('bound_files', {}).items():
                if digest(acceptance._file(inside(base, base / path), 67108864)) != expected:
                    raise PolicyError('cached workflow receipt changed')
            if name in ('prepare', 'generate'):
                manifest = _read(inside(base, base / out['manifest']), out['manifest_sha256'])
                snapshots.assert_snapshot(inside(base, base / out['tree']), manifest)
            if name == 'report':
                manifest = _read(inside(base, base / out['bundle'] / 'manifest.json'))
                snapshots.assert_snapshot(inside(base, base / out['bundle'] / 'files'), manifest)

    def _execute(self, workflow_id, initial_active_s=0.):
        owner = self.store.acquire(workflow_id)
        final_state = 'failed'
        base = self._base(workflow_id)
        trace = Trace(base / 'events.jsonl', workflow_id, task_id='workflow')
        try:
            self.store.charge_active(owner, initial_active_s)
            with ActiveBudget(self.store, owner) as budget:
                self._check_cached(workflow_id, self.store.get(workflow_id))
                requests = PersistentRequests(self.store, owner)
                for stage in STAGES:
                    row = self.store.get(workflow_id)
                    if row['control']:
                        final_state = 'paused' if row['control'] == 'pause' else 'cancelled'
                        break
                    saved = row['stages'][stage]
                    if saved['state'] == 'succeeded':
                        trace.emit('workflow.stage.reused', {'stage': stage}, model=None)
                        continue
                    if saved['state'] == 'failed' and not saved['retryable']:
                        raise WorkflowError('unchanged rejected stage cannot be retried')
                    if budget.remaining_s() <= 0:
                        raise WorkflowError('workflow active time exhausted')
                    attempt = self.store.begin_stage(owner, stage)
                    number = self.store.get(workflow_id)['stages'][stage]['attempts']
                    directory = inside(base, base / 'a' / stage / str(number))
                    directory.mkdir(parents=True, exist_ok=False)
                    trace.emit('workflow.stage.start', {'stage': stage, 'attempt': attempt}, model=None)
                    try:
                        output = self._stage(stage, workflow_id, owner, directory, budget, requests)
                        control = self.store.get(workflow_id)['control']
                        if control or budget.remaining_s() <= 0:
                            output = {**output, 'reason': control or 'active_time_exhausted'}
                            self.store.finish_stage(owner, stage, 'interrupted', output, retryable=True)
                            final_state = 'paused' if control == 'pause' else 'cancelled' if control == 'cancel' else 'failed'
                            break
                        ok = output.get('passed') is True
                        self.store.finish_stage(owner, stage, 'succeeded' if ok else 'failed', output,
                                                retryable=output.get('retryable') is True)
                        trace.emit('workflow.stage.end', {'stage': stage, 'passed': ok}, model=None)
                        if not ok:
                            break
                        if self.checkpoint is not None:
                            self.checkpoint(stage, workflow_id)
                    except (OSError, ValueError, TypeError):
                        self.store.finish_stage(owner, stage, 'failed', {'reason': 'stage_execution_error'}, retryable=True)
                        break
                else:
                    final_state = 'completed'
        finally:
            if final_state == 'completed':
                settled = self.store.get(workflow_id)
                if (settled['time_reserved_s'] != 0 or settled['time_spent_s'] >= settled['spec']['timeout_s']):
                    final_state = 'failed'
            self.store.release(owner, final_state)
        return self.status(workflow_id)

    def _stage(self, stage, workflow_id, owner, directory, budget, requests):
        base, row = self._base(workflow_id), self.store.get(workflow_id)
        task, contract, execution_path = self._inputs(workflow_id, row)
        spec = row['spec']
        relative = lambda p: p.relative_to(base).as_posix()
        bind = lambda p: {relative(p): digest(p.read_bytes())}
        if stage == 'prepare':
            seed = directory / 'seed'
            manifest = snapshots.seed_project(self.repo, seed)
            path = directory / 'manifest.json'
            value = _write(directory, 'manifest.json', manifest)
            unchanged = snapshots.content_hash(manifest) == spec['seed_content_sha256']
            return {'passed': unchanged, 'retryable': False,
                    'reason': 'source_snapshot_ready' if unchanged else 'source_changed_before_snapshot',
                    'tree': relative(seed), 'manifest': relative(path), 'manifest_sha256': value,
                    'bound_files': bind(path), 'seed_content_sha256': snapshots.content_hash(manifest)}
        prepared = row['stages']['prepare']['output']
        seed = inside(base, base / prepared['tree'])
        seed_manifest = _read(inside(base, base / prepared['manifest']), prepared['manifest_sha256'])
        if stage == 'generate':
            workspace = directory / 'w'
            snapshots.materialize(seed, seed_manifest, workspace)
            _init_git(workspace)
            execution = execution_contract.load(execution_path, workspace) if execution_path else None
            cfg = Config(**spec['config'])
            run_dir = workspace / '.codex-flow/runs/generate'
            budget.set_cancel_path(run_dir / 'cancel.request')
            child = ProcessGuard(self.store, owner)
            metrics = self.backend.generate(workspace, cfg, task, run_dir, requests, budget, execution, child)
            if type(metrics.get('native_exit_code')) is int:
                for child_row in self.store.get(workflow_id)['children']:
                    self.store.clear_child(owner, child_row['pid'])
            self.store.record_requests(owner, metrics.get('subscription', {}).get('requests', []))
            metrics_hash = _write(directory, 'generation.json', metrics)
            passed = metrics.get('status') == 'completed_unverified' and (
                not execution or metrics.get('execution_contract', {}).get('verified') is True)
            out = {'passed': passed, 'retryable': not passed, 'metrics': relative(directory / 'generation.json'),
                   'bound_files': {relative(directory / 'generation.json'): metrics_hash}, 'backend_kind': self.backend.kind}
            if passed:
                manifest = snapshots.inventory(workspace)
                value = _write(directory, 'manifest.json', manifest)
                out.update(tree=relative(workspace), manifest=relative(directory / 'manifest.json'), manifest_sha256=value)
                out['bound_files'].update(bind(directory / 'manifest.json'))
            return out
        generated = row['stages']['generate']['output']
        workspace = inside(base, base / generated['tree'])
        result_manifest = _read(inside(base, base / generated['manifest']), generated['manifest_sha256'])
        snapshots.assert_snapshot(workspace, result_manifest)
        if stage == 'verify':
            run_dir = directory / 'check'
            run_dir.mkdir()
            budget.set_cancel_path(run_dir / 'cancel.request')
            receipt = self.backend.verify(workspace, contract, run_dir, budget, ProcessGuard(self.store, owner))
            if receipt.get('sdk_root_exit_observed') is True:
                for child_row in self.store.get(workflow_id)['children']:
                    self.store.clear_child(owner, child_row['pid'])
            snapshots.assert_snapshot(workspace, result_manifest)
            value = _write(directory, 'verification.json', receipt)
            return {'passed': receipt.get('accepted') is True and receipt.get('status') == 'passed',
                    'retryable': receipt.get('status') in ('timed_out', 'cancelled'),
                    'bound_files': {relative(directory / 'verification.json'): value},
                    'receipt': relative(directory / 'verification.json')}
        report = snapshots.report_bundle(seed, seed_manifest, workspace, result_manifest, directory / 'bundle')
        report['source_changed_since_start'] = snapshots.content_hash(snapshots.project_inventory(self.repo)) != snapshots.content_hash(seed_manifest)
        report['source_project_updated'] = False
        report['backend_kind'] = self.backend.kind
        report['request_reservations'] = requests.used
        ledger = self.store.get(workflow_id)
        records = [request['records'][-1] if request['records'] else None for request in ledger['requests']]
        report['requests_completed'] = sum(r is not None and r.get('status') == 'completed' for r in records)
        report['requests_failed'] = sum(r is not None and r.get('status') == 'failed' for r in records)
        report['requests_unknown'] = sum(r is None or r.get('status') not in ('completed', 'failed') for r in records)
        usage_keys = ('input_tokens', 'output_tokens', 'total_tokens')
        complete_usage = [r.get('usage') if r is not None else None for r in records]
        report['all_requests_usage'] = ({k: sum(u[k] for u in complete_usage) for k in usage_keys}
             if records and report['requests_completed'] == len(records)
             and all(isinstance(u, dict) and all(type(u.get(k)) is int and u[k] >= 0 for k in usage_keys) for u in complete_usage) else None)
        report['active_time_at_report_s'] = budget.timeout_s - budget.total_remaining_s()
        report['actual_api_cost_usd'] = None
        report['subscription_quota_delta'] = None
        value = _write(directory, 'summary.json', report)
        return {'passed': True, 'bundle': relative(directory / 'bundle'), 'summary': report,
                'bound_files': {relative(directory / 'summary.json'): value,
                                **bind(directory / 'bundle/manifest.json'), **bind(directory / 'bundle/diff.patch'),
                                **bind(directory / 'bundle/seed-manifest.json'), **bind(directory / 'bundle/report.json')}}
