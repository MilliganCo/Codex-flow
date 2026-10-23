from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ascii_tree.cli import main


WORKSPACE = Path(__file__).resolve().parents[1]


def command(*args):
    return subprocess.run([sys.executable, "-m", "ascii_tree", *args], cwd=WORKSPACE,
                          stdin=subprocess.DEVNULL, capture_output=True, timeout=15)


class CliTests(unittest.TestCase):
    def test_help_and_version_start_and_exit_cleanly(self):
        for args in (("--help",), ("view", "--help"), ("render", "--help"), ("--version",)):
            result = command(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(result.stdout)
            self.assertEqual(result.stderr, b"")

    def test_headless_all_modes_exact_bytes_and_determinism(self):
        for mode in ("2d", "3d", "4d"):
            args = ("render", "--seed", "42", "--mode", mode, "--width", "80", "--height", "30",
                    "--yaw", "35", "--pitch", "15", "--angle4", "48", "--time", "1.25")
            a, b = command(*args), command(*args)
            self.assertEqual(a.returncode, 0, a.stderr)
            self.assertEqual(a.stdout, b.stdout)
            self.assertEqual(len(a.stdout), 81 * 30)
            self.assertTrue(all(c == 10 or 32 <= c <= 126 for c in a.stdout))
            self.assertEqual(a.stderr, b"")

    def test_file_export_matches_stdout_without_ansi_or_crlf(self):
        with tempfile.TemporaryDirectory(dir=WORKSPACE / ".tmp") as temporary:
            output = Path(temporary) / "frame.txt"
            args = ("render", "--seed", "42", "--mode", "4d", "--angle4", "35")
            result = command(*args, "--output", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, b"")
            self.assertEqual(output.read_bytes(), command(*args).stdout)
            self.assertEqual(len(output.read_bytes()), 101 * 40)

    def test_noninteractive_view_exits_with_actionable_message(self):
        result = command("view", "--seed", "42")
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"TTY", result.stderr)
        self.assertIn(b"render", result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertEqual(result.stdout, b"")

    def test_bad_arguments_fail_fast_without_traceback(self):
        for args in (("--width", "0"), ("--height", "-1"), ("--width", "501"),
                     ("--angle4", "nan"), ("--yaw", "inf"), ("--zoom", "9"),
                     ("--aspect", "0"), ("--plane", "xx"), ("--mode", "5d")):
            with self.subTest(args=args):
                result = command("render", *args)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn(b"Traceback", result.stderr)

    def test_tiny_headless_frame(self):
        result = command("render", "--width", "1", "--height", "1", "--mode", "4d", "--angle4", "90")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout), 2)

    def test_invalid_output_path_is_reported(self):
        with tempfile.TemporaryDirectory(dir=WORKSPACE / ".tmp") as temporary:
            result = command("render", "--output", str(Path(temporary) / "missing" / "frame.txt"))
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"ascii-tree:", result.stderr)
            self.assertNotIn(b"Traceback", result.stderr)

    def test_cli_ctrl_c_returns_130(self):
        with patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True), patch("ascii_tree.cli.run_view", side_effect=KeyboardInterrupt):
            self.assertEqual(main(["view"]), 130)
