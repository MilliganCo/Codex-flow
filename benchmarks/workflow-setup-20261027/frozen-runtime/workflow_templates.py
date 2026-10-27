"""Generate checker bytes; never import or execute project/checker code on the host.

The unittest template preserves baseline test bytes while allowing added tests. It
attests ordinary unittest outcomes, not resistance to adversarial Python tests.
Only the official SDK sandbox may execute the generated source.
"""
from __future__ import annotations

import json
import re

_RESERVED = {'.git', '.codex-flow', '.codex', '.agents', '.home', '.tmp', '~'}
_DEVICES = {'con', 'prn', 'aux', 'nul', 'conin$', 'conout$'} | {
    prefix + digit for prefix in ('com', 'lpt') for digit in '123456789¹²³'}


def _relative(value: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 512
            or any(c in value for c in '\\:<>"|?*') or any(ord(c) < 32 for c in value)):
        raise ValueError('test paths must be bounded relative POSIX paths')
    if any(not p or p in ('.', '..') or p.casefold() in _RESERVED or p.endswith(('.', ' '))
           or p.split('.')[0].casefold() in _DEVICES for p in value.split('/')):
        raise ValueError('test path alias, reserved component or escape refused')
    return value


def unittest_checker(test_dir: str = 'tests', pattern: str = 'test*.py', allow_skips: int = 0,
                     baseline_tests: dict[str, str] | None = None) -> bytes:
    """Return one self-contained SDK-only checker with immutable option literals.

    ``allow_skips`` bounds skipped cases and skip events (including subtests).
    They never count as passes. Missing/changed baseline Python files fail acceptance;
    new test files are permitted. Baselines are integrity checks, not a Python
    security boundary. Invalid template options raise ``ValueError``.
    """
    _relative(test_dir)
    if (not isinstance(pattern, str) or not pattern or len(pattern) > 128
            or any(c in pattern for c in '/\\:<>"|') or any(ord(c) < 32 for c in pattern)
            or pattern in ('.', '..') or pattern.endswith(('.', ' '))
            or pattern.casefold() in _RESERVED):
        raise ValueError('unittest pattern must be a bounded basename glob')
    if type(allow_skips) is not int or not 0 <= allow_skips <= 800:
        raise ValueError('allow_skips must be an integer from 0 to 800')
    baseline = {} if baseline_tests is None else baseline_tests
    if not isinstance(baseline, dict) or len(baseline) > 800:
        raise ValueError('baseline_tests must be a bounded path-to-SHA256 dictionary')
    seen: set[str] = set()
    for name, digest in baseline.items():
        _relative(name)
        if (not name.endswith('.py') or name.casefold() in seen or not isinstance(digest, str)
                or re.fullmatch('[0-9a-f]{64}', digest) is None):
            raise ValueError('invalid baseline test path, alias or SHA256')
        seen.add(name.casefold())
    options = json.dumps({'test_dir': test_dir, 'pattern': pattern, 'allow_skips': allow_skips,
                          'baseline_tests': baseline}, sort_keys=True, ensure_ascii=True)
    return (_SOURCE.replace('__OPTIONS_LITERAL__', repr(options))).encode('utf-8')


_SOURCE = '''"""SDK-only unittest acceptance; not an adversarial Python security boundary."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import unittest

OPTIONS = json.loads(__OPTIONS_LITERAL__)
MAX_TESTS = 800
MAX_ENTRIES = 4096
MAX_BYTES = 65536
MAX_FILE_BYTES = 67108864


class BoundaryError(Exception):
    pass


def inside(root, path):
    target = path.resolve(strict=True)
    if target != root and root not in target.parents:
        raise BoundaryError('path')
    if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 1024:
        raise BoundaryError('link')
    return target


def inventory(root, folder):
    todo, entries = [folder], 0
    while todo:
        path = todo.pop()
        inside(root, path)
        entries += 1
        if entries > MAX_ENTRIES:
            raise BoundaryError('discovery_bound')
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            with os.scandir(path) as children:
                for child in children:
                    entries += 1
                    if entries + len(todo) > MAX_ENTRIES:
                        raise BoundaryError('discovery_bound')
                    todo.append(Path(child.path))
        elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise BoundaryError('file')


def baseline_matches(root):
    for name, expected in OPTIONS['baseline_tests'].items():
        path = root / name
        try:
            inside(root, path)
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_FILE_BYTES:
                return False
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(65536), b''):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                return False
        except (OSError, ValueError, BoundaryError):
            return False
    return True


def cases_in(suite):
    cases, active = [], set()
    def visit(item, depth=0):
        if depth > 64:
            raise BoundaryError('suite_depth')
        if isinstance(item, unittest.TestSuite):
            if id(item) in active:
                raise BoundaryError('suite_cycle')
            active.add(id(item))
            for child in item:
                visit(child, depth + 1)
            active.remove(id(item))
        elif isinstance(item, unittest.TestCase):
            cases.append(item)
            if len(cases) > MAX_TESTS:
                raise BoundaryError('test_bound')
        else:
            raise BoundaryError('malformed_suite')
    visit(suite)
    return cases


class Loader(unittest.TestLoader):
    collected = 0
    def getTestCaseNames(self, testCaseClass):
        names = super().getTestCaseNames(testCaseClass)
        self.collected += len(names) or int(hasattr(testCaseClass, 'runTest'))
        if self.collected > MAX_TESTS:
            raise BoundaryError('test_bound')
        return names


class Suite(unittest.TestSuite):
    def run(self, result, debug=False):
        self.result = result
        return super().run(result, debug)
    def __iter__(self):
        for test in super().__iter__():
            before = self.result.testsRun
            yield test
            if self.result.testsRun == before and self.result.fixture_outcome == 'skipped' and (
                    getattr(self.result, '_moduleSetUpFailed', False)
                    or getattr(type(test), '_classSetupFailed', False)):
                self.result.fixture_skipped += 1


class Result(unittest.TestResult):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.rows = []
        self.current = None
        self.skip_events = 0
        self.fixture_skipped = self.fixture_errors = 0
        self.fixture_outcome = None
        self.bad = False

    def startTest(self, test):
        super().startTest(test)
        if type(self.testsRun) is not int or self.testsRun > MAX_TESTS:
            raise BoundaryError('execution_bound')
        label = str(test.id())[:512]
        slug = re.sub('[^A-Za-z0-9_.:-]', '_', label)[-24:]
        digest = hashlib.sha256(label.encode('utf-8', 'replace')).hexdigest()[:12]
        self.current = {'id': 'test.%04d.%s.%s' % (self.testsRun, slug, digest), 'status': 'pending'}
        self.rows.append(self.current)

    def stopTest(self, test):
        if self.current is not None and self.current['status'] == 'pending':
            self.current['status'] = 'failed'
            self.bad = True
        self.current = None
        super().stopTest(test)

    def addSuccess(self, test):
        if self.current is not None and self.current['status'] == 'pending':
            self.current['status'] = 'passed'

    def reject(self, test, *args):
        self.bad = True
        if self.current is None:
            self.fixture_errors += 1
            self.fixture_outcome = 'failed'
        if self.current is not None:
            self.current['status'] = 'failed'

    addFailure = reject
    addError = reject
    addExpectedFailure = reject
    addUnexpectedSuccess = reject

    def addSkip(self, test, reason):
        self.skip_events += 1
        if self.current is None:
            self.fixture_outcome = 'skipped'
        if self.current is not None and self.current['status'] != 'failed':
            self.current['status'] = 'skipped'

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self.reject(test)

    def wasSuccessful(self):
        return not self.bad


class Sink:
    def write(self, text):
        return len(text)
    def flush(self):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--nonce', required=True)
    args = parser.parse_args()
    checks = {name: False for name in ('baseline', 'discovery', 'testbound', 'nonempty', 'skipallowance', 'overallresult')}
    result, cases, reason = Result(), [], ''
    try:
        root = args.workspace.resolve(strict=True)
        folder = inside(root, root / OPTIONS['test_dir'])
        if not folder.is_dir():
            raise BoundaryError('test_directory')
        checks['baseline'] = baseline_matches(root)
        if not checks['baseline']:
            raise BoundaryError('baseline')
        inventory(root, folder)
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(root))
        loader = Loader()
        suite = loader.discover(str(folder), pattern=OPTIONS['pattern'])
        cases = cases_in(suite)
        checks['discovery'] = not loader.errors
        checks['testbound'] = len(cases) <= MAX_TESTS
        unittest.TextTestRunner(stream=Sink(), resultclass=lambda *a, **kw: result, verbosity=0).run(Suite(cases))
        passed = sum(row['status'] == 'passed' for row in result.rows)
        skipped = sum(row['status'] == 'skipped' for row in result.rows) + result.fixture_skipped
        checks['nonempty'] = type(result.testsRun) is int and result.testsRun > 0 and passed > 0
        checks['skipallowance'] = max(result.skip_events, skipped) <= OPTIONS['allow_skips']
        checks['overallresult'] = (result.wasSuccessful() and result.testsRun + result.fixture_skipped == len(cases)
                                   and len(result.rows) == result.testsRun
                                   and all(row['status'] in ('passed', 'skipped') for row in result.rows))
        checks['baseline'] = baseline_matches(root)
    except BaseException as error:
        reason = type(error).__name__[:80]
        checks['overallresult'] = False
    rows = [row for row in result.rows if row['status'] != 'skipped' or OPTIONS['allow_skips'] == 0]
    rows = [dict(row, status='failed' if row['status'] == 'pending' else row['status']) for row in rows]
    rows += [{'id': 'policy.' + name, 'status': 'passed' if value else 'failed'} for name, value in checks.items()]
    report = {'schema': 1, 'nonce': args.nonce, 'checks': rows}
    raw = json.dumps(report, ensure_ascii=True, separators=(',', ':')).encode('utf-8')
    if len(raw) > MAX_BYTES:
        raw = json.dumps({'schema': 1, 'nonce': args.nonce, 'checks': [
            {'id': 'policy.reportbound', 'status': 'failed'}]}, separators=(',', ':')).encode('utf-8')
    with args.report.open('xb') as stream:
        stream.write(raw)
    details = {'schema': 1, 'collected': len(cases), 'executed': result.testsRun,
               'passed': sum(row['status'] == 'passed' for row in result.rows),
               'failed': sum(row['status'] in ('failed', 'pending') for row in result.rows),
               'skipped': sum(row['status'] == 'skipped' for row in result.rows) + result.fixture_skipped,
               'skip_events': result.skip_events, 'fixture_errors': result.fixture_errors,
               'allow_skips': OPTIONS['allow_skips'], 'reason': reason}
    try:
        with args.report.with_name('details.json').open('xb') as stream:
            stream.write(json.dumps(details, ensure_ascii=True).encode('utf-8'))
    except OSError:
        pass


if __name__ == '__main__':
    main()
'''
