import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ascii_tree.app import canvas_size, compose_screen, export_frame, run_view
from ascii_tree.render import render_tree
from ascii_tree.state import ExplorerState
from ascii_tree.terminal import KeyDecoder, Terminal
from tests.support import FakeClock, FakeTerminal


WORKSPACE = Path(__file__).resolve().parents[1]


class StateTests(unittest.TestCase):
    def test_mode_switch_and_controls_preserve_same_tree_object(self):
        state = ExplorerState()
        original = state.tree
        for key in ("1", "2", "right", "up", "3", "]", "+", "-", "r", "h", "?"):
            state.handle_key(key)
            self.assertIs(state.tree, original)
        state.handle_key("g")
        self.assertEqual(state.seed, 43)
        self.assertIsNot(state.tree, original)

    def test_camera_4d_zoom_animation_and_reset(self):
        state = ExplorerState()
        state.handle_key("1")
        state.handle_key("right")
        self.assertEqual(state.yaw, -25)
        state.handle_key("2")
        state.handle_key("right")
        self.assertEqual(state.yaw, 343)
        state.handle_key("]")
        self.assertEqual(state.angle4, 0)
        state.handle_key("3")
        state.handle_key("]")
        self.assertEqual(state.angle4, 8)
        state.handle_key("+")
        self.assertGreater(state.zoom, 1)
        state.handle_key(" ")
        state.advance(0.5)
        self.assertEqual(state.angle4, 17)
        self.assertEqual(state.time, 0.5)
        state.handle_key("h")
        state.advance(2)
        self.assertEqual(state.time, 0.5)
        state.handle_key("r")
        self.assertEqual((state.yaw, state.pitch, state.angle4, state.zoom, state.time), (-25, 8, 0, 1, 0))
        self.assertFalse(state.animated)

    def test_control_limits_and_quit_variants(self):
        state = ExplorerState()
        for _ in range(100):
            for key in ("+", "up"):
                state.handle_key(key)
        self.assertEqual((state.zoom, state.pitch), (6, 85))
        for _ in range(100):
            for key in ("-", "down"):
                state.handle_key(key)
        self.assertEqual((state.zoom, state.pitch), (0.1, -85))
        for key in ("Q", "escape", "\x03"):
            state.running = True
            state.handle_key(key)
            self.assertFalse(state.running)


class AppTests(unittest.TestCase):
    def test_full_loop_modes_rotation_help_animation_export_and_exit(self):
        state = ExplorerState()
        original = state.tree
        terminal = FakeTerminal(events=(["1"], ["2", "right"], ["3"], ["]"], ["h"], ["h", " "], [], [" ", "e"], ["q"]))
        with tempfile.TemporaryDirectory(dir=WORKSPACE / ".tmp") as temporary:
            result = run_view(state, Path(temporary), terminal, FakeClock())
            files = list(Path(temporary).glob("*.txt"))
            self.assertEqual(len(files), 1)
            exported = files[0].read_bytes()
            self.assertEqual(exported, render_tree(state.tree, state.options(*canvas_size(99, 39))).encode("ascii"))
            self.assertEqual(len(exported), 100 * 34)
        self.assertEqual(result, 0)
        self.assertIs(state.tree, original)
        self.assertTrue(terminal.entered and terminal.closed)
        frames = "".join(terminal.frames)
        self.assertIn(" 2D |", frames)
        self.assertIn(" 3D |", frames)
        self.assertIn("4D -> 3D -> terminal", frames)
        self.assertIn("XW   8.0 deg", frames)
        self.assertIn("HELP", frames)
        self.assertIn("PLAY", frames)
        self.assertIn("Saved", frames)
        for frame, (width, height) in zip(terminal.frames, terminal.frame_sizes):
            self.assertEqual(len(frame.splitlines()), height)
            self.assertTrue(all(len(line) == width for line in frame.splitlines()))

    def test_resize_including_minimum_and_restoration(self):
        state = ExplorerState()
        terminal = FakeTerminal(events=([], [], [], [], ["q"]), sizes=((99, 39), (1, 1), (15, 6), (39, 14), (99, 39)))
        run_view(state, terminal=terminal, clock=FakeClock())
        self.assertEqual(terminal.frame_sizes, [(99, 39), (1, 1), (15, 6), (39, 14), (99, 39)])
        self.assertTrue(terminal.closed)

    def test_small_help_still_names_exit_and_modes(self):
        state = ExplorerState(help_visible=True)
        for width, height in ((40, 12), (20, 8)):
            screen = compose_screen(state, width, height, "\n")
            self.assertIn("exit", screen)
            self.assertIn("1/2/3", screen)
            self.assertEqual(len(screen.splitlines()), height)

    def test_idle_loop_does_not_redraw_or_spam(self):
        terminal = FakeTerminal(events=([], [], [], ["q"]))
        run_view(ExplorerState(), terminal=terminal, clock=FakeClock())
        self.assertEqual(len(terminal.frames), 1)

    def test_keyboard_interrupt_and_output_failure_restore_terminal(self):
        for kwargs, error in (({"interrupt": True}, KeyboardInterrupt), ({"draw_error": True}, OSError)):
            terminal = FakeTerminal(**kwargs)
            with self.assertRaises(error):
                run_view(ExplorerState(), terminal=terminal, clock=FakeClock())
            self.assertTrue(terminal.closed)

    def test_export_failure_is_visible_and_app_can_quit(self):
        state = ExplorerState()
        terminal = FakeTerminal(events=(["e"], ["q"]))
        with patch("ascii_tree.app.export_frame", side_effect=OSError("read only")):
            self.assertEqual(run_view(state, terminal=terminal, clock=FakeClock()), 0)
        self.assertIn("Export failed:", state.message)
        self.assertTrue(terminal.closed)

    def test_exports_use_unique_names_and_exact_lf_bytes(self):
        state = ExplorerState(mode="4d", angle4=35)
        with tempfile.TemporaryDirectory(dir=WORKSPACE / ".tmp") as temporary:
            first = export_frame(Path(temporary), state, 80, 30)
            second = export_frame(Path(temporary), state, 80, 30)
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            data = first.read_bytes()
            self.assertEqual(len(data), 81 * 30)
            self.assertNotIn(b"\r", data)
            self.assertNotIn(b"\x1b", data)


class TerminalTests(unittest.TestCase):
    def test_windows_special_key_prefix_and_escape(self):
        chars = ["\xe0", "H", "\xe0", "M", "3", "]", "\x1b"]
        fake_msvcrt = SimpleNamespace(kbhit=lambda: bool(chars), getwch=lambda: chars.pop(0))
        with patch("ascii_tree.terminal.os", SimpleNamespace(name="nt")), patch.dict("sys.modules", {"msvcrt": fake_msvcrt}):
            self.assertEqual(Terminal().read_keys(0), ["up", "right", "3", "]", "escape"])

    def test_windows_polling_decodes_arrows_and_handles_ctrl_c_directly(self):
        chars = iter(("\xe0", "H", "3", "]", "\x03"))
        pending = [next(chars)]

        def kbhit():
            if pending:
                return True
            try:
                pending.append(next(chars))
                return True
            except StopIteration:
                return False

        fake_msvcrt = SimpleNamespace(kbhit=kbhit, getwch=lambda: pending.pop())
        with patch("ascii_tree.terminal.os", SimpleNamespace(name="nt")), patch.dict("sys.modules", {"msvcrt": fake_msvcrt}):
            with self.assertRaises(KeyboardInterrupt):
                Terminal().read_keys(0)

    def test_incremental_ansi_arrows_and_escape(self):
        decoder = KeyDecoder()
        self.assertEqual(decoder.feed("1\x1b["), ["1"])
        self.assertEqual(decoder.feed("A\x1b[B\x1bOC\x1b[D"), ["up", "down", "right", "left"])
        self.assertEqual(decoder.feed("\x1b"), [])
        self.assertEqual(decoder.feed("", flush_escape=True), ["escape"])
        self.assertEqual(decoder.feed("\x1b[1;5A"), ["up"])
        self.assertEqual(decoder.feed("\x1b[999~q"), ["q"])

    def test_terminal_draw_uses_cursor_addressing(self):
        output = io.StringIO()
        Terminal(stdout=output).draw("abc\nxyz\n")
        self.assertEqual(output.getvalue(), "\x1b[Habc\r\nxyz\x1b[J")

    def test_real_cleanup_sequence_on_exception(self):
        output = io.StringIO()
        terminal = Terminal(stdout=output)
        terminal._entered = True
        terminal.__exit__(KeyboardInterrupt, KeyboardInterrupt(), None)
        self.assertIn("\x1b[?25h", output.getvalue())
        self.assertIn("\x1b[?1049l", output.getvalue())
        self.assertFalse(terminal._entered)

    def test_non_tty_terminal_refuses_startup(self):
        with self.assertRaises(OSError):
            Terminal(io.StringIO(), io.StringIO()).__enter__()
