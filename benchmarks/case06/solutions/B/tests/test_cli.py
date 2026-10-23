from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def cli(*args):
    return subprocess.run([sys.executable, "-m", "ascii_tree", *args], cwd=ROOT,
                          input=b"", capture_output=True, timeout=15)


class CliTests(unittest.TestCase):
    def test_help(self):
        for args in (("--help",), ("view", "--help"), ("render", "--help")):
            result = cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(b"usage:", result.stdout)

    def test_headless_render_exact_bytes_twice(self):
        args = ("render", "--seed", "42", "--mode", "4d", "--angle4d", "35", "--width", "80", "--height", "30", "--time", "1.5")
        first, second = cli(*args), cli(*args)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(len(first.stdout), 81 * 30)
        self.assertNotIn(b"\r", first.stdout)
        self.assertEqual(len(first.stdout.splitlines()), 30)
        self.assertTrue(all(len(row) == 80 for row in first.stdout.splitlines()))
        self.assertNotIn(b"\x1b", first.stdout)

    def test_txt_export_lf_ascii_without_ansi(self):
        temp_root = ROOT / ".tmp"
        temp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as temp:
            output = Path(temp) / "tree.txt"
            result = cli("render", "--seed", "42", "--mode", "3d", "--output", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, b"")
            raw = output.read_bytes()
            self.assertEqual(len(raw), 101 * 40)
            self.assertTrue(all(value == 10 or 32 <= value <= 126 for value in raw))
            self.assertNotIn(b"\r", raw)

    def test_view_without_tty_exits_instead_of_hanging(self):
        result = cli("view", "--seed", "42")
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"TTY", result.stderr)
        self.assertEqual(result.stdout, b"")

    def test_bad_args_and_unwritable_output_are_clean_errors(self):
        for args in (("render", "--width", "0"), ("render", "--yaw", "nan"),
                     ("render", "--height", "1000000"), ("render", "--mode", "5d"),
                     ("render", "--output", "no-such-dir/frame.txt")):
            result = cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b"Traceback", result.stderr)

    def test_minimal_headless_cli(self):
        result = cli("render", "--width", "1", "--height", "1", "--mode", "4d")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertEqual(len(result.stdout.splitlines()[0]), 1)


if __name__ == "__main__":
    unittest.main()
