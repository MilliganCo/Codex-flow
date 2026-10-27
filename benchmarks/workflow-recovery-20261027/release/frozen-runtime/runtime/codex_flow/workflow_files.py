"""Bounded byte snapshots and review bundles; project files are never executed."""
from __future__ import annotations

import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from .contracts import PolicyError, inside

MAX_FILES = 10000
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_DIFF_FILE_BYTES = 1024 * 1024
MAX_DIFF_TOTAL_BYTES = 8 * 1024 * 1024
PRIVATE = {'.git', '.codex-flow', '.codex', '.agents', '.home', '.tmp'}
DEVICES = {'con', 'prn', 'aux', 'nul', 'conin$', 'conout$'} | {
    prefix + number for prefix in ('com', 'lpt') for number in '123456789¹²³'}


def _relative(name):
    if not isinstance(name, str) or not name or any(c in name for c in '\\:<>"|?*'):
        raise PolicyError('snapshot requires relative POSIX paths')
    parts = name.split('/')
    if any(not p or p in ('.', '..') or p.endswith(('.', ' ')) or
           p.split('.')[0].casefold() in DEVICES or any(ord(c) < 32 for c in p) for p in parts):
        raise PolicyError('snapshot path alias or escape refused')
    return name


def _omitted(name):
    parts = name.casefold().split('/')
    leaf = parts[-1]
    return (any(p in PRIVATE for p in parts) or leaf in ('auth.json', 'credentials.json', '.env')
            or leaf.startswith('.env.') and leaf != '.env.example' or leaf.endswith(('.key', '.pem')))


def _aliases(names):
    seen = {}
    for name in names:
        _relative(name)
        parts = name.split('/')
        for i in range(1, len(parts) + 1):
            prefix = '/'.join(parts[:i])
            previous = seen.setdefault(prefix.casefold(), prefix)
            if previous != prefix:
                raise PolicyError('snapshot case alias refused')
        if any('/'.join(parts[:i]) in names for i in range(1, len(parts))):
            raise PolicyError('snapshot file and directory collision')


def _root(path):
    path = Path(path).absolute()
    _relative('/'.join(path.parts[1:]))
    path = inside(path, path)
    if not path.is_dir():
        raise PolicyError('snapshot root must be an existing directory')
    return path


def _identity(info):
    # Windows lstat and CRT fstat can expose different creation-time values.
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns if os.name != 'nt' else None,
            info.st_mode, info.st_nlink)


def _read(root, name):
    path = inside(root, root / _relative(name))
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_FILE_BYTES:
        raise PolicyError('snapshot regular file boundary or size refused')
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise PolicyError('snapshot file changed before read')
        raw = stream.read(MAX_FILE_BYTES + 1)
        after = os.fstat(stream.fileno())
    inside(root, path)
    if len(raw) > MAX_FILE_BYTES or len(raw) != before.st_size or any(
            _identity(info) != _identity(before) for info in (after, path.lstat())):
        raise PolicyError('snapshot file changed during read')
    return raw, {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw),
                 'executable': bool(before.st_mode & 0o111) if os.name != 'nt' else False}


def _manifest(manifest):
    if (not isinstance(manifest, dict) or set(manifest) - {'schema', 'files', 'omitted', 'source_head'}
            or type(manifest.get('schema')) is not int or manifest['schema'] != 1
            or not isinstance(manifest.get('files'), dict) or not isinstance(manifest.get('omitted'), list)):
        raise PolicyError('invalid snapshot manifest')
    files = manifest['files']
    _aliases(files)
    total = 0
    for name, row in files.items():
        if (_omitted(name) or not isinstance(row, dict) or set(row) != {'sha256', 'size', 'executable'}
                or not isinstance(row['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', row['sha256'])
                or type(row['size']) is not int or not 0 <= row['size'] <= MAX_FILE_BYTES
                or type(row['executable']) is not bool):
            raise PolicyError('invalid snapshot file manifest')
        total += row['size']
    if len(files) > MAX_FILES or total > MAX_TOTAL_BYTES or len(manifest['omitted']) > MAX_FILES * 2:
        raise PolicyError('snapshot inventory bound exceeded')
    for name in manifest['omitted']:
        _relative(name)
    if 'source_head' in manifest and (not isinstance(manifest['source_head'], str) or
                                    not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', manifest['source_head'])):
        raise PolicyError('invalid snapshot source head')
    return files


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('utf-8')


def manifest_hash(manifest):
    _manifest(manifest)
    return hashlib.sha256(_json(manifest)).hexdigest()


def content_hash(manifest):
    return hashlib.sha256(_json(_manifest(manifest))).hexdigest()


def _walk(root):
    names, omitted, todo, visited = [], [], [root], 0
    while todo:
        for path in sorted(todo.pop().iterdir()):
            visited += 1
            if visited > MAX_FILES * 2:
                raise PolicyError('snapshot inventory bound exceeded')
            name = _relative(path.relative_to(root).as_posix())
            inside(root, path)
            if _omitted(name):
                omitted.append(name)
            elif path.is_dir():
                todo.append(path)
            else:
                names.append(name)
    _aliases(set(names))
    return sorted(names), sorted(omitted)


def inventory(root: Path) -> dict:
    root = _root(root)
    names, omitted = _walk(root)
    files, total = {}, 0
    for name in names:
        _, files[name] = _read(root, name)
        total += files[name]['size']
        if len(files) > MAX_FILES or total > MAX_TOTAL_BYTES:
            raise PolicyError('snapshot inventory bound exceeded')
    return {'schema': 1, 'files': files, 'omitted': omitted}


def assert_snapshot(root: Path, manifest: dict) -> None:
    if inventory(root)['files'] != _manifest(manifest):
        raise PolicyError('snapshot file inventory or bytes changed')


def _fresh(dest, sources=()):
    dest = Path(dest).absolute()
    _relative('/'.join(dest.parts[1:]))
    dest = inside(dest.parent, dest)
    if any(dest == source or source in dest.parents or dest in source.parents for source in sources):
        raise PolicyError('snapshot destination overlaps its source')
    if not dest.parent.is_dir():
        raise PolicyError('snapshot destination parent must exist')
    dest.mkdir(exist_ok=False)
    return dest


def _write(root, name, raw, executable=False):
    path = inside(root, root / _relative(name))
    path.parent.mkdir(parents=True, exist_ok=True)
    path = inside(root, path)
    with path.open('xb') as stream:
        stream.write(raw)
        if os.name != 'nt' and executable:
            os.fchmod(stream.fileno(), 0o755)


def materialize(seed: Path, manifest: dict, dest: Path) -> None:
    seed = _root(seed)
    files = _manifest(manifest)
    assert_snapshot(seed, manifest)
    dest = _fresh(dest, (seed,))
    for name, expected in sorted(files.items()):
        raw, actual = _read(seed, name)
        if actual != expected:
            raise PolicyError('snapshot seed changed during materialization')
        _write(dest, name, raw, expected['executable'])
    assert_snapshot(seed, manifest)
    assert_snapshot(dest, manifest)


def _git(repo, *args, optional=False):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env.update(GIT_OPTIONAL_LOCKS='0', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT='0', GIT_NO_REPLACE_OBJECTS='1')
    command = ['git', '-c', 'core.hooksPath=' + os.devnull, '-c', 'core.fsmonitor=false',
               '-c', 'core.untrackedCache=false', '--no-pager', '-C', str(repo), *args]
    result = subprocess.run(command, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, shell=False, check=False)
    if result.returncode and not optional:
        raise PolicyError('snapshot Git metadata command failed')
    if len(result.stdout) > MAX_FILES * 4096:
        raise PolicyError('snapshot Git metadata bound exceeded')
    return result.stdout if result.returncode == 0 else b''


def _source(repo):
    raw = _git(repo, 'ls-files', '-z', '--cached', '--others', '--exclude-standard')
    if raw and not raw.endswith(b'\0'):
        raise PolicyError('snapshot Git filenames must be NUL terminated')
    try:
        names = sorted(set(raw[:-1].decode('utf-8').split('\0'))) if raw else []
    except UnicodeDecodeError:
        raise PolicyError('snapshot requires UTF-8 filenames') from None
    if len(names) > MAX_FILES * 2:
        raise PolicyError('snapshot inventory bound exceeded')
    # Git marks untracked nested repositories with a final slash, including
    # our excluded attempt workspaces. Normalize only excluded directory markers.
    names = [name[:-1] if name.endswith('/') and _omitted(name[:-1]) else name for name in names]
    _aliases({name for name in names if not _omitted(name)})
    files, omitted, total = {}, [], 0
    for name in names:
        path = inside(repo, repo / _relative(name))
        if _omitted(name):
            omitted.append(name)
            continue
        if not path.exists():
            omitted.append(name)
            continue
        _, files[name] = _read(repo, name)
        total += files[name]['size']
        if len(files) > MAX_FILES or total > MAX_TOTAL_BYTES:
            raise PolicyError('snapshot inventory bound exceeded')
    manifest = {'schema': 1, 'files': files, 'omitted': omitted}
    head = _git(repo, 'rev-parse', '--verify', 'HEAD', optional=True).strip()
    if head:
        manifest['source_head'] = head.decode('ascii')
    return manifest


def project_inventory(repo: Path) -> dict:
    """Read working bytes selected by Git without copying or creating any path."""
    repo = _root(repo)
    inside(repo, repo / '.git')
    top = _git(repo, 'rev-parse', '--show-toplevel').decode('utf-8').strip()
    if Path(top).resolve() != repo:
        raise PolicyError('snapshot requires the Git project root')
    return _source(repo)


def seed_project(repo: Path, dest: Path) -> dict:
    repo = _root(repo)
    manifest = project_inventory(repo)
    # A project may keep workflow state in one of the excluded control directories.
    destination = Path(dest).absolute()
    control = repo in destination.parents and any(p.casefold() in PRIVATE
                                                 for p in destination.relative_to(repo).parts)
    sources = () if control else (repo,)
    dest = _fresh(destination, sources)
    for name, expected in manifest['files'].items():
        raw, actual = _read(repo, name)
        if actual != expected:
            raise PolicyError('snapshot source changed during copy')
        _write(dest, name, raw, expected['executable'])
    current = project_inventory(repo)
    if current['files'] != manifest['files'] or current.get('source_head') != manifest.get('source_head'):
        raise PolicyError('snapshot source changed during copy')
    assert_snapshot(dest, manifest)
    return manifest


def _diff_summary(name, reason):
    encoded = name.encode('utf-8')
    label = encoded[:144].decode('utf-8', errors='ignore')
    if len(encoded) > 144:
        label += '...#' + hashlib.sha256(encoded).hexdigest()[:12]
    return ('Diff summary for ' + label + ': ' + reason + '; review files/ and manifest.json.\n').encode('utf-8')


def _diff_piece(seed, before, result, after, name):
    if sum(rows.get(name, {}).get('size', 0) for rows in (before, after)) > MAX_DIFF_FILE_BYTES:
        return _diff_summary(name, 'text size limit'), True
    old, old_row = _read(seed, name) if name in before else (b'', None)
    new, new_row = _read(result, name) if name in after else (b'', None)
    if old_row != before.get(name) or new_row != after.get(name):
        raise PolicyError('snapshot changed during diff generation')
    try:
        if b'\0' in old or b'\0' in new:
            raise UnicodeError()
        lines = difflib.unified_diff(old.decode('utf-8').splitlines(keepends=True),
                                    new.decode('utf-8').splitlines(keepends=True),
                                    'a/' + name if name in before else '/dev/null',
                                    'b/' + name if name in after else '/dev/null')
    except UnicodeError:
        return _diff_summary(name, 'binary content'), True
    piece = bytearray()
    for line in lines:
        raw = (line if line.endswith('\n') else line + '\n\\ No newline at end of file\n').encode('utf-8')
        if len(piece) + len(raw) > MAX_DIFF_FILE_BYTES:
            return _diff_summary(name, 'text size limit'), True
        piece.extend(raw)
    return bytes(piece), False


def report_bundle(seed: Path, seed_manifest: dict, result: Path, result_manifest: dict, dest: Path) -> dict:
    seed, result = _root(seed), _root(result)
    before, after = _manifest(seed_manifest), _manifest(result_manifest)
    assert_snapshot(seed, seed_manifest)
    assert_snapshot(result, result_manifest)
    report = {'schema': 1, 'added': sorted(after.keys() - before.keys()),
              'deleted': sorted(before.keys() - after.keys()),
              'changed': sorted(n for n in before.keys() & after.keys() if before[n] != after[n]),
              'seed_manifest_sha256': manifest_hash(seed_manifest),
              'result_manifest_sha256': manifest_hash(result_manifest),
              'files': 'files', 'manifest': 'manifest.json', 'diff': 'diff.patch'}
    dest = _fresh(dest, (seed, result))
    materialize(result, result_manifest, dest / 'files')
    digest, written, limited = hashlib.sha256(), 0, False
    footer = b'Diff size limit reached; review all changed paths in report.json and exact files/ with manifest.json.\n'
    with (dest / 'diff.patch').open('xb') as stream:
        for name in sorted(set(report['added'] + report['deleted'] + report['changed'])):
            raw, partial = _diff_piece(seed, before, result, after, name)
            limited |= partial
            if written + len(raw) > MAX_DIFF_TOTAL_BYTES - len(footer):
                raw, limited = _diff_summary(name, 'total text diff limit'), True
            stop = written + len(raw) > MAX_DIFF_TOTAL_BYTES - len(footer)
            if stop:
                raw = footer if written + len(footer) <= MAX_DIFF_TOTAL_BYTES else b''
            stream.write(raw)
            digest.update(raw)
            written += len(raw)
            if stop:
                break
    report['diff_sha256'] = digest.hexdigest()
    report['text_diff_limited'] = limited
    for name, value in (('manifest.json', result_manifest), ('seed-manifest.json', seed_manifest),
                        ('report.json', report)):
        _write(dest, name, _json(value) + b'\n')
    assert_snapshot(seed, seed_manifest)
    assert_snapshot(result, result_manifest)
    assert_snapshot(dest / 'files', result_manifest)
    return report
