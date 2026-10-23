import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ascii_tree.app import Explorer
from ascii_tree.terminal import (PosixKeyDecoder, Terminal, TerminalError, WindowsInput,
                                 run_interactive)

ROOT = Path(__file__).resolve().parents[1]


class AppTests(unittest.TestCase):
    def setUp(self):
        self.state = Explorer()

    def test_modes_preserve_object_identity_and_geometry(self):
        tree = self.state.tree
        for key, mode in (("1", "2d"), ("2", "3d"), ("3", "4d"), ("1", "2d")):
            self.state.handle_key(key)
            self.assertEqual(self.state.mode, mode)
            self.assertIs(self.state.tree, tree)

    def test_all_camera_controls_and_reset(self):
        for key in ("right", "up", "+", "3", "]"):
            self.assertTrue(self.state.handle_key(key))
        self.assertEqual(self.state.yaw, 35.5)
        self.assertEqual(self.state.pitch, -3)
        self.assertEqual(self.state.angle4, 7.5)
        self.assertGreater(self.state.zoom, 1)
        self.state.handle_key("r")
        self.assertEqual((self.state.yaw, self.state.pitch, self.state.angle4, self.state.zoom), (28, -8, 0, 1))
        for key in ("left", "down", "-", "["):
            self.state.handle_key(key)
        self.assertEqual((self.state.yaw, self.state.pitch, self.state.angle4), (20.5, -13, 352.5))
        self.assertLess(self.state.zoom, 1)

    def test_new_tree_only_on_g(self):
        original = self.state.tree
        self.state.handle_key("G")
        self.assertEqual(self.state.seed, 43)
        self.assertIsNot(self.state.tree, original)
        self.assertNotEqual(self.state.tree.segments, original.segments)

    def test_play_pause_and_four_dimensional_animation(self):
        self.state.handle_key("3")
        self.state.advance(1)
        self.assertEqual(self.state.elapsed, 0)
        self.state.handle_key(" ")
        self.state.advance(0.5)
        self.assertEqual((self.state.elapsed, self.state.angle4, self.state.yaw), (0.5, 7, 34))
        self.state.handle_key(" ")
        self.state.advance(1)
        self.assertEqual(self.state.elapsed, 0.5)

    def test_ui_resize_and_minimum_terminal(self):
        for columns, rows in ((100, 40), (80, 30), (18, 6), (2, 2), (1, 1), (0, 0)):
            for help_visible in (False, True):
                self.state.help_visible = help_visible
                screen = self.state.screen(columns, rows)
                self.assertLessEqual(len(screen), max(1, rows - 1))
                self.assertEqual({len(line) for line in screen}, {max(1, columns - 1)})
                self.assertTrue(all(32 <= ord(c) <= 126 for line in screen for c in line))

    def test_help_and_4d_explanation_visible(self):
        self.state.handle_key("3")
        self.assertIn("4D data -> XW rotation", "\n".join(self.state.screen(100, 40)))
        self.state.handle_key("?")
        self.assertIn("X' = X*cos(a) - W*sin(a)", "\n".join(self.state.screen(100, 40)))
        self.state.handle_key("h")
        self.assertFalse(self.state.help_visible)

    def test_export_exact_current_raster_without_ui_and_no_overwrite(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            self.state.export_dir = Path(directory)
            self.state.screen(100, 40)
            expected = ("\n".join(self.state.last_frame) + "\n").encode("ascii")
            first, second = self.state.export_frame(), self.state.export_frame()
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), expected)
            self.assertEqual(second.read_bytes(), expected)
            self.assertNotIn(b"\x1b", expected)
            self.assertNotIn(b"ASCII TREE", expected)

    def test_export_errors_are_reported_in_ui(self):
        with patch.object(Explorer, "export_frame", side_effect=PermissionError("read only")):
            self.state.handle_key("e")
        self.assertIn("Export failed", self.state.message)

    def test_2d_camera_keys_do_not_move_front_elevation(self):
        self.state.handle_key("1")
        self.state.handle_key("right")
        self.assertEqual(self.state.yaw, 28)
        self.assertIn("2D is a fixed", self.state.message)

    def test_quit_variants(self):
        for key in ("Q", "esc", "ctrl+c"):
            state = Explorer()
            state.handle_key(key)
            self.assertFalse(state.running)


class DecoderTests(unittest.TestCase):
    def test_windows_native_arrows_ctrl_c_and_keyup(self):
        for code, expected in ((0x25, "left"), (0x26, "up"), (0x27, "right"), (0x28, "down")):
            self.assertEqual(WindowsInput.decode("\x00", code), expected)
        self.assertEqual(WindowsInput.decode("\x1b", 0x1B), "esc")
        self.assertEqual(WindowsInput.decode("\x03", 0x43), "ctrl+c")
        self.assertEqual(WindowsInput.decode("c", 0x43, 0x8), "ctrl+c")
        self.assertEqual(WindowsInput.decode("G", 0x47), "G")
        self.assertIsNone(WindowsInput.decode("G", 0x47, down=False))

    def test_posix_fragmented_arrow_and_escape(self):
        decoder = PosixKeyDecoder()
        self.assertEqual(decoder.feed("\x1b", 1), [])
        self.assertEqual(decoder.feed("[", 1.01), [])
        self.assertEqual(decoder.feed("A", 1.02), ["up"])
        self.assertEqual(decoder.feed("\x1b[B\x1bOC\x1b[Dg", 2), ["down", "right", "left", "g"])
        self.assertEqual(decoder.feed("\x1b", 3), [])
        self.assertEqual(decoder.feed("", 3.1), ["esc"])

    def test_unknown_csi_does_not_trigger_number_keys(self):
        self.assertEqual(PosixKeyDecoder().feed("\x1b[3~", 1), [])


class FakeTerminal:
    def __init__(self, events, sizes=None):
        self.events = iter(events)
        self.sizes = iter(sizes or [])
        self.current_size = (100, 40)
        self.frames = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def poll_keys(self):
        event = next(self.events, ["q"])
        if isinstance(event, BaseException):
            raise event
        return event

    def size(self):
        self.current_size = next(self.sizes, self.current_size)
        return self.current_size

    def draw(self, lines):
        self.frames.append(lines)


class LoopTests(unittest.TestCase):
    def test_scripted_start_modes_resize_animation_export_shutdown(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            state = Explorer(export_dir=Path(directory))
            terminal = FakeTerminal([[], ["1"], ["2"], ["3", "]"], [" "], [], ["g"],
                                     ["r"], ["h"], ["?"], ["e"], ["q"]],
                                    [(100, 40), (100, 40), (18, 6), (1, 1), (100, 40)])
            ticks = iter(i * 0.1 for i in range(100))
            code = run_interactive(state, terminal, clock=lambda: next(ticks), sleep=lambda _: None)
            self.assertEqual(code, 0)
            self.assertTrue(terminal.closed)
            self.assertGreater(len(terminal.frames), 7)
            self.assertTrue(any("2D" in "".join(frame) for frame in terminal.frames))
            self.assertTrue(any("4D" in "".join(frame) for frame in terminal.frames))
            self.assertEqual(len(list(Path(directory).glob("*.txt"))), 1)

    def test_ctrl_c_restores_terminal_and_returns_130(self):
        terminal = FakeTerminal([[], KeyboardInterrupt()])
        self.assertEqual(run_interactive(Explorer(), terminal, sleep=lambda _: None), 130)
        self.assertTrue(terminal.closed)

    def test_ctrl_c_key_event_restores_terminal_and_returns_130(self):
        terminal = FakeTerminal([[], ["ctrl+c"]])
        self.assertEqual(run_interactive(Explorer(), terminal, sleep=lambda _: None), 130)
        self.assertTrue(terminal.closed)

    def test_failure_still_restores_terminal(self):
        terminal = FakeTerminal([[]])
        terminal.draw = Mock(side_effect=RuntimeError("draw failed"))
        with self.assertRaisesRegex(RuntimeError, "draw failed"):
            run_interactive(Explorer(), terminal)
        self.assertTrue(terminal.closed)

    def test_terminal_draw_updates_in_place_without_newline_spam(self):
        stream = io.StringIO()
        with patch("sys.stdout", stream):
            Terminal().draw(("abc", "def"))
        self.assertNotIn("\n", stream.getvalue())
        self.assertIn("\x1b[1;1Habc", stream.getvalue())
        self.assertIn("\x1b[2;1Hdef", stream.getvalue())

    def test_non_tty_cannot_enter_terminal(self):
        with patch("sys.stdin.isatty", return_value=False), self.assertRaises(TerminalError):
            with Terminal():
                pass
