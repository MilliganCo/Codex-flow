from pathlib import Path
import os
import tempfile
import types
import unittest
from unittest.mock import patch

from ascii_tree.app import Explorer
from ascii_tree.model import generate_tree
from ascii_tree.render import RenderSettings
from ascii_tree.terminal import ENTER, LEAVE, Terminal, run

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / ".tmp"
TMP.mkdir(exist_ok=True)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tree = generate_tree(42)
        self.app = Explorer(self.tree)

    def test_switch_modes_keeps_exact_object(self):
        frames = []
        for key, mode in (("1", "2d"), ("2", "3d"), ("3", "4d"), ("1", "2d")):
            self.app.handle_key(key)
            self.assertEqual(self.app.settings.mode, mode)
            self.assertIs(self.app.tree, self.tree)
            frames.append(self.app.frame())
        self.assertEqual(frames[0], frames[-1])
        self.assertNotEqual(frames[0], frames[1])

    def test_keys_camera_zoom_hyper_rotation_and_reset(self):
        self.app.handle_key("right")
        self.app.handle_key("up")
        self.app.handle_key("+")
        self.app.handle_key("3")
        self.app.handle_key("]")
        self.assertEqual(self.app.settings.yaw, 32.5)
        self.assertEqual(self.app.settings.pitch, -3)
        self.assertEqual(self.app.settings.angle4d, 7.5)
        self.assertGreater(self.app.settings.zoom, 1)
        self.app.handle_key("R")
        self.assertEqual(self.app.settings, RenderSettings(mode="4d"))

    def test_only_g_replaces_object_and_is_reproducible(self):
        self.app.handle_key("G")
        self.assertEqual(self.app.tree.seed, 43)
        self.assertEqual(self.app.tree, generate_tree(43))
        self.assertIsNot(self.app.tree, self.tree)

    def test_play_pause_and_4d_animation(self):
        self.app.handle_key("3")
        s = self.app.settings
        self.app.tick(0.1)
        self.assertEqual(self.app.settings, s)
        self.app.handle_key(" ")
        self.app.tick(0.1)
        self.assertGreater(self.app.settings.angle4d, s.angle4d)
        self.assertGreater(self.app.settings.yaw, s.yaw)
        self.assertEqual(self.app.settings.time, 0.1)
        self.app.handle_key(" ")
        s = self.app.settings
        self.app.tick(0.1)
        self.assertEqual(self.app.settings, s)
        self.assertIs(self.app.tree, self.tree)

    def test_2d_animation_is_visible_breeze(self):
        self.app.handle_key("1")
        before = self.app.frame()
        self.app.handle_key(" ")
        for _ in range(10):
            self.app.tick(0.1)
        self.assertNotEqual(before, self.app.frame())

    def test_help_and_quit(self):
        self.app.handle_key("?")
        self.assertTrue(self.app.help_visible)
        self.assertIn("XW rotation", self.app.screen(100, 40))
        self.app.handle_key("H")
        self.assertFalse(self.app.help_visible)
        for key in ("q", "escape", "\x03"):
            self.assertEqual(self.app.handle_key(key), "quit")
            self.assertTrue(self.app.quitting)

    def test_zoom_and_pitch_clamps(self):
        for _ in range(100):
            self.app.handle_key("+")
            self.app.handle_key("up")
        self.assertEqual(self.app.settings.zoom, 5)
        self.assertEqual(self.app.settings.pitch, 80)
        for _ in range(100):
            self.app.handle_key("-")
            self.app.handle_key("down")
        self.assertEqual(self.app.settings.zoom, .15)
        self.assertEqual(self.app.settings.pitch, -80)

    def test_all_sizes_including_minimum(self):
        for width, height in ((100, 40), (20, 10), (5, 3), (1, 1), (0, 0)):
            for help_visible in (False, True):
                self.app.help_visible = help_visible
                screen = self.app.screen(width, height)
                self.assertEqual(len(screen.splitlines()), max(1, height))
                self.assertTrue(all(len(line) == max(1, width) for line in screen.splitlines()))
                self.assertTrue(screen.isascii())

    def test_export_is_tree_only_and_never_overwrites(self):
        with tempfile.TemporaryDirectory(dir=TMP) as directory:
            self.app.resize(80, 36)
            self.app.help_visible = True
            first = self.app.export(Path(directory))
            data = first.read_bytes()
            other_session = Explorer(self.tree, self.app.settings)
            second = other_session.export(Path(directory))
            self.assertNotEqual(first, second)
            self.assertEqual(data, second.read_bytes())
            self.assertEqual(len(data.splitlines()), 30)
            self.assertTrue(all(len(line) == 80 for line in data.splitlines()))
            self.assertNotIn(b"\x1b", data)
            self.assertNotIn(b"EXPLORER", data)


class TerminalTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows keyboard backend")
    def test_windows_extended_arrow_and_raw_ctrl_c(self):
        keys = iter(("\xe0", "M", "\x03", "q"))
        remaining = [4]

        def getwch():
            remaining[0] -= 1
            return next(keys)

        keyboard = types.SimpleNamespace(kbhit=lambda: remaining[0] > 0, getwch=getwch)
        with patch.dict("sys.modules", {"msvcrt": keyboard}):
            self.assertEqual(Terminal().read_keys(), ["right", "\x03", "q"])

    def test_split_posix_arrows_and_escape(self):
        terminal = Terminal()
        terminal.pending = "\x1b["
        self.assertEqual(terminal.decode_pending(0), [])
        terminal.pending += "Ah"
        self.assertEqual(terminal.decode_pending(.02), ["up", "h"])
        terminal.pending = "\x1b"
        self.assertEqual(terminal.decode_pending(1), [])
        self.assertEqual(terminal.decode_pending(1.07), ["escape"])

    def test_startup_resize_switch_export_and_shutdown(self):
        class ScriptedTerminal:
            def __init__(self):
                self.index = 0
                self.closed = False
                self.screens = []
                self.script = [[], ["3"], ["]"], [" "], [], [" "], ["e"], ["2"], ["1"], ["h"], ["h"], ["g"], ["r"], ["q"]]

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.closed = True

            def read_keys(self):
                keys = self.script[self.index]
                self.index += 1
                return keys

            def size(self):
                return (100, 39) if self.index < 8 else (12, 5)

            def draw(self, screen):
                self.screens.append(screen)

        terminal = ScriptedTerminal()
        app = Explorer(generate_tree(42))
        now = iter(i * .1 for i in range(100))
        with tempfile.TemporaryDirectory(dir=TMP) as directory:
            result = run(app, Path(directory), terminal_factory=lambda: terminal,
                         clock=lambda: next(now), sleeper=lambda _: None)
            self.assertEqual(result, 0)
            self.assertEqual(len(list(Path(directory).glob("*.txt"))), 1)
        self.assertTrue(terminal.closed)
        self.assertTrue(any("[4D]" in screen for screen in terminal.screens))
        self.assertEqual(app.tree.seed, 43)
        self.assertLessEqual(len(terminal.screens), len(terminal.script))
        self.assertEqual(len(terminal.screens[-1].splitlines()), 5)

    def test_keyboard_interrupt_always_leaves_terminal(self):
        class Interrupted:
            closed = False

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.closed = True

            def read_keys(self):
                raise KeyboardInterrupt

        terminal = Interrupted()
        self.assertEqual(run(Explorer(generate_tree()), TMP, terminal_factory=lambda: terminal), 0)
        self.assertTrue(terminal.closed)

    def test_ansi_lifecycle_and_draw_do_not_append_frames(self):
        import io
        stream = io.StringIO()
        with patch("sys.stdout", stream):
            Terminal.draw("abc\ndef")
        self.assertEqual(stream.getvalue(), "\x1b[H\x1b[Jabc\r\ndef")
        self.assertIn("\x1b[?25h", LEAVE)
        self.assertIn("\x1b[?1049l", LEAVE)
        self.assertIn("\x1b[?1049h", ENTER)
