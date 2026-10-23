from pathlib import Path
import subprocess
import sys
import unittest

from tests.support import ROOT, temporary_directory


def invoke(*args):
    return subprocess.run([sys.executable, "-m", "ascii_tree", *args], cwd=ROOT,
                          input=b"", capture_output=True, timeout=10)


class CliTests(unittest.TestCase):
    def test_help(self):
        result = invoke("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"view", result.stdout)
        self.assertIn(b"render", result.stdout)

    def test_independent_processes_are_byte_deterministic(self):
        for mode in ("2d", "3d", "4d"):
            args = ("render", "--seed", "42", "--mode", mode, "--width", "80",
                    "--height", "30", "--yaw", "67", "--pitch", "12",
                    "--angle4d", "35", "--time", "1.25")
            a, b = invoke(*args), invoke(*args)
            self.assertEqual((a.returncode, b.returncode), (0, 0))
            self.assertEqual(a.stdout, b.stdout)
            self.assertEqual(len(a.stdout), 81 * 30)
            self.assertEqual(a.stderr, b"")

    def test_real_output_file_is_ascii_and_same_as_stdout(self):
        with temporary_directory() as directory:
            path = Path(directory) / "sample.txt"
            args = ("render", "--mode", "4d", "--angle4d", "45", "--width", "100", "--height", "40")
            result = invoke(*args, "--output", str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            data = path.read_bytes()
            self.assertEqual(data, invoke(*args).stdout)
            self.assertEqual(len(data.splitlines()), 40)
            self.assertTrue(all(len(line) == 100 for line in data.splitlines()))
            self.assertTrue(all(b == 10 or 32 <= b <= 126 for b in data))

    def test_non_tty_view_returns_one_plain_frame(self):
        result = invoke("view", "--seed", "7", "--width", "1", "--height", "1")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stdout), 2)
        self.assertNotIn(b"\x1b", result.stdout)
        self.assertIn(b"No interactive TTY", result.stderr)

    def test_invalid_parameters_exit_clearly(self):
        for args in (("--width", "0"), ("--height", "501"), ("--yaw", "nan"),
                     ("--zoom", "0"), ("--angle4d", "inf"), ("--mode", "5d")):
            with self.subTest(args=args):
                result = invoke("render", *args)
                self.assertEqual(result.returncode, 2)
                self.assertTrue(result.stderr)
                self.assertEqual(result.stdout, b"")

    def test_output_io_error_is_clean(self):
        with temporary_directory() as directory:
            result = invoke("render", "--output", str(Path(directory) / "missing" / "frame.txt"))
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"ascii-tree:", result.stderr)
            self.assertNotIn(b"Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
