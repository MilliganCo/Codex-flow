from dataclasses import replace
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ascii_tree.model import generate_tree
from ascii_tree.render import RenderOptions, render_tree
from ascii_tree.state import Explorer, compose_screen
from ascii_tree.terminal import LEAVE_SCREEN, Terminal, run

ROOT = Path(__file__).resolve().parents[1]


class StateTests(unittest.TestCase):
    def setUp(self):
        self.explorer = Explorer(generate_tree(42), RenderOptions())

    def test_modes_keep_same_object_and_only_g_replaces_tree(self):
        original = self.explorer.tree
        for key, mode in (("1", "2d"), ("2", "3d"), ("3", "4d")):
            self.explorer.key(key)
            self.assertEqual(self.explorer.options.mode, mode)
            self.assertIs(self.explorer.tree, original)
        self.explorer.key("G")
        self.assertEqual(self.explorer.tree.seed, 43)
        self.assertNotEqual(self.explorer.tree, original)

    def test_controls_camera_xw_zoom_reset_and_quit(self):
        original = self.explorer.options
        for key in ("right", "up", "+", "3", "]"):
            self.explorer.key(key)
        self.assertGreater(self.explorer.options.yaw, original.yaw)
        self.assertGreater(self.explorer.options.pitch, original.pitch)
        self.assertGreater(self.explorer.options.zoom, original.zoom)
        self.assertEqual(self.explorer.options.angle4d, 8)
        self.explorer.key("r")
        self.assertEqual(self.explorer.options, replace(original, mode="4d"))
        self.explorer.key("escape")
        self.assertTrue(self.explorer.quit)

    def test_animation_pauses_and_help_freezes_it(self):
        self.explorer.key(" ")
        self.assertTrue(self.explorer.advance(0.1))
        self.assertAlmostEqual(self.explorer.options.time, 0.1)
        self.explorer.key("h")
        self.assertFalse(self.explorer.advance(0.1))
        self.assertAlmostEqual(self.explorer.options.time, 0.1)
        self.explorer.key("?")
        self.explorer.key(" ")
        self.assertFalse(self.explorer.advance(0.1))

    def test_2d_ignores_camera_keys_and_3d_ignores_xw(self):
        self.explorer.key("]")
        self.assertEqual(self.explorer.options.angle4d, 0)
        self.explorer.key("1")
        self.explorer.key("left")
        self.assertEqual(self.explorer.options.yaw, 25)

    def test_resize_and_minimal_screen_never_overflow(self):
        for width, height in ((100, 40), (80, 30), (24, 7), (12, 4), (1, 1), (0, 0)):
            rows, frame = compose_screen(self.explorer, width, height)
            self.assertEqual(len(rows), max(1, height))
            self.assertTrue(all(len(row) == max(1, width) for row in rows))
            self.assertNotIn("\x1b", frame)
        self.explorer.key("h")
        rows, _ = compose_screen(self.explorer, 80, 30)
        self.assertIn("FIELD GUIDE", "".join(rows))

    def test_export_matches_current_raster_and_never_overwrites(self):
        temp_root = ROOT / ".tmp"
        temp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as temp:
            _, frame = compose_screen(self.explorer, 100, 40)
            first = self.explorer.export(Path(temp), frame)
            second = self.explorer.export(Path(temp), frame)
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), frame.encode("ascii"))
            self.assertEqual(second.read_bytes(), first.read_bytes())


class LifecycleTests(unittest.TestCase):
    def test_terminal_exit_always_restores_modes_after_draw_failure(self):
        terminal = Terminal()
        calls = []
        terminal._restore = [lambda: calls.append("input"), lambda: calls.append("output")]
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            terminal.__exit__(RuntimeError, RuntimeError("simulated"), None)
            self.assertIn(LEAVE_SCREEN, output.getvalue())
        self.assertEqual(calls, ["output", "input"])
        self.assertEqual(terminal._restore, [])

    def test_run_startup_resize_controls_and_shutdown_simulation(self):
        events = iter([None, "3", "]", " ", " ", "q"])
        sizes = iter([os.terminal_size((100, 40)), os.terminal_size((80, 30)),
                      os.terminal_size((1, 1)), os.terminal_size((80, 30)), os.terminal_size((80, 30))])
        rows_drawn = []
        lifecycle = []

        class FakeTerminal:
            def __enter__(self):
                lifecycle.append("enter")
                return self
            def __exit__(self, *_):
                lifecycle.append("exit")
            def read_key(self, timeout):
                return next(events)
            def draw(self, rows):
                rows_drawn.append(rows)

        ticks = iter([0, 0.1, 0.2, 0.3, 0.4, 0.5])
        result = run(generate_tree(42), RenderOptions(), ROOT / ".tmp", terminal_factory=FakeTerminal,
                     size_provider=lambda: next(sizes), clock=lambda: next(ticks))
        self.assertEqual(result, 0)
        self.assertEqual(lifecycle, ["enter", "exit"])
        self.assertEqual([len(rows) for rows in rows_drawn], [40, 30, 1, 30, 30])
        self.assertIn("4D", rows_drawn[1][0])

    def test_keyboard_interrupt_restores_terminal_and_returns_130_simulation(self):
        lifecycle = []

        class Interrupted:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                lifecycle.append("restored")
            def read_key(self, timeout):
                raise KeyboardInterrupt

        self.assertEqual(run(generate_tree(42), RenderOptions(), ROOT / ".tmp", terminal_factory=Interrupted), 130)
        self.assertEqual(lifecycle, ["restored"])


if __name__ == "__main__":
    unittest.main()
