"""Host checks inspect checker data only; execution belongs to official SDK tests."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from codex_flow.workflow_templates import unittest_checker


def source_options(raw):
    tree = ast.parse(raw)
    options = next(node for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'OPTIONS' for t in node.targets))
    return json.loads(ast.literal_eval(options.value.args[0]))


class UnittestTemplateTests(unittest.TestCase):
    def test_default_source_is_deterministic_utf8_data_and_parses_without_execution(self):
        raw = unittest_checker()
        self.assertIs(type(raw), bytes)
        self.assertEqual(raw, unittest_checker())
        self.assertEqual(raw.decode('utf-8').encode('utf-8'), raw)
        self.assertEqual(source_options(raw), {'test_dir': 'tests', 'pattern': 'test*.py',
                                               'allow_skips': 0, 'baseline_tests': {}})
        self.assertNotIn(b'__OPTIONS_LITERAL__', raw)
        self.assertLess(len(raw), 262144)

    def test_options_are_literals_and_cannot_inject_python(self):
        pattern = "test');raise RuntimeError('template injection');#.py"
        raw = unittest_checker('qa/unit', pattern, 3)
        self.assertEqual(source_options(raw)['pattern'], pattern)
        self.assertEqual(source_options(raw)['test_dir'], 'qa/unit')
        self.assertEqual(source_options(raw)['allow_skips'], 3)
        raises = [node for node in ast.walk(ast.parse(raw)) if isinstance(node, ast.Raise)]
        self.assertTrue(raises)
        self.assertTrue(all(not isinstance(node.exc, ast.Call) or not isinstance(node.exc.func, ast.Name)
                            or node.exc.func.id != 'RuntimeError' for node in raises))

    def test_directory_rejects_escapes_aliases_private_and_windows_reserved_names(self):
        for name in ('', '.', '..', '/tests', 'C:/tests', 'C:\\tests', '//server/tests', '../tests',
                     'tests/../other', 'tests/./unit', 'tests//unit', 'tests/', 'tests.', 'tests ',
                     '.GIT/tests', 'qa/.CoDeX-FlOw', '.agents/tests', '.tmp/tests', '~/tests',
                     'tests/CON', 'tests/Aux.py', 'tests/LPT¹.txt', 'tests/a:b', 'tests/a?b',
                     'tests/a*b', 'tests/a|b', 'tests/line\nfeed', 't' * 513, None, True, 1):
            with self.subTest(name=name), self.assertRaises(ValueError):
                unittest_checker(test_dir=name)

    def test_relative_unicode_directory_is_preserved_as_data(self):
        self.assertEqual(source_options(unittest_checker('qa/проверки'))['test_dir'], 'qa/проверки')

    def test_pattern_is_one_bounded_basename_glob(self):
        for pattern in ('', '.', '..', '../test.py', '/test.py', 'tests/test.py', 'test\\test.py',
                        'C:test.py', '.GIT', 'test.py.', 'test.py ', 'test\n.py', 't' * 129,
                        None, True, 2):
            with self.subTest(pattern=pattern), self.assertRaises(ValueError):
                unittest_checker(pattern=pattern)
        self.assertEqual(source_options(unittest_checker(pattern='test_[ab]?.py'))['pattern'],
                         'test_[ab]?.py')

    def test_allow_skips_requires_strict_bounded_integer(self):
        for value in (-1, 801, True, False, 1.0, '1', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                unittest_checker(allow_skips=value)
        for value in (0, 1, 800):
            self.assertEqual(source_options(unittest_checker(allow_skips=value))['allow_skips'], value)

    def test_baseline_is_sorted_baked_data_and_does_not_follow_mutated_input(self):
        first = hashlib.sha256(b'first test bytes').hexdigest()
        second = hashlib.sha256(b'second test bytes').hexdigest()
        baseline = {'tests/test_b.py': second, 'tests/test_a.py': first}
        raw = unittest_checker(baseline_tests=baseline)
        self.assertEqual(raw, unittest_checker(baseline_tests=dict(reversed(list(baseline.items())))))
        baseline['tests/test_a.py'] = second
        self.assertEqual(source_options(raw)['baseline_tests']['tests/test_a.py'], first)
        self.assertIn(b"checks['baseline'] = baseline_matches(root)", raw)
        self.assertEqual(raw.count(b"checks['baseline'] = baseline_matches(root)"), 2)
        self.assertIn(b"digest.hexdigest() != expected", raw)
        self.assertIn(b"except (OSError, ValueError, BoundaryError)", raw)

    def test_baseline_rejects_nonpython_aliases_bad_hashes_and_unbounded_manifest(self):
        digest = 'a' * 64
        for baseline in ([], True, {'../tests/test.py': digest}, {'tests/.GIT/test.py': digest},
                         {'tests/test.txt': digest}, {'tests/test.py': 'A' * 64},
                         {'tests/test.py': 'x' * 64}, {'tests/test.py': 'a' * 63},
                         {'tests/test.py': None}, {None: digest},
                         {'tests/test.py': digest, 'Tests/TEST.py': digest},
                         {f'tests/test_{i}.py': digest for i in range(801)}):
            with self.subTest(baseline=str(baseline)[:100]), self.assertRaises(ValueError):
                unittest_checker(baseline_tests=baseline)

    def test_checker_is_self_contained_and_imports_only_standard_library(self):
        tree = ast.parse(unittest_checker())
        modules = {node.names[0].name.split('.')[0] if isinstance(node, ast.Import)
                   else node.module.split('.')[0] for node in ast.walk(tree)
                   if isinstance(node, (ast.Import, ast.ImportFrom))}
        self.assertEqual(modules, {'argparse', 'hashlib', 'json', 'os', 'pathlib', 're', 'stat',
                                   'sys', 'unittest'})
        calls = {node.func.id for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertTrue(calls.isdisjoint({'eval', 'exec', '__import__', 'compile'}))
        self.assertNotIn(str(ROOT).encode(), unittest_checker())

    def test_real_discovery_runner_and_result_drive_counts_not_text_or_exit_status(self):
        source = unittest_checker().decode()
        for fragment in ('class Loader(unittest.TestLoader)', 'class Result(unittest.TestResult)',
                         "loader.discover(str(folder), pattern=OPTIONS['pattern'])",
                         'cases = cases_in(suite)', 'isinstance(item, unittest.TestCase)',
                         'unittest.TextTestRunner(', '.run(Suite(cases))',
                         'resultclass=lambda *a, **kw: result',
                         'type(result.testsRun) is int', 'result.testsRun > 0 and passed > 0',
                         'result.testsRun + result.fixture_skipped == len(cases)',
                         'len(result.rows) == result.testsRun',
                         "checks['discovery'] = not loader.errors"):
            self.assertIn(fragment, source)
        for forbidden in ('countTestCases(', 'subprocess', 'exit_code', 'Ran ', 'traceback'):
            self.assertNotIn(forbidden, source)

    def test_failed_expected_failed_unexpected_success_and_failed_subtests_reject(self):
        tree = ast.parse(unittest_checker())
        result = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Result')
        aliases = {target.id: node.value.id for node in result.body if isinstance(node, ast.Assign)
                   and isinstance(node.value, ast.Name) for target in node.targets if isinstance(target, ast.Name)}
        for name in ('addFailure', 'addError', 'addExpectedFailure', 'addUnexpectedSuccess'):
            self.assertEqual(aliases[name], 'reject')
        self.assertIn(b'if err is not None:\n            self.reject(test)', unittest_checker())
        self.assertIn(b"self.current['status'] = 'failed'", unittest_checker())

    def test_allowed_skips_are_omitted_and_never_converted_to_passed_rows(self):
        raw = unittest_checker(allow_skips=2)
        self.assertIn(b"row['status'] != 'skipped' or OPTIONS['allow_skips'] == 0", raw)
        self.assertIn(b"max(result.skip_events, skipped) <= OPTIONS['allow_skips']", raw)
        self.assertIn(b"self.current['status'] == 'pending':\n            self.current['status'] = 'passed'", raw)
        self.assertIn(b"'skipped': sum(row['status'] == 'skipped'", raw)
        self.assertIn(b"'skip_events': result.skip_events", raw)
        self.assertIn(b"getattr(self.result, '_moduleSetUpFailed', False)", raw)
        self.assertIn(b"getattr(type(test), '_classSetupFailed', False)", raw)
        self.assertIn(b'self.result.fixture_skipped += 1', raw)
        self.assertIn(b"self.result.fixture_outcome == 'skipped'", raw)
        self.assertIn(b"'fixture_errors': result.fixture_errors", raw)

    def test_report_has_exact_schema_fresh_writes_and_bounded_failure_fallback(self):
        raw = unittest_checker()
        for fragment in (b"report = {'schema': 1, 'nonce': args.nonce, 'checks': rows}",
                         b"{'id': 'policy.' + name, 'status': 'passed' if value else 'failed'}",
                         b"MAX_BYTES = 65536", b"if len(raw) > MAX_BYTES:",
                         b"{'id': 'policy.reportbound', 'status': 'failed'}",
                         b"with args.report.open('xb')", b"with_name('details.json').open('xb')",
                         b"except BaseException as error:", b"reason = type(error).__name__[:80]"):
            self.assertIn(fragment, raw)
        self.assertNotIn(b"open('w')", raw)
        self.assertNotIn(b"str(error)", raw)

    def test_discovery_and_execution_are_bounded_with_unique_ascii_outcome_ids(self):
        raw = unittest_checker()
        for fragment in (b'MAX_TESTS = 800', b'MAX_ENTRIES = 4096', b'entries + len(todo) > MAX_ENTRIES',
                         b'len(cases) > MAX_TESTS', b'self.testsRun > MAX_TESTS', b'depth > 64',
                         b'self.collected > MAX_TESTS',
                         b'id(item) in active', b"re.sub('[^A-Za-z0-9_.:-]', '_', label)[-24:]",
                         b"'test.%04d.%s.%s' % (self.testsRun, slug, digest)"):
            self.assertIn(fragment, raw)
        # Bound the serialized representation even when every selected test passes.
        maximal_id = 'test.0800.' + 'x' * 24 + '.' + 'f' * 12
        self.assertLessEqual(len(maximal_id), 80)
        rows = [{'id': maximal_id, 'status': 'passed'} for _ in range(800)]
        rows += [{'id': 'policy.' + 'x' * 16, 'status': 'passed'} for _ in range(6)]
        raw_report = json.dumps({'schema': 1, 'nonce': 'f' * 32, 'checks': rows},
                               separators=(',', ':')).encode()
        self.assertLessEqual(len(raw_report), 65536)

    def test_application_path_is_added_only_inside_generated_checker(self):
        self.assertIn(b'sys.path.insert(0, str(root))', unittest_checker())
        self.assertIn(b'sys.dont_write_bytecode = True', unittest_checker())
        source = (ROOT / 'runtime/codex_flow/workflow_templates.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        module_imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
        imported = {alias.name for node in module_imports for alias in node.names}
        self.assertEqual(imported, {'annotations', 'json', 're'})


if __name__ == '__main__':
    unittest.main()
