#!/usr/bin/env python3
"""Codex Flow: offline installer, bounded inspection, and repo scaffolding.

Python 3.11+, standard library only. Never starts agents, installs dependencies,
reads credentials/session databases, or executes repository test/build commands.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from typing import Any

VERSION = '1.2.0'
OWNER = 'codex-flow'
SKILL_SOURCE = Path(__file__).absolute().parents[1]
MAX_BYTES = 2 * 1024 * 1024
BEGIN = '<!-- codex-flow:begin -->'
END = '<!-- codex-flow:end -->'
GLOBAL_BLOCK = '''## Codex Flow execution defaults
For software work, use the installed `codex-flow` skill for nontrivial implementation,
debugging, review, resuming work, or explicit workflow commands. For a tiny, clear
change, work directly and run its relevant check; do not bootstrap or create a team.
Use one coordinating workflow, not a stack of competing planners or autonomous loops.
Prefer one writer. Delegate only independent work with explicit scope and evidence;
start with at most two helpers. Never assume a subagent has an isolated worktree.
Keep acceptance criteria fixed, make the first useful check early, and avoid repeated
full scans, speculative improvements, or unchanged failing retries. Use Graphify only
when its dependency information is relevant, not as a mandatory startup step.
Playwright/browser UI checks are NOT default. Begin with focused non-browser tests.
Do not launch browsers, take screenshots, or run optional E2E for routine UI changes.
Use browsers only on explicit request, an applicable mandatory project/CI check,
or when browser-only/critical user behavior cannot be validated otherwise.
When justified, route through `codex-flow` browser guidance; Lightpanda/Obscura
are optional compatible DOM paths, not mandatory installs or visual substitutes.
Verify the actual combined change before completion; distinguish passed, failed, and
not-run checks. Preserve user changes, secrets, approval boundaries, and project rules.
These defaults do not override explicit user instructions or more specific repository
requirements. If workflows conflict, surface the conflict rather than silently stacking
or disabling them. Never claim a skill can guarantee speed or enforce a runtime timer.'''
# Canonical previous global blocks; foreign/edited content is preserved.
KNOWN_GLOBAL_BLOCK_HASHES = frozenset({
    "dee6320efe181d5ce9bfc9903aa729fcc31b74e55d878d124c9542fc6c850b03",  # 1.0.0
    "817ffbe1a6b9fcad1395d92c89614a5cb0c260446428efe605ea6f0195e195e3",  # 1.1.0
})
REPO_BLOCK = '''## Codex Flow project context
For nontrivial software work, read `.codex-flow/PROJECT.md` when relevant and use
`codex-flow` if it is available. This file is context, not executable configuration.
Treat discovered commands as UNVERIFIED until their source and execution are checked.
Use one task checkpoint only for long work; prefer an existing project tracker.
Do not create parallel writers without explicit ownership and verified isolation.
Project safety, test requirements, and explicit user directions remain authoritative.'''

class FlowError(RuntimeError):
    """A safe refusal or an actionable local operation error."""

@dataclass
class Settings:
    home: Path
    codex_home: Path | None = None
    skills_dir: Path | None = None

    def __post_init__(self):
        self.home = absolute(self.home)
        self.codex_home = absolute(self.codex_home or os.environ.get('CODEX_HOME') or self.home / '.codex')
        self.skills_dir = absolute(self.skills_dir or self.home / '.agents' / 'skills')

    @property
    def skill_dir(self) -> Path:
        return self.skills_dir / OWNER

    @property
    def manifest(self) -> Path:
        return self.codex_home / 'codex-flow-install.json'


def absolute(path: str | Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def safe_path(path: Path) -> None:
    """Refuse symbolic links and Windows junction/reparse points in any ancestor."""
    p = absolute(path)
    for item in [p, *p.parents]:
        try:
            st = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & 0x400:
            raise FlowError(f'Link/junction boundary refused: {item}. Use an explicit physical path.')


def read_bytes(path: Path) -> bytes:
    safe_path(path)
    if path.stat().st_size > MAX_BYTES:
        raise FlowError(f'File exceeds the {MAX_BYTES}-byte inspection limit: {path}')
    return path.read_bytes()


def decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith(b'\xff\xfe'): return raw[2:].decode('utf-16-le'), 'utf-16-le-bom'
    if raw.startswith(b'\xfe\xff'): return raw[2:].decode('utf-16-be'), 'utf-16-be-bom'
    if raw.startswith(b'\xef\xbb\xbf'): return raw[3:].decode('utf-8'), 'utf-8-bom'
    try:
        return raw.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError as exc:
        raise FlowError('Unsupported instruction encoding. Save as UTF-8 before retrying.') from exc


def encode(text: str, kind: str) -> bytes:
    if kind == 'utf-16-le-bom': return b'\xff\xfe' + text.encode('utf-16-le')
    if kind == 'utf-16-be-bom': return b'\xfe\xff' + text.encode('utf-16-be')
    if kind == 'utf-8-bom': return b'\xef\xbb\xbf' + text.encode('utf-8')
    return text.encode('utf-8')


def managed_block_hash(raw: bytes) -> str | None:
    """Fingerprint just the managed region; user text outside remains editable."""
    text, _ = decode(raw)
    begin_count, end_count = text.count(BEGIN), text.count(END)
    if begin_count != end_count or begin_count > 1:
        raise FlowError('Malformed or duplicate Codex Flow markers; update refused.')
    if begin_count == 0:
        return None
    left = text.index(BEGIN) + len(BEGIN)
    right = text.index(END)
    if right < left:
        raise FlowError('Reversed Codex Flow markers; update refused.')
    canonical = text[left:right].strip().replace('\r\n', '\n')
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def known_global_block_hashes() -> frozenset[str]:
    return KNOWN_GLOBAL_BLOCK_HASHES | {hashlib.sha256(GLOBAL_BLOCK.strip().encode('utf-8')).hexdigest()}


def update_block(raw: bytes, body: str | None) -> bytes:
    text, kind = decode(raw)
    n1, n2 = text.count(BEGIN), text.count(END)
    if n1 != n2 or n1 > 1:
        raise FlowError('Malformed or duplicate Codex Flow markers. No instructions were overwritten.')
    nl = '\r\n' if '\r\n' in text else '\n'
    block = (BEGIN + '\n' + body.strip() + '\n' + END).replace('\n', nl) if body is not None else ''
    if n1:
        a, b = text.index(BEGIN), text.index(END) + len(END)
        if b <= a: raise FlowError('Reversed Codex Flow markers.')
        text = text[:a] + block + text[b:]
    elif body is not None:
        text += (nl * 2 if text else '') + block + nl
    return encode(text, kind)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def atomic_write(path: Path, content: bytes) -> None:
    safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    fd, name = tempfile.mkstemp(prefix='.codex-flow-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None: os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def json_bytes(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')


def transact(changes: dict[Path, bytes | None], backups: Path, dry_run: bool) -> dict:
    """Preflight, backup, apply atomically per file, and roll back on an error."""
    pending: dict[Path, bytes | None] = {}
    previous: dict[Path, bytes | None] = {}
    for path, value in changes.items():
        safe_path(path)
        if path.exists() and not path.is_file(): raise FlowError(f'Expected a file: {path}')
        old = read_bytes(path) if path.exists() else None
        if old != value:
            pending[path], previous[path] = value, old
    result = {'changed': [str(p) for p in pending], 'dry_run': dry_run}
    if not pending or dry_run: return result
    safe_path(backups)
    backup = backups / stamp()
    backup.mkdir(parents=True, exist_ok=False)
    index = []
    for i, (p, old) in enumerate(previous.items()):
        name = f'{i:04d}.bak' if old is not None else None
        if name: (backup / name).write_bytes(old)
        index.append({'path': str(p), 'backup': name})
    (backup / 'index.json').write_bytes(json_bytes(index))
    applied: list[Path] = []
    try:
        for path, value in pending.items():
            if value is None:
                path.unlink()
            else:
                atomic_write(path, value)
            applied.append(path)
    except Exception as exc:
        failures = []
        for path in reversed(applied):
            try:
                if previous[path] is None: path.unlink(missing_ok=True)
                else: atomic_write(path, previous[path])
            except Exception:
                failures.append(str(path))
        extra = f' Manual recovery needed for: {failures}.' if failures else ' Changed files were rolled back.'
        raise FlowError(f'Operation failed ({type(exc).__name__}).{extra} Backup: {backup}') from exc
    result['backup'] = str(backup)
    return result


def effective_agents(root: Path) -> Path:
    over = root / 'AGENTS.override.md'
    if over.exists() and decode(read_bytes(over))[0].strip(): return over
    return root / 'AGENTS.md'


def permitted_install_path(settings: Settings, p: Path) -> bool:
    p = absolute(p)
    if p in [settings.codex_home / 'AGENTS.md', settings.codex_home / 'AGENTS.override.md']:
        return True
    if p.is_relative_to(settings.skill_dir): return True
    return p.parent == settings.codex_home / 'agents' and p.name in {
        'cf-explorer.toml', 'cf-reviewer.toml', 'cf-worker.toml'}


def load_manifest(settings: Settings) -> dict | None:
    if not settings.manifest.exists(): return None
    try:
        data = json.loads(read_bytes(settings.manifest))
        if not isinstance(data, dict) or not isinstance(data.get('files'), dict):
            raise ValueError('manifest must be an object with a file map')
        if data.get('owner') != OWNER or data.get('skill_dir') != str(settings.skill_dir):
            raise ValueError('ownership mismatch')
        for path, record in data['files'].items():
            if not isinstance(record, dict): raise ValueError('invalid file record')
            if not permitted_install_path(settings, Path(path)): raise ValueError('unowned path')
            safe_path(Path(path))
            if record['before'] is not None:
                base64.b64decode(record['before'], validate=True)
            if not re.fullmatch('[0-9a-f]{64}', record['after']): raise ValueError('invalid checksum')
        return data
    except (ValueError, KeyError, TypeError) as exc:
        raise FlowError('Install manifest is invalid or points outside owned paths. No changes made.') from exc


def install(settings: Settings, source: Path, *, skill_only=False, native_agents=False,
            dry_run=False, replace_edited=False) -> dict:
    for p in [settings.codex_home, settings.skill_dir]: safe_path(p)
    source = absolute(source)
    if not (source / 'SKILL.md').is_file(): raise FlowError('The source skill folder is incomplete.')
    if source == settings.skill_dir: raise FlowError('Run installer from the unpacked archive, not its installed copy.')
    previous = load_manifest(settings)
    options = {'skill_only': skill_only, 'native_agents': native_agents}
    if previous and previous.get('options') != options:
        raise FlowError('Installation options changed. Uninstall first, then install with the desired options.')
    if not previous and settings.skill_dir.exists() and any(settings.skill_dir.iterdir()):
        raise FlowError('Destination already contains an unowned skill. Move it aside before installing.')
    old_records = previous['files'] if previous else {}
    changes: dict[Path, bytes | None] = {}
    warnings = []
    sources = sorted(p for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    for p in sources:
        relative = p.relative_to(source)
        target = settings.skill_dir / relative
        safe_path(p)
        changes[target] = read_bytes(p)
    if native_agents:
        examples = source.parents[1] / 'examples' / 'native-agents'
        for name in ('cf-explorer.toml', 'cf-reviewer.toml', 'cf-worker.toml'):
            p = examples / name
            if not p.is_file(): raise FlowError('Native agent examples are missing from this archive.')
            changes[settings.codex_home / 'agents' / name] = read_bytes(p)
    global_target = None
    if not skill_only:
        global_target = effective_agents(settings.codex_home)
        old_global_targets = [Path(key) for key, record in old_records.items() if record.get('kind') == 'global']
        if previous and old_global_targets != [global_target]:
            raise FlowError('Effective global AGENTS target differs from previous install or the manifest is incomplete. '
                            'Review AGENTS.md/AGENTS.override.md and migrate by hand; no changes made.')
        raw = read_bytes(global_target) if global_target.exists() else b''
        current_block_hash = managed_block_hash(raw)
        if previous and current_block_hash not in known_global_block_hashes():
            raise FlowError('Existing Codex Flow global instruction block was edited or removed. '
                            'Preserve the custom instructions and reconcile the block manually before upgrading. '
                            'No files were modified; -ReplaceEdited does not bypass this protection.')
        if not previous and current_block_hash is not None:
            raise FlowError('Codex Flow markers exist without a matching install manifest. '
                            'The existing managed region is not owned by this installer; review it manually.')
        changes[global_target] = update_block(raw, GLOBAL_BLOCK)
        if global_target.name == 'AGENTS.override.md':
            warnings.append('Appended only to the existing effective AGENTS.override.md; base AGENTS.md is unchanged.')
        if len(changes[global_target]) > 24000:
            warnings.append('Global guidance is large; check the combined instruction size before relying on this block.')
    # Preserve user-edited managed code; global guidance is updated by markers only.
    records = dict(old_records)
    for target, content in changes.items():
        safe_path(target)
        current = read_bytes(target) if target.exists() else None
        record = old_records.get(str(target))
        if record and target != global_target and current is not None:
            if digest(current) != record['after'] and current != content and not replace_edited:
                raise FlowError(f'Locally edited managed file preserved: {target}. Back it up, then use --replace-edited explicitly.')
        if not record and target != global_target and current is not None and current != content:
            raise FlowError(f'Unowned existing file preserved: {target}')
        records[str(target)] = {
            'before': record['before'] if record else (base64.b64encode(current).decode('ascii') if current is not None else None),
            'after': digest(content),
            'kind': 'global' if target == global_target else 'file',
        }
    manifest = {'owner': OWNER, 'version': VERSION, 'skill_dir': str(settings.skill_dir),
                'options': options, 'files': records}
    changes[settings.manifest] = json_bytes(manifest)
    result = transact(changes, settings.codex_home / 'codex-flow-backups', dry_run)
    result.update({'version': VERSION, 'skill_dir': str(settings.skill_dir),
                   'global_instructions': str(global_target) if global_target else None, 'warnings': warnings})
    return result


def uninstall(settings: Settings, *, dry_run=False) -> dict:
    previous = load_manifest(settings)
    if not previous: return {'changed': [], 'dry_run': dry_run, 'warnings': ['No managed installation found.']}
    changes: dict[Path, bytes | None] = {}
    for path, record in previous['files'].items():
        p = Path(path)
        current = read_bytes(p) if p.exists() else None
        before = base64.b64decode(record['before']) if record['before'] is not None else None
        if current is None:
            # Do not resurrect a file the user deliberately removed.
            continue
        if record.get('kind') == 'global' and BEGIN in decode(current)[0]:
            if managed_block_hash(current) not in known_global_block_hashes():
                raise FlowError(f'Edited global Codex Flow block preserved during uninstall: {p}. Reconcile it first.')
            stripped = update_block(current, None)
            stripped_text, _ = decode(stripped)
            original_text = decode(before)[0] if before is not None else None
            # Preserve user edits outside our marker, even when a repeated upgrade
            # recorded the entire current file as its new managed checksum.
            if original_text is not None and stripped_text.strip() == original_text.strip():
                changes[p] = before  # restore original bytes including BOM and newlines
            elif stripped_text.strip():
                changes[p] = stripped
            elif original_text is None:
                changes[p] = None
            else:
                changes[p] = stripped  # user intentionally emptied outer guidance
        elif digest(current) == record['after']:
            changes[p] = before
        else:
            raise FlowError(f'Edited managed file preserved: {p}. Back it up and reconcile it before uninstalling.')
    changes[settings.manifest] = None
    result = transact(changes, settings.codex_home / 'codex-flow-backups', dry_run)
    if not dry_run and settings.skill_dir.exists():
        # Only clean parents of owned files, never traverse untracked user directories.
        parents = {settings.skill_dir}
        for owned in previous['files']:
            p = Path(owned)
            if not p.is_relative_to(settings.skill_dir): continue
            for parent in p.parents:
                if not parent.is_relative_to(settings.skill_dir): break
                parents.add(parent)
        for directory in sorted(parents, key=lambda x: len(x.parts), reverse=True):
            safe_path(directory)
            try: directory.rmdir()
            except OSError: pass
    return result


def git(repo: Path, *args: str) -> tuple[int, str]:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
    try:
        proc = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-C', str(repo), *args],
                              capture_output=True, timeout=8, env=env)
        return proc.returncode, proc.stdout[:65536].decode('utf-8', 'replace').strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise FlowError('Git is missing or metadata inspection timed out. No repository code was executed.') from exc


def repo_root(path: Path) -> Path:
    p = absolute(path)
    safe_path(p)
    if not p.is_dir(): raise FlowError(f'Repository directory not found: {p}')
    code, root = git(p, 'rev-parse', '--show-toplevel')
    if code or not root: raise FlowError('A Git working tree is required; this tool will not run git init automatically.')
    root = absolute(root)
    safe_path(root)
    return root


def manifest_candidates(root: Path) -> list[Path]:
    """Known root files and at most two levels of conventional app folders."""
    directories = [root]
    for name in ('backend', 'frontend', 'server', 'client', 'desktop', 'apps', 'packages'):
        p = root / name
        if not p.is_dir() or p.is_symlink(): continue
        safe_path(p)
        directories.append(p)
        if name in ('apps', 'packages'):
            children = []
            for index, child in enumerate(p.iterdir()):
                if index >= 100 or len(children) >= 20: break
                if child.is_dir() and not child.is_symlink() and not child.name.startswith('.') and child.name != 'node_modules':
                    safe_path(child)
                    children.append(child)
            directories.extend(sorted(children))
    result = []
    for directory in directories:
        for name in ('package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod'):
            p = directory / name
            if p.is_file():
                safe_path(p)
                result.append(p)
    return result


def discover_project(root: Path) -> dict:
    commands, manifests, warnings = [], [], []
    for path in manifest_candidates(root):
        rel = path.relative_to(root).as_posix()
        manifests.append(rel)
        cwd = path.parent.relative_to(root).as_posix()
        try:
            raw = read_bytes(path).decode('utf-8-sig')
            if path.name == 'package.json':
                data = json.loads(raw)
                if not isinstance(data, dict): raise ValueError('package manifest must be an object')
                scripts = data.get('scripts', {})
                if not isinstance(scripts, dict): raise ValueError('scripts must be a map')
                runner = 'npm'
                if (path.parent / 'pnpm-lock.yaml').exists(): runner = 'pnpm'
                elif (path.parent / 'yarn.lock').exists(): runner = 'yarn'
                elif (path.parent / 'bun.lock').exists() or (path.parent / 'bun.lockb').exists(): runner = 'bun'
                for name in ('test', 'test:unit', 'test:ci', 'lint', 'typecheck', 'check', 'build'):
                    if name in scripts:
                        commands.append({'cwd': cwd, 'command': f'{runner} run {name}', 'status': 'UNVERIFIED', 'source': rel})
                        if isinstance(scripts[name], str) and re.search(r'(^|\s)(--watch|watch)(\s|$)', scripts[name]):
                            warnings.append(f'{rel}: {name} appears watch-based; choose a finite invocation before verification.')
            elif path.name == 'pyproject.toml':
                data = tomllib.loads(raw)
                if 'pytest' in data.get('tool', {}):
                    commands.append({'cwd': cwd, 'command': 'python -m pytest', 'status': 'UNVERIFIED', 'source': rel})
            elif path.name == 'Cargo.toml':
                tomllib.loads(raw)
                commands.append({'cwd': cwd, 'command': 'cargo test', 'status': 'UNVERIFIED', 'source': rel})
            elif path.name == 'go.mod':
                commands.append({'cwd': cwd, 'command': 'go test ./...', 'status': 'UNVERIFIED', 'source': rel})
        except (ValueError, UnicodeError, FlowError):
            warnings.append(f'Could not safely parse {rel}; inspect this file manually. Its contents were not logged.')
    return {'manifests': manifests, 'commands': commands, 'warnings': warnings}


def project_text(info: dict) -> str:
    lines = ['# Project context for Codex Flow', '',
             'Status: BOOTSTRAPPED; project-specific facts and commands still need validation.',
             'This is human/agent context, NOT a Codex config file. Do not execute it.', '',
             '## Source inventory (bounded, potentially partial discovery)',
             'Only conventional folders are inspected; at most 100 entries / 20 subfolders per apps or packages directory.',
             *[f'- `{x}`' for x in info['manifests']], '',
             '## Candidate verification commands — UNVERIFIED',
             'Read the referenced manifest, README and relevant CI workflow before running a candidate.',
             'Check for watch mode, side effects, required credentials, databases and network access.',
             'Do not treat exit 0 as enough when zero tests ran. Never label a missing check passed.', '',
             '| Working directory | Candidate | Evidence | Status |',
             '|---|---|---|---|']
    for c in info['commands']:
        lines.append(f"| `{c['cwd']}` | `{c['command']}` | `{c['source']}` | UNVERIFIED |")
    if not info['commands']:
        lines.append('| Not established | Determine from README / CI / manifests | No safe candidate established | UNVERIFIED |')
    lines += ['', '## Stable project facts',
              '- Purpose and supported runtime: not established by bootstrap.',
              '- Module ownership and shared interfaces: determine only for the current task.',
              '- Protected data, migrations, public API and deployment boundaries: follow existing project instructions.',
              '- Environment setup: use the existing documented environment; do not reinstall by default.',
              '- Existing task tracker / implementation status file: reuse it rather than create a second ledger.',
              '- Graphify: use an existing relevant index; validate important findings against current source.', '',
              '## Working defaults',
              '- Tiny task: one agent, focused edit and check; no new plan document.',
              '- Normal task: short acceptance contract, implementation, relevant verification, final diff.',
              '- Parallel work: one coordinator, usually at most two independent helpers; one writer by default.',
              '- Long work: one checkpoint per task, preserve accepted decisions, stop loops without evidence.',
              '- Commands and concurrency limits here are guidance; they do not enforce runtime limits.', '',
              '## Bootstrap warnings', *[f'- {x}' for x in info['warnings']], '']
    return '\n'.join(lines)


def bootstrap(path: Path, *, attach=False, dry_run=False) -> dict:
    root = repo_root(path)
    state = root / '.codex-flow'
    safe_path(state)
    info = discover_project(root)
    changes: dict[Path, bytes | None] = {}
    profile = state / 'PROJECT.md'
    if not profile.exists(): changes[profile] = project_text(info).encode('utf-8')
    ignore = state / '.gitignore'
    if not ignore.exists(): changes[ignore] = b'tasks/\nreports/\nbackups/\n'
    target = None
    if attach:
        target = effective_agents(root)
        changes[target] = update_block(read_bytes(target) if target.exists() else b'', REPO_BLOCK)
    result = transact(changes, state / 'backups', dry_run)
    result.update({'repo': str(root), 'profile': str(profile), 'instructions': str(target) if target else None,
                   'warnings': info['warnings'], 'commands_executed': False})
    return result


def new_task(path: Path, task_id: str, title: str, *, dry_run=False) -> dict:
    forbidden = {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))}
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', task_id) or task_id.lower() in forbidden:
        raise FlowError('Task id must be a safe 1–64 character name, without slashes or reserved Windows names.')
    if not title.strip() or len(title) > 300 or '\n' in title or '\r' in title:
        raise FlowError('Title must be one non-empty line, at most 300 characters.')
    root = repo_root(path)
    target = root / '.codex-flow' / 'tasks' / f'{task_id}.md'
    safe_path(target)
    if target.exists(): raise FlowError('This task checkpoint already exists. Read and update it instead of replacing it.')
    _, branch = git(root, 'symbolic-ref', '--short', 'HEAD')
    _, head = git(root, 'rev-parse', '--verify', 'HEAD')
    text = f'''# {title}

Task id: {task_id}
State: NOT_STARTED
Created UTC: {datetime.now(timezone.utc).isoformat()}
Branch at creation: {branch or 'detached / unknown'}
HEAD at creation: {head or 'unborn / unknown'}

## Acceptance criteria and non-goals
Record only the requested observable outcomes; do not invent extra scope.

## Current checkpoint
No implementation or verification has been performed by this helper.

## Decisions and evidence
Record stable decisions, relevant paths, and why rejected hypotheses were rejected.

## Work ownership
One coordinator. List any actual helper id, precise scope, and verified working directory.

## Verification
| Command and cwd | Result | Evidence / timestamp |
|---|---|---|
| Not run | NOT_RUN | Bootstrap only |

## Blocker and next exact action
Determine the smallest useful next action from the current code and task contract.

## Handoff
Before resuming, compare branch/HEAD/dirty files against this note. Do not redo a completed
step without a changed input or contrary evidence. Never store credentials or full raw logs here.
'''
    changes = {target: text.encode('utf-8')}
    ignore = root / '.codex-flow' / '.gitignore'
    if not ignore.exists(): changes[ignore] = b'tasks/\nreports/\nbackups/\n'
    result = transact(changes, root / '.codex-flow' / 'backups', dry_run)
    result['path'] = str(target)
    return result


def instruction_facts(path: Path) -> dict:
    if not path.exists(): return {'exists': False}
    raw = read_bytes(path)
    text, _ = decode(raw)
    terms = ('superpowers', 'graphify', 'always', 'mandatory', 'обязательно', 'всегда')
    return {'exists': True, 'bytes': len(raw), 'flow_block': BEGIN in text,
            'keyword_counts': {t: len(re.findall(re.escape(t), text, re.IGNORECASE)) for t in terms}}


def config_facts(path: Path) -> dict:
    if not path.exists(): return {'exists': False}
    data = tomllib.loads(decode(read_bytes(path))[0])
    facts: dict[str, Any] = {'exists': True, 'values': {}}
    allowed = {'model_reasoning_effort': {'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'},
               'service_tier': {'default', 'auto', 'standard', 'fast', 'flex'},
               'sandbox_mode': {'read-only', 'workspace-write', 'danger-full-access'},
               'approval_policy': {'untrusted', 'on-failure', 'on-request', 'never'}}
    for key, choices in allowed.items():
        if key in data: facts['values'][key] = data[key] if isinstance(data[key], str) and data[key] in choices else 'present; value not reported'
    agents = data.get('agents', {})
    for key in ('enabled', 'max_concurrent_threads_per_session', 'max_threads'):
        value = agents.get(key) if isinstance(agents, dict) else None
        if type(value) in (bool, int): facts['values']['agents.' + key] = value
    # Report counts rather than provider identifiers, commands, arguments, URLs or env values.
    for group in ('mcp_servers', 'plugins'):
        entries = data.get(group, {})
        if isinstance(entries, dict):
            facts[group] = {'configured_count': len(entries),
                           'explicitly_enabled_count': sum(isinstance(v, dict) and v.get('enabled') is True for v in entries.values()),
                           'explicitly_disabled_count': sum(isinstance(v, dict) and v.get('enabled') is False for v in entries.values())}
    skills = data.get('skills', {})
    entries = skills.get('config', []) if isinstance(skills, dict) else []
    facts['disabled_skill_entries'] = sum(isinstance(v, dict) and v.get('enabled') is False for v in entries) if isinstance(entries, list) else 0
    facts['runtime_activation_verified'] = False
    return facts


def doctor(settings: Settings, repo: Path | None = None) -> dict:
    result: dict[str, Any] = {'version': VERSION, 'python': sys.version.split()[0],
        'codex_home': str(settings.codex_home), 'skills_dir': str(settings.skills_dir),
        'codex_on_path': shutil.which('codex') is not None, 'git_on_path': shutil.which('git') is not None,
        'warnings': [], 'inspection': 'Read-only; no credentials, sessions, databases, caches, or model calls.'}
    for root in (settings.codex_home, settings.skills_dir): safe_path(root)
    configs = {'user_config': settings.codex_home / 'config.toml'}
    instructions = {'global_agents': settings.codex_home / 'AGENTS.md',
                    'global_override': settings.codex_home / 'AGENTS.override.md'}
    if repo is not None:
        root = repo_root(repo)
        result['repo'] = str(root)
        configs['repo_config'] = root / '.codex' / 'config.toml'
        instructions['repo_agents'] = root / 'AGENTS.md'
        instructions['repo_override'] = root / 'AGENTS.override.md'
        result['repo_profile_exists'] = (root / '.codex-flow' / 'PROJECT.md').exists()
    for label, path in instructions.items():
        try: result[label] = instruction_facts(path)
        except (FlowError, OSError, UnicodeError):
            result[label] = {'status': 'not inspected'}
            result['warnings'].append(f'{label}: unreadable, linked, oversized or unsupported encoding.')
    for label, path in configs.items():
        try: result[label] = config_facts(path)
        except (FlowError, OSError, ValueError, UnicodeError):
            result[label] = {'status': 'not parsed'}
            result['warnings'].append(f'{label}: cannot safely parse TOML; raw contents were not logged.')
    names = []
    truncated = False
    if settings.skills_dir.is_dir():
        for index, directory in enumerate(settings.skills_dir.iterdir()):
            if index >= 200:
                truncated = True
                break
            if not directory.is_dir() or directory.is_symlink(): continue
            try:
                safe_path(directory)
                if (directory / 'SKILL.md').is_file(): names.append(directory.name)
            except FlowError: continue
    # Count only one-level local folders, not metadata across caches/marketplaces.
    result['local_skills'] = {'count': len(names), 'partial': truncated, 'flow_present': OWNER in names,
                              'scope': 'Immediate children of user .agents/skills; not all installed plugins.'}
    result['legacy_skill_directory_present'] = (settings.codex_home / 'skills').exists()
    if result.get('global_override', {}).get('bytes', 0):
        result['warnings'].append('A non-empty global AGENTS.override.md takes precedence over global AGENTS.md.')
    if any(result.get(k, {}).get('bytes', 0) > 24000 for k in instructions):
        result['warnings'].append('An instruction file is large. Inspect instruction-chain size and competing process rules.')
    result['warnings'].append('Configured/local presence does not prove a skill or plugin was active in a slow session.')
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Codex Flow offline setup and project helpers (Python 3.11+).')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('install', 'uninstall', 'doctor'):
        p = sub.add_parser(name)
        p.add_argument('--home', type=Path, default=Path.home())
        p.add_argument('--codex-home', type=Path)
        p.add_argument('--skills-dir', type=Path)
        if name != 'doctor': p.add_argument('--dry-run', action='store_true')
        else: p.add_argument('--repo', type=Path)
        if name == 'install':
            p.add_argument('--skill-only', action='store_true')
            p.add_argument('--native-agents', action='store_true')
            p.add_argument('--replace-edited', action='store_true')
    p = sub.add_parser('init')
    p.add_argument('--repo', type=Path, default=Path.cwd())
    p.add_argument('--attach', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p = sub.add_parser('new-task')
    p.add_argument('--repo', type=Path, default=Path.cwd())
    p.add_argument('--id', required=True)
    p.add_argument('--title', required=True)
    p.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command in ('install', 'uninstall', 'doctor'):
            settings = Settings(args.home, args.codex_home, args.skills_dir)
            if args.command == 'install':
                result = install(settings, SKILL_SOURCE, skill_only=args.skill_only,
                                 native_agents=args.native_agents, dry_run=args.dry_run, replace_edited=args.replace_edited)
            elif args.command == 'uninstall': result = uninstall(settings, dry_run=args.dry_run)
            else: result = doctor(settings, args.repo)
        elif args.command == 'init': result = bootstrap(args.repo, attach=args.attach, dry_run=args.dry_run)
        else: result = new_task(args.repo, args.id, args.title, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (FlowError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'): sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
