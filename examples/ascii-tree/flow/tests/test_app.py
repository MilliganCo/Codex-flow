import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ascii_tree.app import Explorer
from ascii_tree.render import render
from ascii_tree.terminal import KeyDecoder, Terminal, run_interactive, windows_key


class AppTests(unittest.TestCase):
    def setUp(self):
        self.app = Explorer()

    def test_switch_modes_preserves_same_object(self):
        tree = self.app.tree
        for key, mode in (("1", "2d"), ("2", "3d"), ("3", "4d"), ("1", "2d")):
            self.app.handle(key)
            self.assertEqual(self.app.options.mode, mode)
            self.assertIs(self.app.tree, tree)

    def test_camera_and_xw_controls(self):
        self.app.handle("left")
        self.assertEqual(self.app.options.yaw, 17)
        self.app.handle("up")
        self.assertEqual(self.app.options.pitch, -14)
        self.app.handle("3")
        self.app.handle("]")
        self.assertEqual(self.app.options.angle4d, 8)
        self.app.handle("[")
        self.assertEqual(self.app.options.angle4d, 0)
        self.app.handle("1")
        old = self.app.options
        self.app.handle("left")
        self.app.handle("]")
        self.assertEqual(self.app.options, old)

    def test_animation_pause_reset_and_new_seed(self):
        tree = self.app.tree
        self.app.handle(" ")
        self.app.tick(0.1)
        self.assertAlmostEqual(self.app.options.time, 0.1)
        self.app.handle(" ")
        self.app.tick(0.1)
        self.assertAlmostEqual(self.app.options.time, 0.1)
        self.app.handle("+")
        self.assertGreater(self.app.options.zoom, 1)
        self.app.handle("r")
        self.assertEqual(self.app.options.zoom, 1)
        self.assertEqual(self.app.options.time, 0)
        self.assertFalse(self.app.animated)
        self.assertIs(self.app.tree, tree)
        self.app.handle("g")
        self.assertEqual(self.app.seed, 43)
        self.assertIsNot(self.app.tree, tree)

    def test_zoom_limits_and_pitch_limits(self):
        for _ in range(100):
            self.app.handle("+")
            self.app.handle("up")
        self.assertEqual(self.app.options.zoom, 5)
        self.assertEqual(self.app.options.pitch, -80)
        for _ in range(100):
            self.app.handle("-")
            self.app.handle("down")
        self.assertEqual(self.app.options.zoom, 0.15)
        self.assertEqual(self.app.options.pitch, 80)

    def test_help_and_resize_down_to_one_cell(self):
        for size in ((100, 40), (25, 12), (8, 4), (1, 1), (0, 0), (80, 30)):
            for key in ("h", "?"):
                self.app.handle(key)
                screen = self.app.screen(*size)
                lines = screen.splitlines()
                self.assertEqual(len(lines), max(1, size[1] - 1))
                self.assertTrue(all(len(line) == max(1, size[0] - 1) for line in lines))
                self.assertTrue(screen.isascii())
        self.app.handle("3")
        self.assertIn("4D data -> 3D -> 2D", self.app.screen(100, 40))

    def test_export_exact_raster_even_with_help_or_queued_mode_key(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            self.app.export_dir = Path(directory)
            self.app.screen(100, 40)
            self.app.handle("3")
            self.app.handle("h")
            self.app.handle("e")
            files = list(Path(directory).glob("*.txt"))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_bytes(), render(self.app.tree, self.app.options).encode("ascii"))
            self.assertNotIn(b"HELP", files[0].read_bytes())
            # New sessions must never overwrite an existing frame.
            first = files[0].read_bytes()
            self.app.exports = 0
            self.app.handle("e")
            self.assertEqual(len(list(Path(directory).glob("*.txt"))), 2)
            self.assertEqual(files[0].read_bytes(), first)

    def test_failed_export_is_nonfatal(self):
        with patch("ascii_tree.app.Path.mkdir", side_effect=PermissionError("denied")):
            self.app.handle("e")
        self.assertIn("Export failed", self.app.status)
        self.assertTrue(self.app.running)

    def test_unknown_key_and_quit(self):
        self.assertFalse(self.app.handle("unknown"))
        for key in ("q", "Q", "escape", "ctrl+c"):
            app = Explorer()
            app.handle(key)
            self.assertFalse(app.running)


class DecoderTests(unittest.TestCase):
    def test_windows_arrows_and_composed_punctuation(self):
        self.assertEqual(windows_key(True, 0x27, "\x00"), "right")
        self.assertEqual(windows_key(False, 0x27, "\x00"), "")
        self.assertEqual(windows_key(True, 0x12, "\x00"), "")
        self.assertEqual(windows_key(False, 0x12, "]"), "]")
        self.assertEqual(windows_key(False, 0x12, "["), "[")
        self.assertEqual(windows_key(True, 0, "g"), "g")
        self.assertEqual(windows_key(False, 0, "g"), "")

    def test_fragmented_arrows_and_escape(self):
        d = KeyDecoder()
        self.assertEqual(d.feed("\x1b", 1), [])
        self.assertEqual(d.flush(1.02), [])
        self.assertEqual(d.feed("[", 1.02), [])
        self.assertEqual(d.feed("A", 1.03), ["up"])
        self.assertEqual(d.feed("\x1b[D\x1b[C\x1b[B", 2), ["left", "right", "down"])
        self.assertEqual(d.feed("\x1b", 3), [])
        self.assertEqual(d.flush(3.1), ["escape"])

    def test_regular_keys_and_control_c(self):
        d = KeyDecoder()
        self.assertEqual(d.feed("123[]+- G\x03", 1), ["1", "2", "3", "[", "]", "+", "-", " ", "G", "ctrl+c"])


class ScriptedTerminal:
    def __init__(self, interrupt=False):
        self.frames = []
        self.calls = 0
        self.restored = False
        self.interrupt = interrupt

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.restored = True

    def size(self):
        return ((100, 40), (30, 10), (1, 1), (80, 30))[min(self.calls, 3)]

    def draw(self, screen, resized=False):
        self.frames.append((screen, resized))

    def keys(self, timeout):
        if self.interrupt:
            raise KeyboardInterrupt
        script = (["1"], ["2"], ["3", "]", " "], ["q"])
        result = script[self.calls]
        self.calls += 1
        return result


class LifecycleTests(unittest.TestCase):
    def test_scripted_startup_switch_resize_and_shutdown(self):
        app = Explorer()
        tree = app.tree
        terminal = ScriptedTerminal()
        self.assertEqual(run_interactive(app, terminal), 0)
        self.assertTrue(terminal.restored)
        self.assertEqual(len(terminal.frames), 4)
        self.assertTrue(all(resized for _, resized in terminal.frames))
        self.assertIs(app.tree, tree)
        self.assertEqual(app.options.mode, "4d")

    def test_control_c_restores_terminal(self):
        terminal = ScriptedTerminal(interrupt=True)
        self.assertEqual(run_interactive(Explorer(), terminal), 0)
        self.assertTrue(terminal.restored)

    def test_actual_context_cleanup_on_error(self):
        output = io.StringIO()
        terminal = Terminal(stdout=output)
        restored = []
        def setup():
            terminal._restore.append(lambda: restored.append(True))
        with patch("ascii_tree.terminal.os.name", "nt"), patch.object(terminal, "_setup_windows", setup):
            with self.assertRaises(RuntimeError):
                with terminal:
                    raise RuntimeError("injected")
        self.assertEqual(restored, [True])
        self.assertIn("\x1b[?25l", output.getvalue())
        self.assertTrue(output.getvalue().endswith("\x1b[0m\x1b[?25h\x1b[?1049l"))

    def test_context_restores_partially_configured_terminal(self):
        terminal = Terminal(stdout=io.StringIO())
        restored = []
        def setup():
            terminal._restore.append(lambda: restored.append(True))
            raise OSError("injected setup failure")
        with patch("ascii_tree.terminal.os.name", "nt"), patch.object(terminal, "_setup_windows", setup):
            with self.assertRaises(OSError):
                terminal.__enter__()
        self.assertEqual(restored, [True])
