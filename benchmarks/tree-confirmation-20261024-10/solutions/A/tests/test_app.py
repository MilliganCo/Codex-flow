import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from ascii_tree.app import Explorer, compose, run_loop, viewport_size
from ascii_tree.cli import main
from ascii_tree.terminal import KeyDecoder, Terminal
from tests.support import FakeTerminal, temporary_directory


class StateTests(unittest.TestCase):
    def test_mode_camera_help_export_and_reset_preserve_object(self):
        state = Explorer()
        tree = state.tree
        for key in ("1", "2", "3", "]", "[", "left", "right", "up", "down", "+", "-", "h", "h", "r"):
            state.key(key)
            self.assertIs(tree, state.tree)
        self.assertEqual("4d", state.mode)
        self.assertEqual(42, state.seed)

    def test_only_g_replaces_tree(self):
        state = Explorer()
        original = state.tree
        state.key("G")
        self.assertIsNot(original, state.tree)
        self.assertNotEqual(original.vertices, state.tree.vertices)
        self.assertEqual(43, state.seed)

    def test_animation_pause_help_and_reset(self):
        state = Explorer(mode="4d")
        initial = (state.yaw, state.angle4, state.time)
        state.advance(1)
        self.assertEqual(initial, (state.yaw, state.angle4, state.time))
        state.key(" ")
        state.advance(1)
        self.assertEqual((37, 16, 1), (state.yaw, state.angle4, state.time))
        state.key("h")
        state.advance(1)
        self.assertEqual(1, state.time)
        state.key("h")
        state.key(" ")
        state.advance(1)
        self.assertEqual(1, state.time)
        state.key("r")
        self.assertEqual(initial, (state.yaw, state.angle4, state.time))

    def test_animation_elapsed_time_not_polling_interval(self):
        state = Explorer(mode="4d", playing=True)
        terminal = FakeTerminal((None,) * 8 + ("q",))
        clock = iter(i * 0.025 for i in range(20))
        with patch("ascii_tree.app.time.monotonic", side_effect=lambda: next(clock)):
            run_loop(state, terminal, fps=10)
        self.assertAlmostEqual(0.225, state.time)

    def test_key_bounds_and_2d_no_camera_rotation(self):
        state = Explorer(mode="2d")
        for key in ("up", "right", "]"):
            state.key(key)
        self.assertEqual((25, 8, 0), (state.yaw, state.pitch, state.angle4))
        for _ in range(100):
            state.key("+")
        self.assertEqual(5, state.zoom)
        for _ in range(100):
            state.key("-")
        self.assertEqual(0.15, state.zoom)

    def test_minimum_narrow_and_help_sizes(self):
        state = Explorer()
        for help_open in (False, True):
            state.help_open = help_open
            for width, height in ((1, 1), (2, 2), (12, 5), (30, 10), (100, 40)):
                rows = compose(state, width, height)
                self.assertEqual(height, len(rows))
                self.assertTrue(all(len(row) == width for row in rows))
                self.assertTrue(all(32 <= ord(c) <= 126 for row in rows for c in row))

    def test_ui_explicitly_explains_4d_projection(self):
        state = Explorer(mode="4d")
        rows = compose(state, 100, 40)
        self.assertIn("4D DATA -> 3D -> SCREEN", "\n".join(rows))
        state.key("h")
        self.assertIn("XW rotation mixes", "\n".join(compose(state, 100, 40)))

    def test_export_matches_current_frame_and_does_not_overwrite(self):
        state = Explorer(mode="4d", angle4=45)
        tree = state.tree
        with temporary_directory() as directory:
            first = state.export(80, 30, Path(directory))
            data = first.read_bytes()
            self.assertEqual(state.frame(80, 30).bytes(), data)
            other_session = Explorer(mode="4d", angle4=45)
            second = other_session.export(80, 30, Path(directory))
            self.assertNotEqual(first, second)
            self.assertEqual(data, first.read_bytes())
        self.assertIs(tree, state.tree)


class LoopTests(unittest.TestCase):
    def test_startup_all_modes_resize_export_and_shutdown(self):
        state = Explorer()
        original = state.tree
        terminal = FakeTerminal(("1", "2", "3", "]", "h", "h", "e", "q"),
                                ((100, 40), (80, 30), (12, 5), (1, 1), (100, 40)))
        with temporary_directory() as directory:
            self.assertEqual(0, run_loop(state, terminal, Path(directory)))
            exports = list(Path(directory).glob("*.txt"))
            self.assertEqual(1, len(exports))
            self.assertEqual(100, len(exports[0].read_text().splitlines()[0]))
        self.assertTrue(terminal.entered and terminal.closed)
        self.assertIs(original, state.tree)
        self.assertTrue(any("2D" in rows[0] for rows in terminal.draws))
        self.assertTrue(any("4D" in rows[0] for rows in terminal.draws))

    def test_keyboardinterrupt_restores_context(self):
        terminal = FakeTerminal((KeyboardInterrupt(),))
        with self.assertRaises(KeyboardInterrupt):
            run_loop(Explorer(), terminal)
        self.assertTrue(terminal.closed)

    def test_export_failure_is_visible_and_loop_survives(self):
        state = Explorer()
        terminal = FakeTerminal(("e", "q"))
        with patch.object(state, "export", side_effect=OSError("read-only location")):
            self.assertEqual(0, run_loop(state, terminal))
        self.assertIn("Export failed", state.message)

    def test_finite_duration_shutdown(self):
        terminal = FakeTerminal((None,) * 10)
        with patch("ascii_tree.app.time.monotonic", side_effect=(0, 0, 1)):
            self.assertEqual(0, run_loop(Explorer(), terminal, duration=0.1))
        self.assertTrue(terminal.closed)

    def test_cli_interactive_branch_and_ctrl_c_exit_code(self):
        terminal = FakeTerminal(("3", "]", "q"))
        with patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True), \
                patch("ascii_tree.cli.Terminal", return_value=terminal):
            self.assertEqual(0, main(["view", "--seed", "42"]))
        with patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True), \
                patch("ascii_tree.cli.run_loop", side_effect=KeyboardInterrupt):
            self.assertEqual(130, main(["view"]))


class TerminalTests(unittest.TestCase):
    def test_resize_queries_the_active_output_buffer(self):
        terminal = Terminal(stdout=io.StringIO())
        with patch("os.get_terminal_size", return_value=os.terminal_size((40, 12))) as size:
            terminal.active_output = unittest.mock.Mock()
            terminal.active_output.fileno.return_value = 7
            self.assertEqual((40, 12), terminal.size())
            size.assert_called_once_with(7)

    def test_split_arrow_sequences_and_escape(self):
        decoder = KeyDecoder()
        decoder.feed("\x1b", 0)
        self.assertIsNone(decoder.pop(0.01))
        decoder.feed("[A", 0.02)
        self.assertEqual("up", decoder.pop(0.02))
        decoder.feed("\x1b[D3]", 1)
        self.assertEqual(["left", "3", "]"], [decoder.pop(1) for _ in range(3)])
        decoder.feed("\x1b", 2)
        self.assertEqual("escape", decoder.pop(2.05))

    def test_terminal_restored_after_exception(self):
        stream = io.StringIO()
        terminal = Terminal(stdout=stream)
        with patch.object(terminal, "_enable"), patch.object(terminal, "_restore") as restore:
            with self.assertRaises(RuntimeError):
                with terminal:
                    raise RuntimeError("test interruption")
            restore.assert_called_once()
        self.assertIn(Terminal.ENTER, stream.getvalue())
        self.assertTrue(stream.getvalue().endswith(Terminal.LEAVE))

    def test_failed_startup_still_restores_terminal(self):
        terminal = Terminal(stdout=io.StringIO())
        with patch.object(terminal, "_enable", side_effect=OSError("failed")), \
                patch.object(terminal, "_restore") as restore:
            with self.assertRaises(OSError):
                terminal.__enter__()
            restore.assert_called_once()

    def test_redraw_uses_cursor_addresses_and_skips_identical_rows(self):
        stream = io.StringIO()
        terminal = Terminal(stdout=stream)
        terminal.draw(("tree", "root"))
        size = len(stream.getvalue())
        terminal.draw(("tree", "root"))
        self.assertEqual(size, len(stream.getvalue()))
        terminal.draw(("TREE", "root"))
        self.assertEqual("\x1b[1;1HTREE", stream.getvalue()[size:])
        self.assertNotIn("\n", stream.getvalue())
