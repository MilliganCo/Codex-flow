from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def cli(*args):
    return subprocess.run([sys.executable, "-m", "ascii_tree", *args], cwd=ROOT,
                          input=b"", capture_output=True, timeout=10)


class CliTests(unittest.TestCase):
    def test_help_and_version(self):
        result = cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"render", result.stdout)
        self.assertEqual(cli("--version").stdout.strip(), b"1.0.0")

    def test_headless_all_modes(self):
        for mode in ("2d", "3d", "4d"):
            result = cli("render", "--mode", mode, "--width", "80", "--height", "30")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, b"")
            self.assertEqual(len(result.stdout), 81 * 30)
            self.assertNotIn(b"\r", result.stdout)
            self.assertNotIn(b"\x1b", result.stdout)

    def test_same_arguments_produce_identical_file_and_stdout_bytes(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        args = ("render", "--seed", "42", "--mode", "4d", "--yaw", "19", "--pitch", "-12",
                "--angle4", "37", "--time", "1.25")
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            output = Path(directory) / "frame.txt"
            result = cli(*args, "--output", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, b"")
            data = output.read_bytes()
            self.assertEqual(data, cli(*args).stdout)
            self.assertEqual(data, cli(*args).stdout)
            self.assertEqual(len(data), 101 * 40)

    def test_noninteractive_view_outputs_one_frame_and_exits(self):
        viewed = cli("view", "--width", "12", "--height", "5")
        rendered = cli("render", "--width", "12", "--height", "5")
        self.assertEqual(viewed.returncode, 0, viewed.stderr)
        self.assertIn(b"No interactive TTY", viewed.stderr)
        self.assertEqual(viewed.stdout, rendered.stdout)

    def test_minimum_headless_frame(self):
        result = cli("render", "--mode", "4d", "--angle4", "90", "--width", "1", "--height", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout), 2)

    def test_invalid_parameters_are_clear_finite_failures(self):
        for args in (("--width", "0"), ("--angle4", "nan"), ("--zoom", "99"), ("--mode", "5d")):
            result = cli("render", *args)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"error:", result.stderr)
            self.assertEqual(result.stdout, b"")

    def test_file_error_is_reported_without_traceback(self):
        result = cli("render", "--output", str(ROOT / ".tmp" / "missing-dir" / "frame.txt"))
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"ascii-tree:", result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)
