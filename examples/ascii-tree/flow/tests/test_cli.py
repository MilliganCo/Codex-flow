import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def cli(*args):
    return subprocess.run([sys.executable, "-m", "ascii_tree", *args], input=b"", capture_output=True, timeout=15)


class CLITests(unittest.TestCase):
    def test_help(self):
        result = cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"render", result.stdout)
        self.assertIn(b"view", result.stdout)

    def test_headless_stdout_deterministic_bytes(self):
        for mode in ("2d", "3d", "4d"):
            args = ("render", "--seed", "42", "--mode", mode, "--width", "80", "--height", "30", "--angle4d", "37", "--time", "2.5")
            a, b = cli(*args), cli(*args)
            self.assertEqual(a.returncode, 0, a.stderr)
            self.assertEqual(b.returncode, 0, b.stderr)
            self.assertEqual(a.stdout, b.stdout)
            self.assertEqual(len(a.stdout), 81 * 30)
            self.assertEqual(a.stderr, b"")
            self.assertNotIn(b"\r", a.stdout)

    def test_txt_export_and_minimal_size(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = Path(directory) / "sample.txt"
            result = cli("render", "--mode", "4d", "--output", str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            data = path.read_bytes()
            self.assertEqual(len(data), 4040)
            self.assertNotIn(b"\x1b", data)
            self.assertTrue(data.isascii())
            result = cli("render", "--width", "1", "--height", "1")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(result.stdout), 2)

    def test_noninteractive_view_fails_fast_with_guidance(self):
        result = cli("view")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"TTY", result.stderr)
        self.assertIn(b"render", result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)

    def test_invalid_options_and_write_error(self):
        for args in (("render", "--width", "0"), ("render", "--yaw", "nan"),
                     ("render", "--mode", "5d"), ("render", "--output", "does-not-exist/frame.txt")):
            result = cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(b"Traceback", result.stderr)

    def test_powershell_entrypoint(self):
        if os.name != "nt":
            self.skipTest("PowerShell wrapper is Windows-specific")
        result = subprocess.run(["pwsh", "-NoProfile", "-File", "ascii-tree.ps1", "render", "--width", "10", "--height", "4"], capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 4)
