from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import io
import os

from ascii_tree.app import Explorer, compose
from ascii_tree.render import View, render_tree
from ascii_tree.terminal import ENTER, LEAVE, Terminal, run

ROOT = Path(__file__).resolve().parents[1]
(ROOT/'.tmp').mkdir(exist_ok=True)


class AppTests(unittest.TestCase):
    def test_switching_modes_preserves_object(self):
        app = Explorer()
        original = app.tree
        for key, mode in [('1', '2d'), ('2', '3d'), ('3', '4d'), ('2', '3d')]:
            app.handle(key)
            self.assertEqual(app.view.mode, mode)
            self.assertIs(app.tree, original)
        app.handle('G')
        self.assertEqual(app.seed, 43)
        self.assertIsNot(app.tree, original)

    def test_controls_animation_reset(self):
        app = Explorer()
        original = app.tree
        for key in ('3', 'right', 'up', ']', '+'):
            app.handle(key)
        self.assertNotEqual(app.view, View(mode='4d'))
        self.assertEqual(app.view.angle4d, 8)
        app.handle(' ')
        app.tick(.5)
        self.assertEqual(app.view.time, .5)
        app.handle(' ')
        paused = app.view
        app.tick(10)
        self.assertEqual(app.view, paused)
        app.handle('R')
        self.assertEqual(app.view, View(mode='4d'))
        self.assertIs(app.tree, original)
        app.handle('h')
        self.assertTrue(app.help_open)
        app.handle('?')
        self.assertFalse(app.help_open)
        for key in ('q', 'esc', 'ctrl+c'):
            app = Explorer()
            app.handle(key)
            self.assertFalse(app.running)

    def test_resize_and_minimum_layout(self):
        app = Explorer(view=View(mode='4d'))
        for help_open in (False, True):
            app.help_open = help_open
            for width, height in ((1, 1), (3, 2), (15, 4), (16, 5), (80, 30), (100, 40)):
                lines, frame_size = compose(app, width, height)
                self.assertEqual(len(lines), height)
                self.assertTrue(all(len(line) == width for line in lines))
                self.assertTrue(all(value > 0 for value in frame_size))

    def test_export_is_current_clean_frame_and_preserves_existing_files(self):
        app = Explorer(view=View(mode='4d', angle4d=37, time=3))
        with tempfile.TemporaryDirectory(dir=ROOT/'.tmp') as directory:
            first = app.export(80, 30, Path(directory))
            expected = render_tree(app.tree, 80, 30, app.view).encode('ascii')
            self.assertEqual(first.read_bytes(), expected)
            # New session at the same seed must not overwrite this export.
            second = Explorer().export(80, 30, Path(directory))
            third = Explorer(view=View(mode='4d')).export(80, 30, Path(directory))
            self.assertEqual(first.read_bytes(), expected)
            self.assertNotEqual(first, third)
            self.assertNotEqual(first, second)

    def test_ui_loop_lifecycle_simulated_resize_and_quit(self):
        app = Explorer()
        output = io.StringIO()
        with patch('ascii_tree.terminal.Terminal') as terminal, patch('ascii_tree.terminal.sys.stdout', output), \
             patch('ascii_tree.terminal.shutil.get_terminal_size', side_effect=[os.terminal_size(s) for s in ((100, 40), (3, 2), (80, 30))]), \
             patch('ascii_tree.terminal.time.sleep'):
            terminal.return_value.__enter__.return_value.keys.side_effect = [['3', ']'], ['h'], ['q']]
            self.assertEqual(run(app, Path.cwd()), 0)
            terminal.return_value.__exit__.assert_called_once()
        self.assertEqual(app.view.mode, '4d')
        self.assertIn('4D', output.getvalue())
        self.assertIn('XW 8', output.getvalue())
        self.assertFalse(app.running)

    def test_loop_restores_on_interrupt_and_io_error(self):
        for exception, expected in ((KeyboardInterrupt, 0), (OSError, None)):
            with patch('ascii_tree.terminal.Terminal') as terminal:
                terminal.return_value.__enter__.return_value.keys.side_effect = exception
                if expected is None:
                    with self.assertRaises(OSError):
                        run(Explorer(), Path.cwd())
                else:
                    self.assertEqual(run(Explorer(), Path.cwd()), expected)
                terminal.return_value.__exit__.assert_called_once()
