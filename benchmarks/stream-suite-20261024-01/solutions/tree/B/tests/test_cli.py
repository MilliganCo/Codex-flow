import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
(ROOT/'.tmp').mkdir(exist_ok=True)


def cli(*args):
    return subprocess.run([sys.executable, '-m', 'ascii_tree', *args], cwd=ROOT,
                          input=b'', capture_output=True, timeout=15)


class CliTests(unittest.TestCase):
    def test_help(self):
        result = cli('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'render', result.stdout)

    def test_headless_stdout_deterministic(self):
        args = ('render', '--seed', '42', '--mode', '4d', '--angle4d', '35',
                '--yaw', '60', '--pitch', '10', '--time', '2', '--width', '80', '--height', '30')
        first, second = cli(*args), cli(*args)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr, b'')
        self.assertEqual(len(first.stdout), 81*30)
        self.assertNotIn(b'\r', first.stdout)
        self.assertNotIn(b'\x1b', first.stdout)

    def test_file_export_ascii_and_dimensions(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as directory:
            path = Path(directory)/'frame.txt'
            result = cli('render', '--seed', '42', '--mode', '3d', '--width', '100', '--height', '40', '--output', str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            content = path.read_bytes()
            self.assertEqual(len(content), 101*40)
            self.assertEqual(result.stdout, b'')
            self.assertTrue(all(c == 10 or 32 <= c <= 126 for c in content))

    def test_view_non_tty_does_not_hang_or_write_ansi(self):
        result = cli('view', '--seed', '42', '--mode', '3d')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b'')
        self.assertIn(b'interactive TTY', result.stderr)
        self.assertNotIn(b'\x1b', result.stderr)

    def test_invalid_args_fail_cleanly(self):
        for args in (('render', '--width', '0'), ('render', '--height', '251'),
                     ('render', '--zoom', 'nan'), ('render', '--mode', '5d'),
                     ('render', '--yaw', 'inf'), ('render', '--output', str(ROOT/'missing'/'f.txt'))):
            result = cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b'Traceback', result.stderr)

    def test_minimum_headless_frame(self):
        result = cli('render', '--width', '1', '--height', '1', '--mode', '4d', '--angle4d', '90')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout), 2)
