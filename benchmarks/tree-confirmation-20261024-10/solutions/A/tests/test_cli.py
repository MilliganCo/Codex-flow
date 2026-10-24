from pathlib import Path
import subprocess
import sys
import unittest

from tests.support import ROOT, temporary_directory


def invoke(*args):
    return subprocess.run([sys.executable, "-m", "ascii_tree", *args], cwd=ROOT,
                          input=b"", capture_output=True, timeout=15)


class CLITests(unittest.TestCase):
    def test_help_and_no_arguments(self):
        for args in ((), ("--help",), ("view", "--help"), ("render", "--help")):
            result = invoke(*args)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn(b"usage:", result.stdout)

    def test_headless_export_dimensions_ascii_and_byte_determinism(self):
        with temporary_directory() as directory:
            path = Path(directory) / "sample.txt"
            args = ("render", "--seed", "42", "--mode", "4d", "--width", "80", "--height", "30",
                    "--yaw", "30", "--pitch", "12", "--angle4", "45", "--time", "1.25")
            result = invoke(*args, "--output", str(path))
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(b"", result.stdout)
            data = path.read_bytes()
            self.assertEqual(30 * 81, len(data))
            self.assertEqual([80] * 30, [len(row) for row in data.splitlines()])
            self.assertTrue(all(byte == 10 or 32 <= byte <= 126 for byte in data))
            self.assertEqual(data, invoke(*args).stdout)

    def test_no_tty_view_is_single_plain_frame_not_animation_spam(self):
        result = invoke("view", "--seed", "7", "--width", "80", "--height", "30", "--animate")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(30, len(result.stdout.splitlines()))
        self.assertNotIn(b"\x1b", result.stdout)
        self.assertIn(b"No interactive TTY", result.stderr)

    def test_cli_all_modes_and_tiny_frames(self):
        for mode in ("2d", "3d", "4d"):
            result = invoke("render", "--mode", mode, "--width", "1", "--height", "1")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(2, len(result.stdout))

    def test_invalid_inputs_fail_cleanly(self):
        for option, value in (("--width", "0"), ("--height", "999999"), ("--angle4", "nan"),
                              ("--zoom", "inf"), ("--aspect", "0"), ("--time", "-1")):
            result = invoke("render", option, value)
            self.assertEqual(2, result.returncode)
            self.assertNotIn(b"Traceback", result.stderr)

    def test_output_error_is_clear(self):
        with temporary_directory() as directory:
            result = invoke("render", "--output", directory)
            self.assertEqual(2, result.returncode)
            self.assertIn(b"ascii-tree:", result.stderr)
            self.assertNotIn(b"Traceback", result.stderr)
