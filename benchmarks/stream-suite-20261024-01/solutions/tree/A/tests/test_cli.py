from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / ".tmp"
TMP.mkdir(exist_ok=True)


def cli(*args):
    return subprocess.run([sys.executable, str(ROOT / "ascii-tree.py"), *args],
                          input=b"", capture_output=True, cwd=ROOT, timeout=15)


class CLITests(unittest.TestCase):
    def test_help_and_version(self):
        result = cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"render", result.stdout)
        self.assertIn(b"view", result.stdout)
        self.assertEqual(cli("--version").stdout.strip(), b"1.0.0")

    def test_module_entrypoint(self):
        result = subprocess.run([sys.executable, "-m", "ascii_tree", "render", "--width", "4", "--height", "3"],
                                cwd=ROOT, input=b"", capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout), 5 * 3)

    def test_headless_is_deterministic_and_has_clean_bytes(self):
        args = ("render", "--seed", "42", "--mode", "4d", "--width", "100", "--height", "40",
                "--yaw", "30", "--pitch", "10", "--angle4d", "45", "--time", "1.5")
        a, b = cli(*args), cli(*args)
        self.assertEqual(a.returncode, 0, a.stderr)
        self.assertEqual(a.stdout, b.stdout)
        self.assertEqual(len(a.stdout), 101 * 40)
        self.assertTrue(all(byte == 10 or 32 <= byte <= 126 for byte in a.stdout))
        self.assertEqual(a.stderr, b"")

    def test_file_export_matches_stdout_exactly(self):
        args = ("render", "--seed", "42", "--mode", "4d", "--width", "80", "--height", "30", "--angle4d", "35")
        with tempfile.TemporaryDirectory(dir=TMP) as directory:
            path = Path(directory) / "frame.txt"
            file_result = cli(*args, "--output", str(path))
            self.assertEqual(file_result.returncode, 0, file_result.stderr)
            self.assertEqual(file_result.stdout, b"")
            self.assertEqual(path.read_bytes(), cli(*args).stdout)

    def test_view_without_tty_exits_with_useful_message_and_no_ansi(self):
        result = cli("view", "--seed", "42")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"render", result.stderr)
        self.assertNotIn(b"\x1b", result.stderr)

    def test_invalid_input_is_finite_failure_without_traceback(self):
        for args in (("--width", "0"), ("--height", "201"), ("--yaw", "nan"),
                     ("--angle4d", "inf"), ("--mode", "5d"), ("--zoom", "99")):
            result = cli("render", *args)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b"Traceback", result.stderr)

    def test_minimal_headless_frame(self):
        result = cli("render", "--mode", "4d", "--width", "1", "--height", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout), 2)

    def test_large_but_finite_time_and_angles_do_not_overflow(self):
        for mode in ("2d", "4d"):
            result = cli("render", "--mode", mode, "--time", "1e308", "--yaw", "1e308",
                         "--angle4d", "1e308", "--width", "4", "--height", "3")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(result.stdout), 15)

    def test_output_error_is_reported(self):
        result = cli("render", "--output", str(ROOT / "absent-parent" / "frame.txt"))
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"ascii-tree:", result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)
