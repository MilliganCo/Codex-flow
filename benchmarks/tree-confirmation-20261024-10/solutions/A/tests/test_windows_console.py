import json
import os
import subprocess
import sys
import unittest

from tests.support import ROOT, temporary_directory


@unittest.skipUnless(os.name == "nt", "native Windows console test; use manual TTY check on POSIX")
class NativeWindowsConsoleTests(unittest.TestCase):
    def test_real_console_input_resize_animation_export_quit_and_ctrl_c(self):
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0  # SW_HIDE: this test must not open a visible window.
        with temporary_directory() as directory:
            result = subprocess.run([sys.executable, "-m", "tests.windows_console_driver", directory],
                                    cwd=ROOT, input=b"", capture_output=True, timeout=15,
                                    creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup)
        self.assertEqual(0, result.returncode, result.stderr.decode(errors="replace"))
        report = json.loads(result.stdout)
        self.assertTrue(report["native_console"])
        self.assertTrue(report["console_mode_restored"])
        self.assertEqual(130, report["ctrl_c_code"])
        self.assertGreaterEqual(report["frames"], 16)
        self.assertIn([40, 12], report["sizes"])
