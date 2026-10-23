from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ascii_tree.geometry import generate_tree
from ascii_tree.render import RenderOptions, frame_bytes

ROOT = Path(__file__).resolve().parents[1]


def cli(*args):
    return subprocess.run([sys.executable, "-m", "ascii_tree", *args], cwd=ROOT,
                          input=b"", capture_output=True, timeout=10)


class CliTests(unittest.TestCase):
    def test_global_and_subcommand_help(self):
        for args in (("--help",), ("render", "--help"), ("view", "--help")):
            result = cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(b"usage:", result.stdout)

    def test_headless_stdout_is_exact_frame(self):
        result = cli("render", "--seed", "42", "--mode", "4d", "--width", "80",
                     "--height", "30", "--yaw", "75", "--pitch", "12", "--angle4", "35", "--time", "1.5")
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = frame_bytes(generate_tree(42), RenderOptions(mode="4d", width=80, height=30,
                                yaw=75, pitch=12, angle4=35, time=1.5))
        self.assertEqual(result.stdout, expected)
        self.assertEqual(result.stderr, b"")

    def test_export_and_repeated_cli_are_byte_identical(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            output = Path(directory) / "sample.txt"
            args = ("render", "--mode", "3d", "--seed", "42")
            written = cli(*args, "--output", str(output))
            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertEqual(written.stdout, b"")
            self.assertEqual(output.read_bytes(), cli(*args).stdout)
            self.assertEqual(output.read_bytes(), cli(*args).stdout)

    def test_noninteractive_view_refuses_without_ansi_or_hanging(self):
        result = cli("view", "--seed", "42")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"TTY", result.stderr)
        self.assertIn(b"render", result.stderr)
        self.assertNotIn(b"\x1b", result.stderr)

    def test_invalid_arguments_have_clear_errors(self):
        for args in (("--width", "0"), ("--height", "201"), ("--yaw", "nan"),
                     ("--zoom", "0"), ("--mode", "5d")):
            result = cli("render", *args)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"error:", result.stderr)
            self.assertNotIn(b"Traceback", result.stderr)

    def test_write_error_is_reported(self):
        result = cli("render", "--output", str(ROOT / ".tmp" / "not-created" / "sample.txt"))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(b"Traceback", result.stderr)

    def test_minimum_headless_cli_frame(self):
        result = cli("render", "--width", "1", "--height", "1", "--mode", "4d", "--xw", "90")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout), 2)
