from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ascii_tree.cli import main

ROOT = Path(__file__).resolve().parent.parent


def cli(*args):
    return subprocess.run([sys.executable, "-m", "ascii_tree", *args], cwd=ROOT,
                          input=b"", capture_output=True, timeout=15)


class CLITests(unittest.TestCase):
    def test_help(self):
        result = cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"render", result.stdout)
        self.assertIn(b"view", result.stdout)

    def test_interactive_start_preserves_signed_pitch(self):
        with patch("ascii_tree.cli.sys.stdin.isatty", return_value=True), \
             patch("ascii_tree.cli.sys.stdout.isatty", return_value=True), \
             patch("ascii_tree.cli.run_interactive", return_value=0) as run:
            self.assertEqual(main(["view"]), 0)
        state = run.call_args.args[0]
        self.assertEqual(state.view.pitch, -7)
        state.key("up")
        self.assertEqual(state.view.pitch, -1)

    def test_headless_render_in_separate_processes_deterministic(self):
        args = ("render", "--seed", "42", "--mode", "4d", "--angle4d", "35", "--yaw", "70",
                "--pitch", "12", "--width", "80", "--height", "30", "--time", "1.25")
        a, b = cli(*args), cli(*args)
        self.assertEqual((a.returncode, b.returncode), (0, 0))
        self.assertEqual(a.stderr, b"")
        self.assertEqual(a.stdout, b.stdout)
        self.assertEqual(len(a.stdout), 81 * 30)
        self.assertNotIn(b"\r", a.stdout)
        self.assertNotIn(b"\x1b", a.stdout)

    def test_headless_file_output(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            path = Path(directory) / "sample.txt"
            result = cli("render", "--mode", "2d", "--output", str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, b"")
            data = path.read_bytes()
            self.assertEqual(len(data), 101 * 40)
            self.assertTrue(all(32 <= byte <= 126 or byte == 10 for byte in data))

    def test_noninteractive_view_is_finite_and_informative(self):
        result = cli("view", "--seed", "42", "--mode", "3d")
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"interactive TTY", result.stderr)
        self.assertEqual(result.stdout, b"")
        self.assertNotIn(b"\x1b", result.stderr)

    def test_minimum_size(self):
        result = cli("render", "--mode", "4d", "--width", "1", "--height", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout), 2)

    def test_invalid_arguments_fail_cleanly(self):
        cases = (("--width", "0"), ("--height", "9999999"), ("--yaw", "nan"),
                 ("--angle4d", "inf"), ("--zoom", "0"), ("--mode", "5d"),
                 ("--output", ".tmp/nonexistent/parent/frame.txt"))
        for case in cases:
            with self.subTest(case=case):
                result = cli("render", *case)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn(b"Traceback", result.stderr)
                self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main()
