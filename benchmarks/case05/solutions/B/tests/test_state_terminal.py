import io
from pathlib import Path
import unittest
from unittest.mock import patch

from ascii_tree.state import Explorer
from ascii_tree.terminal import (ENTER_SCREEN, LEAVE_SCREEN, KeyDecoder,
                                 NativeTerminal, layout, run_view)
from tests.support import temporary_directory


class FakeClock:
    now = 0.0

    def __call__(self):
        return self.now


class FakeTerminal:
    def __init__(self, keys, sizes=((100, 40),), interrupt=False):
        self.clock = FakeClock()
        self.keys = iter(keys)
        self.sizes = sizes
        self.iteration = 0
        self.draws = []
        self.entered = self.exited = False
        self.interrupt = interrupt

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *_exc):
        self.exited = True

    def size(self):
        return self.sizes[min(max(0, self.iteration - 1), len(self.sizes) - 1)]

    def read_key(self, timeout):
        self.clock.now += 0.1
        self.iteration += 1
        if self.interrupt:
            raise KeyboardInterrupt
        return next(self.keys, "q")

    def draw(self, rows):
        self.draws.append(rows)


class StateTests(unittest.TestCase):
    def test_switch_rotate_zoom_reset_preserves_model(self):
        state = Explorer()
        tree = state.tree
        for key in ("1", "+", "2", "right", "up", "3", "]", "[", "r"):
            state.key(key)
            self.assertIs(state.tree, tree)
            self.assertEqual(state.seed, 42)
        self.assertEqual(state.mode, "4d")
        self.assertEqual((state.yaw, state.pitch, state.angle4d, state.zoom), (25, -8, 0, 1))
        state.key("G")
        self.assertIsNot(state.tree, tree)
        self.assertEqual(state.seed, 43)
        self.assertNotEqual(state.tree.segments, tree.segments)

    def test_animation_play_pause_all_modes(self):
        for mode in ("2d", "3d", "4d"):
            state = Explorer(mode=mode)
            before = state.frame(80, 30)
            state.tick(0.8)
            self.assertEqual(before, state.frame(80, 30))
            state.key(" ")
            state.tick(0.8)
            after = state.frame(80, 30)
            self.assertNotEqual(before, after)
            state.key(" ")
            state.tick(1.0)
            self.assertEqual(after, state.frame(80, 30))

    def test_controls_have_bounds_and_2d_ignores_camera(self):
        state = Explorer(mode="2d")
        before = state.frame(20, 10)
        for key in ("left", "up", "]"):
            state.key(key)
        self.assertEqual(before, state.frame(20, 10))
        for _ in range(150):
            state.key("+")
        self.assertEqual(state.zoom, 5)
        for _ in range(150):
            state.key("-")
        self.assertEqual(state.zoom, 0.15)


class TerminalTests(unittest.TestCase):
    def test_key_decoder_windows_ansi_and_escape(self):
        decoder = KeyDecoder()
        decoder.feed("\xe0M\x00H\x1b[D\x1b[B+G ", 0)
        actual = [decoder.pop(0) for _ in range(7)]
        self.assertEqual(actual, ["right", "up", "left", "down", "+", "G", " "])
        decoder.feed("\x1b", 1)
        self.assertIsNone(decoder.pop(1.02))
        self.assertEqual(decoder.pop(1.05), "escape")

    def test_split_arrow_followed_by_split_arrow_does_not_exit(self):
        decoder = KeyDecoder()
        decoder.feed("\x1b[", 0)
        self.assertIsNone(decoder.pop(0.02))
        decoder.feed("A\x1b[", 0.035)
        self.assertEqual(decoder.pop(0.035), "up")
        self.assertIsNone(decoder.pop(0.045))
        decoder.feed("C", 0.05)
        self.assertEqual(decoder.pop(0.05), "right")

    def test_loop_switch_export_resize_and_shutdown(self):
        state = Explorer()
        tree = state.tree
        sizes = ((100, 40), (80, 30), (12, 5), (1, 1), (100, 40), (100, 40))
        terminal = FakeTerminal(["1", "2", "3", "]", "e", "h", "q"], sizes)
        with temporary_directory() as directory:
            with patch("ascii_tree.terminal.time.monotonic", terminal.clock):
                result = run_view(state, terminal, export_dir=Path(directory))
            self.assertEqual(result, 0)
            self.assertTrue(terminal.entered and terminal.exited)
            self.assertIs(state.tree, tree)
            self.assertEqual(len(terminal.draws), 6)
            for i, rows in enumerate(terminal.draws):
                width, height = sizes[i]
                self.assertEqual(len(rows), height)
                self.assertTrue(all(len(row) == width for row in rows))
            paths = list(Path(directory).glob("*.txt"))
            self.assertEqual(len(paths), 1)
            expected = state.frame(100, 36)
            self.assertEqual(paths[0].read_bytes(), ("\n".join(expected) + "\n").encode("ascii"))
            self.assertEqual(len(paths[0].read_bytes()), 101 * 36)

    def test_keyboard_interrupt_always_exits_context(self):
        terminal = FakeTerminal([], interrupt=True)
        with patch("ascii_tree.terminal.time.monotonic", terminal.clock):
            self.assertEqual(run_view(Explorer(), terminal), 130)
        self.assertTrue(terminal.entered and terminal.exited)

    def test_finite_startup_and_shutdown(self):
        terminal = FakeTerminal([None])
        with patch("ascii_tree.terminal.time.monotonic", terminal.clock):
            self.assertEqual(run_view(Explorer(), terminal, max_frames=1), 0)
        self.assertEqual(len(terminal.draws), 1)
        self.assertTrue(terminal.exited)

    def test_export_error_keeps_viewer_alive(self):
        terminal = FakeTerminal(["e", "q"])
        state = Explorer()
        with temporary_directory() as directory:
            blocked = Path(directory) / "file"
            blocked.write_text("occupied", encoding="ascii")
            with patch("ascii_tree.terminal.time.monotonic", terminal.clock):
                self.assertEqual(run_view(state, terminal, export_dir=blocked), 0)
        self.assertTrue(state.message.startswith("Export failed:"))

    def test_layout_tiny_and_help_are_ascii(self):
        state = Explorer(mode="4d", help_visible=True)
        for width, height in ((1, 1), (2, 2), (10, 3), (20, 8), (100, 40)):
            rows, image = layout(state, width, height)
            self.assertEqual(len(rows), height)
            self.assertTrue(all(len(row) == width for row in rows))
            self.assertTrue(all(32 <= ord(ch) <= 126 for row in rows for ch in row))
            self.assertTrue(image)

    def test_native_draw_uses_cursor_addressing_no_newline_spam(self):
        out = io.StringIO()
        with patch("ascii_tree.terminal.sys.stdout", out):
            NativeTerminal().draw(("abc", "def"))
        data = out.getvalue()
        self.assertIn("\x1b[1;1H", data)
        self.assertIn("\x1b[2;1H", data)
        self.assertNotIn("\n", data)
        self.assertIn("def\x1b[?7h", data)  # last cell is not cleared

    def test_terminal_exit_restores_cursor_and_wrapping(self):
        out = io.StringIO()
        with patch("ascii_tree.terminal.sys.stdout", out):
            NativeTerminal().__exit__(None, None, None)
        self.assertEqual(out.getvalue(), LEAVE_SCREEN)
        self.assertIn("\x1b[?25h", out.getvalue())
        self.assertIn("\x1b[?7h", out.getvalue())
        self.assertIn("\x1b[?1049h", ENTER_SCREEN)


if __name__ == "__main__":
    unittest.main()
