from dataclasses import replace
import io
from pathlib import Path
import tempfile
import unittest

from ascii_tree.app import ExplorerState, compose_screen, image_size
from ascii_tree.render import RenderOptions, frame_bytes, render_frame
from ascii_tree.terminal import Terminal, run_interactive

ROOT = Path(__file__).resolve().parents[1]


class AppTests(unittest.TestCase):
    def setUp(self):
        self.state = ExplorerState()
        (ROOT / ".tmp").mkdir(exist_ok=True)

    def test_switching_and_camera_controls_preserve_same_object(self):
        original = self.state.tree
        for key, mode in (("1", "2d"), ("2", "3d"), ("3", "4d")):
            self.assertTrue(self.state.handle_key(key))
            self.assertEqual(self.state.settings.mode, mode)
            self.assertIs(self.state.tree, original)
        for key in ("left", "right", "up", "down", "[", "]", "+", "-", "r"):
            self.state.handle_key(key)
            self.assertIs(self.state.tree, original)

    def test_real_keys_change_camera_xw_and_zoom_then_reset(self):
        self.state.handle_key("3")
        before = self.state.settings
        for key in ("right", "up", "]", "+"):
            self.state.handle_key(key)
        o = self.state.settings
        self.assertNotEqual(o.yaw, before.yaw)
        self.assertNotEqual(o.pitch, before.pitch)
        self.assertEqual(o.angle4, 8)
        self.assertGreater(o.zoom, 1)
        self.state.handle_key("r")
        self.assertEqual(self.state.settings, replace(RenderOptions(), mode="4d"))

    def test_new_seed_is_only_regeneration_control(self):
        old = self.state.tree
        self.state.handle_key("G")
        self.assertEqual(self.state.seed, 43)
        self.assertIsNot(old, self.state.tree)
        self.assertNotEqual(old.nodes, self.state.tree.nodes)

    def test_pause_help_and_animation(self):
        self.assertFalse(self.state.tick(0.1))
        self.state.handle_key(" ")
        self.assertTrue(self.state.tick(0.1))
        before = self.state.settings.time
        self.state.handle_key("?")
        self.assertTrue(self.state.help_visible)
        self.assertFalse(self.state.tick(0.1))
        self.assertEqual(self.state.settings.time, before)
        self.state.handle_key("h")
        self.state.handle_key(" ")
        self.assertFalse(self.state.playing)

    def test_export_matches_current_frame_and_preserves_existing_file(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            self.state.export_dir = Path(directory)
            self.state.handle_key("3")
            self.state.handle_key("]")
            first = self.state.export(80, 30)
            second = self.state.export(80, 30)
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), frame_bytes(self.state.tree, self.state.options(80, 30)))
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertNotIn(b"\x1b", first.read_bytes())

    def test_export_error_remains_in_ui_without_crashing(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            blocker = Path(directory) / "file"
            blocker.write_text("keep", encoding="ascii")
            self.state.export_dir = blocker
            self.state.handle_key("e")
            self.assertIn("Export failed", self.state.message)
            self.assertEqual(blocker.read_text(), "keep")

    def test_tiny_window_export_is_the_visible_image(self):
        width, height = image_size(20, 8)
        screen = compose_screen(self.state, 20, 8)
        self.assertEqual(screen[1:], render_frame(self.state.tree, self.state.options(width, height)))
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            self.state.export_dir = Path(directory)
            self.assertEqual(self.state.export(width, height).read_bytes(),
                             ("\n".join(screen[1:]) + "\n").encode("ascii"))

    def test_all_layouts_resize_and_stay_ascii(self):
        for help_visible in (False, True):
            self.state.help_visible = help_visible
            for columns, rows in ((1, 1), (2, 2), (15, 6), (36, 10), (80, 30), (100, 40)):
                with self.subTest(help=help_visible, size=(columns, rows)):
                    lines = compose_screen(self.state, columns, rows)
                    self.assertEqual(len(lines), rows)
                    self.assertTrue(all(len(line) == max(1, columns - 1) for line in lines))
                    self.assertTrue(all(line.isascii() for line in lines))
        self.assertEqual(image_size(0, 0), (1, 1))

    def test_zoom_and_pitch_clamped_under_repeated_input(self):
        for _ in range(100):
            self.state.handle_key("+")
            self.state.handle_key("up")
        self.assertEqual(self.state.settings.zoom, 8)
        self.assertEqual(self.state.settings.pitch, 80)
        for _ in range(100):
            self.state.handle_key("-")
            self.state.handle_key("down")
        self.assertEqual(self.state.settings.zoom, 0.1)
        self.assertEqual(self.state.settings.pitch, -80)

    def test_all_quit_keys(self):
        for key in ("q", "Q", "escape", "ctrl-c"):
            self.state.quit = False
            self.state.handle_key(key)
            self.assertTrue(self.state.quit)


class ScriptedTerminal:
    def __init__(self, keys):
        self.keys = iter(keys)
        self.entered = self.exited = False
        self.draws = []
        self.count = 0

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *args):
        self.exited = True

    def size(self):
        return ((100, 40), (12, 5), (1, 1), (100, 40))[min(self.count, 3)]

    def draw(self, lines):
        self.draws.append(lines)

    def read_key(self, timeout):
        self.count += 1
        key = next(self.keys)
        if isinstance(key, BaseException):
            raise key
        return key


class LifecycleTests(unittest.TestCase):
    def run_script(self, terminal):
        ticks = iter(i * 0.12 for i in range(100))
        state = ExplorerState()
        code = run_interactive(state, terminal_factory=lambda: terminal, clock=lambda: next(ticks))
        return code, state

    def test_startup_hotkeys_resize_and_clean_shutdown(self):
        terminal = ScriptedTerminal(["1", "2", "3", "]", "right", "up", "+", " ", " ", "h", "h", "g", "r", "q"])
        code, state = self.run_script(terminal)
        self.assertEqual(code, 0)
        self.assertTrue(terminal.entered and terminal.exited)
        self.assertGreater(len(terminal.draws), 10)
        self.assertEqual(state.seed, 43)
        self.assertTrue(any(len(frame) == 1 for frame in terminal.draws))
        self.assertTrue(any("4D data -> 3D -> 2D" in "\n".join(frame) for frame in terminal.draws))

    def test_ctrl_c_restores_console_and_returns_130(self):
        terminal = ScriptedTerminal([KeyboardInterrupt()])
        code, _ = self.run_script(terminal)
        self.assertEqual(code, 130)
        self.assertTrue(terminal.exited)

    def test_ctrl_c_key_restores_console_and_returns_130(self):
        terminal = ScriptedTerminal(["ctrl-c"])
        code, _ = self.run_script(terminal)
        self.assertEqual(code, 130)
        self.assertTrue(terminal.exited)

    def test_unexpected_exception_also_restores_console(self):
        terminal = ScriptedTerminal([RuntimeError("test")])
        with self.assertRaises(RuntimeError):
            self.run_script(terminal)
        self.assertTrue(terminal.exited)

    def test_console_exit_restores_cursor_alternate_screen_and_windows_mode(self):
        stream = io.StringIO()
        terminal = Terminal(stdout=stream)
        calls = []

        class Kernel:
            def SetConsoleMode(self, handle, mode):
                calls.append((handle, mode))

        terminal.win_mode = Kernel(), 123, 7
        terminal.win_input_mode = Kernel(), 456, 3
        terminal.__exit__(None, None, None)
        self.assertIn("\x1b[?25h", stream.getvalue())
        self.assertIn("\x1b[?1049l", stream.getvalue())
        self.assertEqual(calls, [(456, 3), (123, 7)])
