from dataclasses import replace
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ascii_tree.projection import View
from ascii_tree.state import Explorer
from ascii_tree.terminal import (
    LEAVE_SCREEN, Terminal, compose_screen, console_mode, run_interactive, windows_key,
)


class StateTests(unittest.TestCase):
    def test_switches_preserve_same_tree_until_g(self):
        state = Explorer()
        original = state.tree
        for key in ("1", "+", "-", "2", "left", "up", "3", "]", "[", " ", "h", "?", "r"):
            state.key(key)
            self.assertIs(state.tree, original)
            self.assertEqual(state.seed, 42)
        state.key("g")
        self.assertIsNot(state.tree, original)
        self.assertEqual(state.seed, 43)
        self.assertNotEqual(original.segments, state.tree.segments)

    def test_keys_and_reset(self):
        state = Explorer()
        state.key("1")
        self.assertEqual(state.view.mode, "2d")
        before = state.view
        state.key("right")
        state.key("]")
        self.assertEqual(before, state.view)
        state.key("2")
        state.key("right")
        state.key("up")
        state.key("+")
        self.assertGreater(state.view.yaw, before.yaw)
        self.assertGreater(state.view.pitch, before.pitch)
        self.assertGreater(state.view.zoom, before.zoom)
        state.key("3")
        state.key("]")
        self.assertEqual(state.view.angle4d, 8)
        state.key("r")
        self.assertEqual(state.view, View(mode="4d"))
        state.key("H")
        self.assertTrue(state.help_open)
        state.key("?")
        self.assertFalse(state.help_open)
        for key in ("q", "escape", "ctrl+c"):
            state.running = True
            state.key(key)
            self.assertFalse(state.running)

    def test_animation_deterministic_and_paused(self):
        a, b = Explorer(view=View(mode="4d")), Explorer(view=View(mode="4d"))
        a.key(" ")
        b.key(" ")
        a.advance(2)
        for _ in range(4):
            b.advance(0.5)
        self.assertEqual(a.view, b.view)
        self.assertEqual(a.view.angle4d, 48)
        a.key(" ")
        before = a.view
        a.advance(100)
        self.assertEqual(a.view, before)

    def test_export_saves_displayed_frame_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory(dir=".tmp") as directory:
            state = Explorer(export_dir=Path(directory))
            frame = state.draw(80, 30)
            state.key("e")
            first = next(Path(directory).glob("*.txt"))
            self.assertEqual(first.read_bytes(), frame.to_bytes())
            state.export_number = 0
            state.key("e")
            self.assertEqual(len(list(Path(directory).glob("*.txt"))), 2)
            self.assertEqual(first.read_bytes(), frame.to_bytes())

    def test_export_error_visible_without_crash(self):
        state = Explorer()
        state.draw(12, 5)
        with patch.object(Path, "mkdir", side_effect=PermissionError("read only")):
            state.key("e")
        self.assertIn("Export failed", state.message)

    def test_ui_small_sizes_help_and_resize(self):
        state = Explorer(view=View(mode="4d"))
        for help_open in (False, True):
            state.help_open = help_open
            for width, height in ((100, 40), (80, 30), (25, 8), (1, 1), (2, 2), (12, 5)):
                rows = compose_screen(state, width, height)
                self.assertEqual(len(rows), height)
                self.assertTrue(all(len(row) == width and row.isascii() for row in rows))
        state.help_open = False
        screen = "\n".join(compose_screen(state, 100, 40))
        self.assertIn("[4D]", screen)
        self.assertIn("4D DATA -> XW -> 3D -> 2D", screen)


class FakeTerminal:
    def __init__(self, keys=("q",), sizes=((100, 40),)):
        self.keys = iter(keys)
        self.sizes = list(sizes)
        self.index = 0
        self.frames = []
        self.entered = False
        self.closed = False
        self.exception = None

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True
        self.exception = exc_type

    def size(self):
        return self.sizes[min(self.index, len(self.sizes) - 1)]

    def present(self, rows):
        self.frames.append(rows)

    def read_key(self, timeout):
        self.index += 1
        key = next(self.keys)
        if isinstance(key, BaseException):
            raise key
        return key


class TerminalTests(unittest.TestCase):
    def test_windows_modes_read_ctrl_c_and_native_keys(self):
        mode = console_mode(0x3FF, False)
        self.assertEqual(mode & 0x247, 0)
        self.assertEqual(mode & 0x80, 0x80)
        self.assertEqual(console_mode(0, True), 5)

    def test_windows_extended_keys(self):
        for prefix in ("\x00", "\xe0"):
            for code, expected in (("K", "left"), ("M", "right"), ("H", "up"), ("P", "down")):
                self.assertEqual(windows_key(prefix, code), expected)
        self.assertEqual(windows_key("\x1b"), "escape")
        self.assertEqual(windows_key("\x03"), "ctrl+c")

    def test_startup_switch_resize_and_shutdown(self):
        terminal = FakeTerminal(("1", "2", "3", "]", "h", "h", "q"),
                                ((100, 40), (80, 30), (12, 5), (2, 2), (100, 40)))
        state = Explorer()
        original = state.tree
        self.assertEqual(run_interactive(state, lambda: terminal), 0)
        self.assertTrue(terminal.entered and terminal.closed)
        self.assertIs(original, state.tree)
        self.assertEqual(len(terminal.frames), 7)
        self.assertEqual(len(terminal.frames[2]), 5)
        self.assertEqual(len(terminal.frames[3]), 2)
        self.assertEqual(state.view.mode, "4d")
        self.assertEqual(state.view.angle4d, 8)

    def test_keyboard_interrupt_restores_context(self):
        terminal = FakeTerminal((KeyboardInterrupt(),))
        self.assertEqual(run_interactive(Explorer(), lambda: terminal), 130)
        self.assertTrue(terminal.closed)
        self.assertIs(terminal.exception, KeyboardInterrupt)

    def test_ctrl_c_key_exits_130_and_restores_context(self):
        terminal = FakeTerminal(("ctrl+c",))
        self.assertEqual(run_interactive(Explorer(), lambda: terminal), 130)
        self.assertTrue(terminal.closed)
        self.assertIs(terminal.exception, KeyboardInterrupt)

    def test_render_failure_restores_context(self):
        terminal = FakeTerminal()
        with patch("ascii_tree.terminal.compose_screen", side_effect=RuntimeError("render failed")):
            with self.assertRaisesRegex(RuntimeError, "render failed"):
                run_interactive(Explorer(), lambda: terminal)
        self.assertTrue(terminal.closed)

    def test_actual_adapter_restores_output_and_console_modes(self):
        terminal = Terminal()
        terminal.output = io.StringIO()
        terminal.entered = True
        calls = []

        class Kernel:
            def SetConsoleMode(self, handle, mode):
                calls.append((handle, mode))

        terminal.kernel = Kernel()
        terminal.saved_modes = [(11, 7), (10, 503)]
        terminal.__exit__(KeyboardInterrupt, KeyboardInterrupt(), None)
        self.assertEqual(terminal.output.getvalue(), LEAVE_SCREEN)
        self.assertEqual(calls, [(10, 503), (11, 7)])
        self.assertFalse(terminal.entered)

    def test_mode_restore_even_if_terminal_output_fails(self):
        terminal = Terminal()
        terminal.entered = True
        calls = []

        class BrokenOutput:
            def write(self, data):
                raise OSError("disconnected")

        class Kernel:
            def SetConsoleMode(self, handle, mode):
                calls.append((handle, mode))

        terminal.output = BrokenOutput()
        terminal.kernel = Kernel()
        terminal.saved_modes = [(11, 7)]
        with self.assertRaises(OSError):
            terminal.__exit__(None, None, None)
        self.assertEqual(calls, [(11, 7)])


if __name__ == "__main__":
    unittest.main()
