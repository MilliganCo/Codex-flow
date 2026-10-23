import os
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(os.name == "nt", "actual ConPTY integration requires Windows")
class WindowsConsoleTests(unittest.TestCase):
    def test_actual_interactive_keys_export_resize_and_shutdown(self):
        from scripts.terminal_smoke import exercise
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            report = exercise(Path(directory))
        self.assertGreaterEqual(len(report["checks"]), 15)
