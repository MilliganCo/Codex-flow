from dataclasses import replace
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from io import StringIO
from ascii_tree.render import render
from ascii_tree.state import Explorer
from ascii_tree.terminal import compose_screen, Terminal, run_view

ROOT = Path(__file__).resolve().parents[1]


class InteractionTests(unittest.TestCase):
    def test_modes_preserve_object_identity(self):
        state=Explorer(42)
        tree=state.tree
        for key,mode in (("1","2d"),("2","3d"),("3","4d"),("2","3d")):
            state.handle(key)
            self.assertEqual(state.mode,mode)
            self.assertIs(state.tree,tree)
            self.assertEqual(state.seed,42)

    def test_controls_animation_and_reset(self):
        state=Explorer(42, "4d")
        for key in ("right","up","]","+","h"," "):
            state.handle(key)
        self.assertTrue(state.help_visible)
        self.assertTrue(state.animated)
        before=state.angle4
        state.advance(.3)
        self.assertGreater(state.angle4,before)
        state.handle(" ")
        before=state.angle4
        state.advance(.3)
        self.assertEqual(state.angle4,before)
        state.handle("r")
        self.assertEqual((state.yaw,state.pitch,state.angle4,state.zoom),(.45,.08,0.,1.))
        old=state.tree
        state.handle("G")
        self.assertEqual(state.seed,43)
        self.assertIsNot(state.tree,old)
        state.handle("escape")
        self.assertFalse(state.running)

    def test_2d_ignores_orbit_and_xw(self):
        state=Explorer(42,"2d")
        before=state.options(80,30)
        for key in ("left","up", "]", " "):
            state.handle(key)
        state.advance(1)
        self.assertEqual(state.options(80,30),before)

    def test_narrow_ui_and_help_never_overflow(self):
        state=Explorer(42,"4d")
        for width,height in ((1,1),(5,3),(20,8),(99,40)):
            for help_visible in (False,True):
                state.help_visible=help_visible
                frame=render(state.tree,state.options(width,max(1,height-5)))
                lines=compose_screen(state,frame,width,height).removeprefix("\x1b[H").split("\r\n")
                self.assertEqual(len(lines),height)
                self.assertTrue(all(len(line)==width for line in lines))

    def test_context_restores_after_interrupt_simulation(self):
        # This only tests context-manager semantics. Real Windows test is separate.
        with patch.object(Terminal,"__enter__",return_value=Terminal()), patch.object(Terminal,"restore") as restore:
            with self.assertRaises(KeyboardInterrupt):
                with Terminal():
                    raise KeyboardInterrupt
            restore.assert_called_once()

    def test_export_key_before_first_draw_produces_complete_frame(self):
        # Event-loop simulation, distinct from the native ConPTY suite.
        class InputTerminal:
            def __init__(self):
                self.keys=iter(("e","q"))
            def __enter__(self):
                return self
            def __exit__(self,*args):
                pass
            def size(self):
                return 80,30
            def read_key(self):
                return next(self.keys)
        with tempfile.TemporaryDirectory() as tmp, patch("ascii_tree.terminal.Terminal",InputTerminal), \
             patch("sys.stdin.isatty",return_value=True), patch("sys.stdout",new_callable=StringIO) as output:
            with patch.object(output,"isatty",return_value=True):
                self.assertEqual(run_view(Explorer(42),Path(tmp)),0)
            data=(Path(tmp)/"tree-42-3d.txt").read_bytes()
            self.assertEqual(len(data),81*25)
            self.assertEqual(len(data.splitlines()),25)


class CLITests(unittest.TestCase):
    def cli(self,*args):
        return subprocess.run([sys.executable,"-m","ascii_tree",*args],cwd=ROOT,
                              capture_output=True,timeout=15)

    def test_help_startup_shutdown(self):
        result=self.cli("--help")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn(b"render",result.stdout)

    def test_headless_same_arguments_same_bytes(self):
        args=("render","--seed","42","--mode","4d","--angle4","35","--time","2",
              "--width","80","--height","30")
        a,b=self.cli(*args),self.cli(*args)
        self.assertEqual(a.returncode,0,a.stderr)
        self.assertEqual(a.stdout,b.stdout)
        self.assertEqual(len(a.stdout),81*30)

    def test_export_matches_stdout(self):
        args=("render","--seed","42","--mode","2d","--width","100","--height","40")
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"frame.txt"
            a=self.cli(*args)
            b=self.cli(*args,"--output",str(path))
            self.assertEqual(b.returncode,0,b.stderr)
            self.assertEqual(a.stdout,path.read_bytes())
            self.assertEqual(b.stdout,b"")

    def test_view_without_tty_is_finite_clear_error(self):
        result=self.cli("view")
        self.assertEqual(result.returncode,2)
        self.assertIn(b"interactive TTY",result.stderr)
        self.assertNotIn(b"\x1b",result.stdout)

    def test_bad_inputs_are_finite_errors(self):
        for args in (("render","--width","0"),("render","--angle4","nan"),
                     ("render","--time","inf"),("view","--zoom","-1"),
                     ("render","--mode","5d")):
            result=self.cli(*args)
            self.assertEqual(result.returncode,2)
            self.assertNotIn(b"Traceback",result.stderr)

    def test_animation_time_changes_headless_frame(self):
        a=self.cli("render","--mode","4d","--time","0")
        b=self.cli("render","--mode","4d","--time","3")
        self.assertNotEqual(a.stdout,b.stdout)
