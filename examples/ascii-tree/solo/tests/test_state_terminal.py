from collections import deque
from dataclasses import replace
import io
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import Mock, patch

from ascii_tree.model import generate_tree
from ascii_tree.renderer import RenderOptions, render_tree
from ascii_tree.state import ExplorerState
from ascii_tree.terminal import (ENTER_SCREEN, LEAVE_SCREEN, KeyDecoder, TerminalError,
                                 TerminalSession, compose_screen, export_frame, run_interactive)
from tests.support import TEMP_ROOT


class StateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_mode_camera_and_animation_do_not_regenerate_tree(self):
        state = ExplorerState(self.tree)
        fingerprint = state.tree.fingerprint
        for key in ("1", "+", "2", "right", "up", "3", "]", ".", "[", ",", " ", "r", "h", "?"):
            state.handle_key(key)
            state.tick(.125)
            self.assertIs(state.tree, self.tree)
            self.assertEqual(state.tree.fingerprint, fingerprint)
        state.handle_key("G")
        self.assertIsNot(state.tree, self.tree)
        self.assertEqual(state.tree.seed, 43)
        self.assertNotEqual(state.tree.fingerprint, fingerprint)

    def test_angles_zoom_reset_export_and_quit(self):
        state = ExplorerState(self.tree, RenderOptions(mode="4d"))
        state.handle_key("]")
        self.assertEqual(state.options.angle4, 7)
        state.handle_key(".")
        self.assertEqual(state.options.angle4, 14)
        state.handle_key("[")
        state.handle_key(",")
        self.assertEqual(state.options.angle4, 0)
        state.handle_key("right")
        self.assertNotEqual(state.options.yaw, -20)
        for _ in range(100):
            state.handle_key("up")
            state.handle_key("+")
        self.assertEqual(state.options.pitch, 80)
        self.assertEqual(state.options.zoom, 5)
        for _ in range(100):
            state.handle_key("down")
            state.handle_key("-")
        self.assertEqual(state.options.pitch, -80)
        self.assertEqual(state.options.zoom, .15)
        state.handle_key("r")
        self.assertEqual((state.options.yaw, state.options.pitch, state.options.zoom, state.options.angle4), (-20, 8, 1, 0))
        self.assertEqual(state.handle_key("E"), "export")
        for key in ("Q", "escape"):
            state.running = True
            state.handle_key(key)
            self.assertFalse(state.running)

    def test_pause_and_2d_controls(self):
        state = ExplorerState(self.tree, RenderOptions(mode="2d"))
        original = state.options
        for key in ("left", "up", "]"):
            state.handle_key(key)
            self.assertEqual(state.options, original)
        state.tick(2)
        self.assertEqual(state.options.time, 0)
        state.handle_key(" ")
        state.tick(1)
        animated = state.options
        self.assertNotEqual(render_tree(self.tree, original), render_tree(self.tree, animated))
        state.handle_key(" ")
        state.tick(2)
        self.assertEqual(state.options, animated)


class DecoderTests(unittest.TestCase):
    def test_fragmented_arrows_and_ordinary_keys(self):
        decoder = KeyDecoder()
        self.assertEqual(decoder.feed("1\x1b["), ["1"])
        self.assertEqual(decoder.feed("A\x1b[D+[]"), ["up", "left", "+", "[", "]"])
        self.assertEqual(decoder.feed("\x1bOB\x1bOC"), ["down", "right"])

    def test_standalone_escape_unsupported_csi_and_ctrl_c(self):
        decoder = KeyDecoder()
        self.assertEqual(decoder.feed("\x1b"), [])
        self.assertEqual(decoder.feed("", flush_escape=True), ["escape"])
        self.assertEqual(decoder.feed("\x1b[15~g"), ["g"])
        with self.assertRaises(KeyboardInterrupt):
            decoder.feed("\x03")


class FakeSession:
    def __init__(self, events, size=(100, 40)):
        self.events = deque(events)
        self.current_size = size
        self.draws = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def size(self):
        return self.current_size

    def draw(self, rows, resized=False):
        self.draws.append((rows, resized))

    def read_key(self, timeout):
        event = self.events.popleft() if self.events else "q"
        if isinstance(event, BaseException):
            raise event
        if isinstance(event, tuple):
            self.current_size = event
            return None
        return event


class TTYString(io.StringIO):
    def isatty(self):
        return True


class TerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_screen_resize_help_and_minimum_dimensions(self):
        state = ExplorerState(self.tree, RenderOptions(mode="4d"))
        for size in ((100, 40), (80, 30), (22, 9), (8, 4), (1, 1)):
            for help_visible in (False, True):
                state.help_visible = help_visible
                screen = compose_screen(state, *size)
                self.assertEqual(len(screen.rows), size[1])
                self.assertTrue(all(len(row) == size[0] for row in screen.rows))
                self.assertTrue(all(row.isascii() for row in screen.rows))
        state.help_visible = False
        self.assertIn("4D DATA -> 3D -> 2D", "\n".join(compose_screen(state, 100, 40).rows))

    def test_application_event_loop_resize_export_and_shutdown(self):
        state = ExplorerState(self.tree)
        session = FakeSession(["1", "2", "3", ".", "right", (18, 6), "h", "h", (100, 40), "e", "q"])
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            self.assertEqual(run_interactive(state, export_dir=Path(directory), session=session), 0)
            files = list(Path(directory).glob("*.txt"))
            self.assertEqual(len(files), 1)
            exported = files[0].read_bytes()
            self.assertEqual(len(exported.splitlines()), 34)
            self.assertTrue(all(len(line) == 100 for line in exported.splitlines()))
            self.assertNotIn(b"\x1b", exported)
        self.assertTrue(session.closed)
        self.assertIs(state.tree, self.tree)
        self.assertTrue(any(len(rows) == 6 and len(rows[0]) == 18 and resized for rows, resized in session.draws))
        self.assertIn("4D", session.draws[-1][0][0])

    def test_ctrl_c_and_render_failure_close_session(self):
        session = FakeSession([KeyboardInterrupt()])
        with self.assertRaises(KeyboardInterrupt):
            run_interactive(ExplorerState(self.tree), session=session)
        self.assertTrue(session.closed)
        session = FakeSession([])
        with patch("ascii_tree.terminal.compose_screen", side_effect=RuntimeError("draw failed")):
            with self.assertRaises(RuntimeError):
                run_interactive(ExplorerState(self.tree), session=session)
        self.assertTrue(session.closed)

    def test_export_does_not_overwrite_and_error_is_visible(self):
        frame = render_tree(self.tree, RenderOptions(20, 8))
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory)
            first = export_frame(frame, path, 42, "3d")
            second = export_frame(frame, path, 42, "3d")
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            blocked = path / "file"
            blocked.write_text("not a directory", encoding="ascii")
            state = ExplorerState(self.tree)
            run_interactive(state, export_dir=blocked, session=FakeSession(["e", "q"]))
            self.assertIn("Export failed:", state.status)

    def test_real_terminal_context_restores_cursor_and_mode_on_interrupt(self):
        for error in (None, KeyboardInterrupt(), RuntimeError("paint failed")):
            output, restore = TTYString(), Mock()
            with patch("ascii_tree.terminal._enable_windows_console", return_value=restore), \
                 patch("ascii_tree.terminal._enable_posix_cbreak", return_value=restore):
                try:
                    with TerminalSession(TTYString(), output):
                        if error:
                            raise error
                except (KeyboardInterrupt, RuntimeError):
                    pass
            self.assertTrue(output.getvalue().startswith(ENTER_SCREEN))
            self.assertTrue(output.getvalue().endswith(LEAVE_SCREEN))
            restore.assert_called_once()

    def test_non_tty_context_rejected_before_escapes(self):
        output = io.StringIO()
        with self.assertRaises(TerminalError):
            with TerminalSession(io.StringIO(), output):
                pass
        self.assertEqual(output.getvalue(), "")

    def test_windows_key_adapter_arrows_ctrl_c_and_brackets(self):
        fake = Mock()
        terminal = TerminalSession()
        with patch("ascii_tree.terminal.os.name", "nt"), patch.dict(sys.modules, {"msvcrt": fake}):
            for code, expected in (("H", "up"), ("P", "down"), ("K", "left"), ("M", "right")):
                fake.kbhit.return_value = True
                fake.getwch.side_effect = ["\xe0", code]
                self.assertEqual(terminal.read_key(.01), expected)
            for char in ("[", "]", ",", "."):
                fake.getwch.side_effect = [char]
                self.assertEqual(terminal.read_key(.01), char)
            fake.getwch.side_effect = ["\x03"]
            with self.assertRaises(KeyboardInterrupt):
                terminal.read_key(.01)

    @unittest.skipUnless(sys.platform == "win32", "Windows native console flags")
    def test_windows_console_modes_restored_and_startup_failure_rolls_back(self):
        import ctypes
        from ascii_tree.terminal import _enable_windows_console
        input_stream, output = Mock(), Mock()
        input_stream.fileno.return_value = 0
        output.fileno.return_value = 1

        def read_mode(handle, pointer):
            pointer._obj.value = 7 if handle.value == 100 else 3
            return 1

        kernel = Mock()
        kernel.GetConsoleMode.side_effect = read_mode
        kernel.SetConsoleMode.return_value = 1
        with patch.object(ctypes, "WinDLL", return_value=kernel), \
             patch("msvcrt.get_osfhandle", side_effect=lambda fd: 100 + fd):
            restore = _enable_windows_console(input_stream, output)
            restore()
        calls = [(call.args[0].value, call.args[1]) for call in kernel.SetConsoleMode.call_args_list]
        self.assertEqual(calls, [(101, 7), (100, 0), (100, 7), (101, 3)])
        kernel.SetConsoleMode.reset_mock()
        kernel.SetConsoleMode.side_effect = [1, 0, 1]
        with patch.object(ctypes, "WinDLL", return_value=kernel), \
             patch("msvcrt.get_osfhandle", side_effect=lambda fd: 100 + fd):
            with self.assertRaises(TerminalError):
                _enable_windows_console(input_stream, output)
        self.assertEqual(kernel.SetConsoleMode.call_args_list[-1].args[1], 3)


if __name__ == "__main__":
    unittest.main()
