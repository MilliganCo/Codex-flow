import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ascii_tree.cli import main
from ascii_tree.terminal import TerminalError
from tests.support import ROOT, TEMP_ROOT


def command(*args):
    return subprocess.run([sys.executable, "-m", "ascii_tree", *args], cwd=ROOT,
                          input=b"", capture_output=True, timeout=15)


class CLITests(unittest.TestCase):
    def test_help_and_version_startup(self):
        for args in (("--help",), ("view", "--help"), ("render", "--help"), ("--version",)):
            with self.subTest(args=args):
                result = command(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout)
                self.assertNotIn(b"Traceback", result.stderr)

    def test_headless_output_is_exact_and_reproducible(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory) / "nested" / "tree.txt"
            args = ("render", "--seed", "42", "--mode", "4d", "--width", "80", "--height", "30",
                    "--yaw", "35", "--pitch", "12", "--angle4", "40", "--time", "1.25")
            result = command(*args, "--output", str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, b"")
            first = path.read_bytes()
            result = command(*args, "--output", "-")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, first)
            self.assertEqual(len(first), 81 * 30)
            self.assertEqual(len(first.splitlines()), 30)
            self.assertTrue(all(len(line) == 80 for line in first.splitlines()))
            self.assertTrue(all(c == 10 or 32 <= c <= 126 for c in first))
            self.assertNotIn(b"\r", first)
            self.assertNotIn(b"\x1b", first)

    def test_noninteractive_view_and_default_start_do_not_hang(self):
        for args in ((), ("view", "--mode", "2d", "--width", "20", "--height", "8")):
            result = command(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(b"No interactive TTY", result.stderr)
            self.assertNotIn(b"\x1b", result.stdout)
            self.assertEqual(len(result.stdout.splitlines()), 40 if not args else 8)

    def test_invalid_cli_and_minimum_size(self):
        for args in (("render", "--width", "0"), ("render", "--angle4", "nan"),
                     ("render", "--zoom", "inf"), ("view", "--fps", "nan"),
                     ("view", "--fps", "100"), ("render", "--seed", "oops")):
            with self.subTest(args=args):
                result = command(*args)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn(b"Traceback", result.stderr)
        result = command("render", "--mode", "4d", "--width", "1", "--height", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout), 2)

    def test_file_write_error_is_reported(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            result = command("render", "--output", directory)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"ascii-tree:", result.stderr)
            self.assertNotIn(b"Traceback", result.stderr)

    def test_interactive_cli_dispatch_and_ctrl_c_exit_code(self):
        input_stream, output = io.StringIO(), io.StringIO()
        input_stream.isatty = lambda: True
        output.isatty = lambda: True
        with patch("ascii_tree.cli.sys.stdin", input_stream), patch("ascii_tree.cli.sys.stdout", output):
            with patch("ascii_tree.cli.run_interactive", return_value=0) as run:
                self.assertEqual(main(["view", "--seed", "7", "--mode", "4d"]), 0)
                self.assertEqual(run.call_args.args[0].tree.seed, 7)
                self.assertEqual(run.call_args.args[0].options.mode, "4d")
            with patch("ascii_tree.cli.run_interactive", side_effect=KeyboardInterrupt):
                self.assertEqual(main(["view"]), 130)
            with patch("ascii_tree.cli.run_interactive", side_effect=TerminalError("test console error")), \
                 patch("ascii_tree.cli.sys.stderr", io.StringIO()) as errors:
                self.assertEqual(main(["view"]), 2)
                self.assertIn("test console error", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
