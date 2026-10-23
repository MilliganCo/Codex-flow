from pathlib import Path
import unittest

from ascii_tree.app import Explorer
from ascii_tree.geometry import View
from ascii_tree.terminal import Terminal
from tests.support import temporary_directory


class ScriptedTerminal:
    def __init__(self, keys, sizes=((100, 40),)):
        self.keys = list(keys)
        self.sizes = sizes
        self.position = 0
        self.frames = []
        self.entered = self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *args):
        self.exited = True

    def size(self):
        return self.sizes[min(self.position, len(self.sizes) - 1)]

    def draw(self, frame):
        self.frames.append(frame)

    def read_keys(self, timeout):
        self.position += 1
        if self.keys:
            key = self.keys.pop(0)
            if isinstance(key, BaseException):
                raise key
            return [key]
        return ['q']


class AppTests(unittest.TestCase):
    def test_switches_keep_exact_same_object_and_seed(self):
        app = Explorer()
        tree = app.tree
        for key, mode in (('1', '2d'), ('2', '3d'), ('3', '4d'), ('1', '2d')):
            app.handle(key)
            self.assertEqual(app.view.mode, mode)
            self.assertIs(app.tree, tree)
            self.assertEqual(app.seed, 42)
        app.handle('G')
        self.assertIsNot(app.tree, tree)
        self.assertNotEqual(app.tree.segments, tree.segments)

    def test_camera_4d_zoom_and_reset(self):
        app = Explorer()
        app.handle('3')
        for key in ('right', 'up', ']', '+'):
            app.handle(key)
        self.assertEqual((app.view.yaw, app.view.pitch, app.view.angle4), (350, 13, 10))
        self.assertGreater(app.view.zoom, 1)
        app.handle('r')
        self.assertEqual(app.view, View(mode='4d'))
        app.handle('1')
        previous = app.view
        for key in ('left', 'up', ']'):
            app.handle(key)
        self.assertEqual(app.view, previous)

    def test_animation_pause_and_resume(self):
        app = Explorer()
        app.advance(.1)
        self.assertEqual(app.view.time, 0)
        app.handle('space')
        app.advance(.1)
        self.assertAlmostEqual(app.view.time, .1)
        app.handle('space')
        app.advance(.1)
        self.assertAlmostEqual(app.view.time, .1)

    def test_export_matches_visible_viewport_and_does_not_overwrite(self):
        with temporary_directory() as directory:
            app = Explorer(export_dir=Path(directory))
            app.screen(80, 30)
            frame = app.last_frame.text().encode('ascii')
            app.handle('e')
            app.handle('e')
            targets = sorted(Path(directory).glob('*.txt'))
            self.assertEqual(len(targets), 2)
            self.assertTrue(all(t.read_bytes() == frame for t in targets))
            self.assertTrue(app.notice.startswith('Saved:'))

    def test_export_error_is_recoverable(self):
        with temporary_directory() as directory:
            target = Path(directory) / 'file'
            target.write_text('existing', encoding='ascii')
            app = Explorer(export_dir=target)
            app.handle('e')
            self.assertTrue(app.notice.startswith('Export failed:'))
            self.assertTrue(app.running)
            self.assertEqual(target.read_text(encoding='ascii'), 'existing')

    def test_tiny_resizes_help_and_ascii_screen(self):
        app = Explorer()
        for size in ((1, 1), (2, 2), (9, 4), (20, 10), (100, 40)):
            for help_open in (False, True):
                app.help_open = help_open
                frame = app.screen(*size)
                self.assertEqual(frame.width, size[0])
                self.assertEqual(frame.height, max(1, size[1] - 1))
                self.assertTrue(all(32 <= ord(c) <= 126 for row in frame.lines for c in row))

    def test_real_event_loop_scripted_switches_resize_and_shutdown(self):
        terminal = ScriptedTerminal(['1', '2', '3', ']', 'h', 'down', 'h', 'space', 'q'],
                                    ((100, 40), (80, 30), (8, 3), (1, 1), (100, 40)))
        app = Explorer()
        app.run(terminal)
        self.assertTrue(terminal.entered and terminal.exited)
        self.assertFalse(app.running)
        self.assertGreater(len(terminal.frames), 5)
        self.assertEqual(app.view.mode, '4d')
        self.assertEqual(app.view.angle4, 10)

    def test_keyboard_interrupt_unwinds_context(self):
        terminal = ScriptedTerminal([KeyboardInterrupt()])
        with self.assertRaises(KeyboardInterrupt):
            Explorer().run(terminal)
        self.assertTrue(terminal.exited)

    def test_ctrl_c_key_unwinds_context(self):
        terminal = ScriptedTerminal(['\x03'])
        with self.assertRaises(KeyboardInterrupt):
            Explorer().run(terminal)
        self.assertTrue(terminal.exited)

    def test_windows_keys_include_ctrl_c_arrows_and_repeats(self):
        from ascii_tree.winconsole import decode_key
        self.assertEqual(decode_key(True, '\x03', 0x43), ['\x03'])
        self.assertEqual(decode_key(True, '\x00', 0x25, 2), ['left', 'left'])
        self.assertEqual(decode_key(True, ' ', 0x20), ['space'])
        self.assertEqual(decode_key(False, 'q', 0x51), [])
        self.assertEqual(decode_key(True, '\x00', 0x10), [])

    def test_paused_loop_does_not_redraw_without_changes(self):
        class IdleTerminal(ScriptedTerminal):
            def read_keys(self, timeout):
                self.position += 1
                return ['q'] if self.position == 5 else []
        terminal = IdleTerminal([])
        Explorer().run(terminal)
        self.assertEqual(len(terminal.frames), 1)

    def test_posix_arrow_fragments_and_standalone_escape(self):
        terminal = Terminal()
        terminal._pending = '\x1b['
        terminal._pending_since = 1
        self.assertEqual(terminal._parse_pending(1.01), [])
        terminal._pending += 'A'
        self.assertEqual(terminal._parse_pending(1.02), ['up'])
        terminal._pending = '\x1b'
        self.assertEqual(terminal._parse_pending(1.2), ['escape'])
        terminal._pending = '\x1bOC +q'
        self.assertEqual(terminal._parse_pending(2), ['right', 'space', '+', 'q'])

    def test_terminal_rejects_non_tty(self):
        import io
        with self.assertRaises(OSError):
            with Terminal(io.StringIO(), io.StringIO()):
                self.fail('Non-TTY accepted')

    def test_terminal_draw_uses_cursor_updates_and_cleanup_restores(self):
        import io
        from ascii_tree.render import Frame
        stream = io.StringIO()
        terminal = Terminal(output_stream=stream)
        terminal.draw(Frame(('abc', 'def')))
        restored = []
        terminal._entered = True
        terminal._restore = lambda: restored.append(True)
        terminal.__exit__(None, None, None)
        self.assertIn('\x1b[2;1Hdef', stream.getvalue())
        self.assertIn('\x1b[?25h\x1b[?1049l', stream.getvalue())
        self.assertEqual(restored, [True])


if __name__ == '__main__':
    unittest.main()
