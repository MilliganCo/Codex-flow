from pathlib import Path
import subprocess
import sys
import unittest

from tests.support import ROOT, temporary_directory


def cli(*arguments):
    return subprocess.run([sys.executable, '-m', 'ascii_tree', *arguments],
                          cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, timeout=10)


class CliTests(unittest.TestCase):
    def test_help_and_version(self):
        result = cli('--help')
        self.assertEqual(result.returncode, 0)
        self.assertIn(b'render', result.stdout)
        self.assertIn(b'view', result.stdout)
        self.assertEqual(cli('--version').stdout.strip(), b'1.0.0')

    def test_headless_export_deterministic_across_processes(self):
        with temporary_directory() as directory:
            first = Path(directory) / 'one.txt'
            second = Path(directory) / 'two.txt'
            arguments = ('render', '--seed', '42', '--mode', '4d', '--width', '80', '--height', '30',
                         '--yaw', '35', '--pitch', '15', '--angle4', '45', '--time', '1.25')
            for path in (first, second):
                result = cli(*arguments, '--output', str(path))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, b'')
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(len(first.read_bytes()), 81 * 30)
            stdout = cli(*arguments)
            self.assertEqual(stdout.stdout, first.read_bytes())

    def test_noninteractive_view_renders_once_and_exits(self):
        result = cli('view', '--seed', '7', '--width', '20', '--height', '10')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'No interactive TTY', result.stderr)
        self.assertEqual(len(result.stdout), 21 * 10)
        self.assertNotIn(b'\x1b', result.stdout)

    def test_minimum_headless_size(self):
        result = cli('render', '--mode', '4d', '--width', '1', '--height', '1')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stdout), 2)

    def test_bad_cli_inputs_fail_cleanly(self):
        for args in (('--width', '0'), ('--height', '201'), ('--yaw', 'nan'),
                     ('--angle4', 'inf'), ('--zoom', '0'), ('--mode', '5d')):
            with self.subTest(args=args):
                result = cli('render', *args)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn(b'Traceback', result.stderr)

    def test_unwritable_output_returns_error_without_traceback(self):
        with temporary_directory() as directory:
            result = cli('render', '--output', directory)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn(b'Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
