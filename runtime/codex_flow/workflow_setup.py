"""Explicit owner initialization, versioned templates, and default checker binding."""
from __future__ import annotations
import ast
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import uuid

from . import acceptance, workflow_files
from .contracts import PolicyError, inside
from .telemetry import write_json
from .workflow_templates import unittest_checker

TASK = ('# Describe the requested change\n\n'
        '<!-- CODEX_FLOW_TASK_REQUIRED -->\n'
        'Replace this marker and describe the result, constraints, and examples.\n'
        'Existing baseline tests are immutable under the generated acceptance checker.\n')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _root(repo):
    return inside(repo.absolute(), repo.absolute())


def _folder(repo):
    return inside(repo, repo / '.codex-flow/project')


def _test_files(manifest, test_dir, pattern):
    return [name for name in manifest['files'] if name.startswith(test_dir + '/')
            and name.endswith('.py') and fnmatch.fnmatchcase(Path(name).name, pattern)]


def _uses_unittest(repo, names):
    for name in names[:200]:
        raw = acceptance._file(inside(repo, repo / name), 262144)
        try:
            tree = ast.parse(raw.decode('utf-8-sig'))
        except (UnicodeError, SyntaxError, RecursionError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(n.name == 'unittest' or n.name.startswith('unittest.') for n in node.names):
                return True
            if isinstance(node, ast.ImportFrom) and node.module and (node.module == 'unittest' or node.module.startswith('unittest.')):
                return True
    return False


def inspect_project(repo, *, framework='auto', test_dir=None, pattern='test*.py', allow_skips=0, inputs=None):
    repo = _root(repo)
    if framework not in ('auto', 'unittest'):
        raise PolicyError('unsupported setup framework')
    manifest = workflow_files.project_inventory(repo)
    candidates = [acceptance._relative(test_dir)] if test_dir is not None else ['tests', 'test']
    selected = None
    for candidate in candidates:
        unittest_checker(candidate, pattern, allow_skips)
        path = inside(repo, repo / candidate)
        names = _test_files(manifest, candidate, pattern)
        if path.is_dir() and names and (framework == 'unittest' or _uses_unittest(repo, names)):
            selected = candidate, names
            break
    if selected is None:
        raise PolicyError('no existing unittest tests detected; select --framework unittest --tests PATH or supply --acceptance-file')
    directory, names = selected
    if len(names) > 800:
        raise PolicyError('too many baseline test files')
    roots = sorted({name.split('/')[0] for name in manifest['files']}) if inputs is None else sorted({acceptance._relative(p) for p in inputs})
    if not 1 <= len(roots) <= 64:
        raise PolicyError('select one to 64 acceptance --input paths')
    public = [name for name in manifest['files'] if any(name == root or name.startswith(root + '/') for root in roots)]
    if (not all(any(name == root or name.startswith(root + '/') for name in public) for root in roots)
            or not all(name in public for name in names)):
        raise PolicyError('acceptance inputs must exist and include every baseline test file')
    if len(public) > acceptance.MAX_FILES or sum(manifest['files'][name]['size'] for name in public) > acceptance.MAX_INPUT_BYTES:
        raise PolicyError('acceptance inventory too large; select narrower --input paths')
    options = {'framework': 'unittest', 'test_dir': directory, 'pattern': pattern,
               'allow_skips': allow_skips, 'inputs': roots}
    baseline = {name: manifest['files'][name]['sha256'] for name in sorted(names)}
    checker = unittest_checker(directory, pattern, allow_skips, baseline)
    if len(checker) > 262144:
        raise PolicyError('generated checker too large')
    contract = {'schema': 1, 'checker': 'checker.py', 'inputs': roots, 'min_checks': 1, 'timeout_s': 300}
    return options, baseline, checker, contract


def _active(repo):
    folder = _folder(repo)
    marker = acceptance._json(acceptance._file(folder / 'active.json', 65536))
    if (not isinstance(marker, dict) or set(marker) != {'schema', 'revision', 'setup_sha256'}
            or type(marker['schema']) is not int or marker['schema'] != 1
            or not isinstance(marker['revision'], str) or not re.fullmatch('[0-9a-f]{32}', marker['revision'])):
        raise PolicyError('invalid workflow setup binding')
    revision = inside(folder, folder / 'v' / marker['revision'])
    raw = acceptance._file(revision / 'setup.json', 262144)
    if _sha(raw) != marker['setup_sha256']:
        raise PolicyError('workflow setup metadata changed')
    setup = acceptance._json(raw)
    if (not isinstance(setup, dict) or setup.get('schema') != 1 or setup.get('kind') != 'codex_flow_unittest_setup'
            or not isinstance(setup.get('bound_files'), dict) or set(setup['bound_files']) != {'checker.py', 'acceptance.json'}):
        raise PolicyError('invalid workflow setup metadata')
    for name, expected in setup['bound_files'].items():
        if _sha(acceptance._file(revision / name, 262144)) != expected:
            raise PolicyError('initialized checker changed; review and use --acceptance-file or workflow init --refresh')
    contract = acceptance.load_contract(revision / 'acceptance.json')
    if (_sha(contract.raw) != setup['bound_files']['acceptance.json']
            or _sha(contract.checker_raw) != setup['bound_files']['checker.py']):
        raise PolicyError('initialized checker changed during admission')
    return revision, setup, contract


def default_contract(repo):
    repo = _root(repo)
    try:
        _, _, contract = _active(repo)
    except FileNotFoundError:
        raise PolicyError('run workflow init or select an explicit --acceptance-file') from None
    return contract


def initialize(repo, *, framework='auto', test_dir=None, pattern='test*.py', allow_skips=0,
               inputs=None, refresh=False, dry_run=False):
    repo = _root(repo)
    options, baseline, checker, contract = inspect_project(repo, framework=framework, test_dir=test_dir,
                                                          pattern=pattern, allow_skips=allow_skips, inputs=inputs)
    folder = _folder(repo)
    marker = folder / 'active.json'
    if marker.exists() and not refresh:
        revision, old, _ = _active(repo)
        if old['options'] != options:
            raise PolicyError('setup options changed; use workflow init --refresh to preserve and replace the active version')
        return {'setup_state': 'existing', 'dry_run': dry_run, 'framework': 'unittest',
                'acceptance_file': (revision / 'acceptance.json').relative_to(repo).as_posix(),
                'task_file': (revision / 'task.md').relative_to(repo).as_posix(),
                'baseline_test_files': len(old['baseline_tests']), 'model_calls': 0, 'external_calls': 0}
    if marker.is_symlink():
        raise PolicyError('linked setup binding refused')
    if dry_run:
        return {'setup_state': 'planned', 'dry_run': True, 'framework': 'unittest', 'options': options,
                'baseline_test_files': len(baseline), 'model_calls': 0, 'external_calls': 0,
                'files': ['acceptance.json', 'checker.py', 'task.md', 'setup.json']}
    # Reject an unexpected owner path before making any new revision.
    inside(repo, folder / 'v')
    revision = inside(folder, folder / 'v' / uuid.uuid4().hex)
    revision.mkdir(parents=True, exist_ok=False)
    raw_contract = json.dumps(contract, ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
    for name, raw in (('checker.py', checker), ('acceptance.json', raw_contract), ('task.md', TASK.encode('utf-8'))):
        with (revision / name).open('xb') as stream:
            stream.write(raw)
    setup = {'schema': 1, 'kind': 'codex_flow_unittest_setup', 'options': options, 'baseline_tests': baseline,
             'bound_files': {'checker.py': _sha(checker), 'acceptance.json': _sha(raw_contract)}}
    raw = json.dumps(setup, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8') + b'\n'
    with (revision / 'setup.json').open('xb') as stream:
        stream.write(raw)
    # Only the small active pointer is replaced; all old owner files remain intact.
    write_json(marker, {'schema': 1, 'revision': revision.name, 'setup_sha256': _sha(raw)})
    return {'setup_state': 'created', 'dry_run': False, 'framework': 'unittest', 'options': options,
            'baseline_test_files': len(baseline), 'acceptance_file': (revision / 'acceptance.json').relative_to(repo).as_posix(),
            'task_file': (revision / 'task.md').relative_to(repo).as_posix(),
            'model_calls': 0, 'external_calls': 0, 'previous_versions_preserved': True}
