from dataclasses import replace
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ascii_tree.cli import main
from ascii_tree.export import write_frame
from ascii_tree.model import generate_tree
from ascii_tree.render import Camera
from ascii_tree.terminal import Explorer, Terminal, compose, export_frame, run

ROOT = Path(__file__).resolve().parents[1]


def setUpModule():
    (ROOT / ".tmp").mkdir(exist_ok=True)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.state = Explorer(generate_tree(42), Camera())

    def test_all_controls(self):
        self.state.key("3")
        self.state.key("]")
        self.assertEqual(self.state.camera.angle4d, 8)
        self.state.key("[")
        self.assertEqual(self.state.camera.angle4d, 0)
        self.state.key("right")
        self.assertEqual(self.state.camera.yaw, 33)
        self.state.key("up")
        self.assertEqual(self.state.camera.pitch, -1)
        self.state.key("+")
        self.assertGreater(self.state.camera.zoom, 1)
        self.state.key("-")
        self.assertAlmostEqual(self.state.camera.zoom, 1)
        self.state.key(" ")
        self.state.tick(.1)
        self.assertAlmostEqual(self.state.camera.time, .1)
        self.state.key(" ")
        self.state.tick(.1)
        self.assertAlmostEqual(self.state.camera.time, .1)
        self.state.key("h")
        self.assertTrue(self.state.help_open)
        self.state.key("?")
        self.assertFalse(self.state.help_open)
        self.state.key("r")
        self.assertEqual(self.state.camera, Camera(mode="4d"))
        self.state.key("q")
        self.assertFalse(self.state.running)

    def test_2d_ignores_camera_but_animates(self):
        self.state.key("1")
        before = self.state.camera
        self.state.key("right")
        self.state.key("]")
        self.assertEqual(self.state.camera, before)
        self.state.key(" ")
        self.state.tick(.1)
        self.assertGreater(self.state.camera.time, 0)

    def test_zoom_tilt_and_time_bounds(self):
        for _ in range(100):
            self.state.key("+")
            self.state.key("up")
        self.assertEqual(self.state.camera.zoom, 8)
        self.assertEqual(self.state.camera.pitch, 85)
        for _ in range(100):
            self.state.key("-")
            self.state.key("down")
        self.assertEqual(self.state.camera.zoom, .1)
        self.assertEqual(self.state.camera.pitch, -85)
        for seconds in (-1, math.inf, math.nan):
            with self.assertRaises(ValueError):
                self.state.tick(seconds)

    def test_compose_resize_help_and_tiny(self):
        for key in ("1", "2", "3"):
            self.state.key(key)
            for width, height in ((100, 40), (80, 30), (1, 1), (5, 2), (23, 7)):
                lines, frame = compose(self.state, width, height)
                self.assertLessEqual(len(lines), height)
                self.assertTrue(all(len(row) == width for row in frame.splitlines()))
            self.state.key("h")
            lines, _ = compose(self.state, 100, 40)
            self.assertIn("CONTROLS", "\n".join(lines))
            self.state.key("h")

    def test_export_is_exact_and_no_overwrite(self):
        _, frame = compose(self.state, 100, 40)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            first = export_frame(Path(directory), self.state, frame)
            second = export_frame(Path(directory), self.state, frame)
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), frame.encode("ascii"))
            self.assertEqual(second.read_bytes(), frame.encode("ascii"))
            self.assertNotIn(b"\r", first.read_bytes())

    def test_run_resize_export_and_cleanup_simulation(self):
        # This verifies the production loop/controller, not native console input.
        class FakeTerminal:
            entered = exited = False
            keys = iter(("3", "]", "e", "h", "q"))
            sizes = iter(((100, 40), (20, 5), (80, 30), (1, 1), (1, 1), (100, 40), (100, 40)))
            painted = []

            def __enter__(self):
                self.entered = True
                return self

            def __exit__(self, *_):
                self.exited = True

            def size(self):
                return next(self.sizes, (100, 40))

            def paint(self, lines, width, height):
                self.painted.append((width, height, lines))

            def key(self, timeout):
                return next(self.keys, "q")

        fake = FakeTerminal()
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            result = run(self.state.tree, self.state.camera, Path(directory), terminal_factory=lambda: fake)
            self.assertEqual(result, 0)
            self.assertTrue(fake.entered and fake.exited)
            self.assertGreater(len(fake.painted), 2)
            self.assertEqual(len(list(Path(directory).glob("*.txt"))), 1)

    def test_ctrl_c_cleans_up_simulation(self):
        class InterruptedTerminal:
            exited = False
            def __enter__(self):
                return self
            def __exit__(self, *_):
                self.exited = True
            def size(self):
                raise KeyboardInterrupt
        fake = InterruptedTerminal()
        result = run(self.state.tree, self.state.camera, ROOT / ".tmp", terminal_factory=lambda: fake)
        self.assertEqual(result, 130)
        self.assertTrue(fake.exited)

    def test_ctrl_c_key_cleans_up_simulation(self):
        class KeyTerminal:
            exited = False
            def __enter__(self):
                return self
            def __exit__(self, *_):
                self.exited = True
            def size(self):
                return 10, 4
            def paint(self, *args):
                pass
            def key(self, timeout):
                return "\x03"
        fake = KeyTerminal()
        result = run(self.state.tree, self.state.camera, ROOT / ".tmp", terminal_factory=lambda: fake)
        self.assertEqual(result, 130)
        self.assertTrue(fake.exited)

    def test_atomic_file_replace_and_failure_preserves_old_file(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            target = Path(directory) / "frame.txt"
            target.write_bytes(b"original\n")
            with patch("ascii_tree.export.os.replace", side_effect=OSError("simulated disk error")):
                with self.assertRaises(OSError):
                    write_frame(target, "new frame\n")
            self.assertEqual(target.read_bytes(), b"original\n")
            self.assertEqual(list(Path(directory).iterdir()), [target])
            write_frame(target, "new frame\n")
            self.assertEqual(target.read_bytes(), b"new frame\n")


class CLITests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "ascii_tree", *args], cwd=ROOT,
                              capture_output=True, timeout=15)

    def test_help_startup_and_shutdown(self):
        result = self.cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"render", result.stdout)

    def test_headless_view_exits_once_without_ansi(self):
        result = self.cli("view", "--seed", "42", "--width", "12", "--height", "4")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 4)
        self.assertNotIn(b"\x1b", result.stdout)

    def test_render_file_bytes_reproducible(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            target = Path(directory) / "frame.txt"
            args = ("render", "--seed", "42", "--mode", "4d", "--width", "100",
                    "--height", "40", "--yaw", "37", "--pitch", "11", "--angle4d", "45",
                    "--time", "1.5", "--output", str(target))
            first = self.cli(*args)
            self.assertEqual(first.returncode, 0, first.stderr)
            data = target.read_bytes()
            second = self.cli(*args)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(data, target.read_bytes())
            self.assertEqual(len(data), 4040)
            self.assertTrue(all(32 <= b <= 126 or b == 10 for b in data))
            self.assertNotIn(b"\r", data)
            self.assertNotIn(b"\x1b", data)
            self.assertEqual(first.stdout, b"")

    def test_invalid_cli_fails_cleanly(self):
        for args in (("--yaw", "nan"), ("--pitch", "inf"), ("--zoom", "0"),
                     ("--angle4d", "NaN"), ("--width", "0"), ("--height", "-1"),
                     ("--aspect", "0.0000000001"), ("--mode", "5d"), ("--seed", "abc")):
            result = self.cli("render", *args)
            self.assertEqual(result.returncode, 2, args)
            self.assertNotIn(b"Traceback", result.stderr)
            self.assertEqual(result.stdout, b"")

    def test_missing_output_parent_clean_error(self):
        result = self.cli("render", "--output", str(ROOT / ".tmp" / "missing-parent" / "file.txt"))
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(b"Traceback", result.stderr)

    def test_finite_view_frames_argument(self):
        for count in ("0", "-1", "10001"):
            result = self.cli("view", "--frames", count)
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
