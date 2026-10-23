"""Finite Windows-native integration test; launch inside a real terminal.

Injects KEY_EVENT records into this process's own console, exercises the real
adapter and controller, checks both console modes after Q and Ctrl+C. No GUI,
external application, third-party package or global configuration is involved.
"""

import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.app import Explorer
from ascii_tree.geometry import View
from ascii_tree.model import generate_tree
from ascii_tree.render import render
from ascii_tree.terminal import Terminal


def console_modes():
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetConsoleMode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    result = []
    for stream in (sys.stdin, sys.stdout):
        mode = wintypes.DWORD()
        assert kernel.GetConsoleMode(msvcrt.get_osfhandle(stream.fileno()), ctypes.byref(mode))
        result.append(mode.value)
    return result


class ProbeTerminal(Terminal):
    def __init__(self, keys):
        super().__init__()
        self.keys = iter(keys)
        self.deadline = time.monotonic() + 10
        self.frames = []

    def draw(self, frame):
        self.frames.append(frame)
        super().draw(frame)

    def read_keys(self, timeout):
        assert time.monotonic() < self.deadline, 'Native TTY test timed out'
        char, virtual = next(self.keys, ('q', 0x51))
        source = self._windows_input
        records = (source.Record * 2)()
        for index in range(2):
            records[index].EventType = 1
            key = records[index].Event.KeyEvent
            key.bKeyDown = index == 0
            key.wRepeatCount = 1
            key.wVirtualKeyCode = virtual
            key.uChar.UnicodeChar = char
        source.kernel.WriteConsoleInputW.argtypes = (ctypes.c_void_p, ctypes.POINTER(source.Record),
                                                     source.DWORD, ctypes.POINTER(source.DWORD))
        count = source.DWORD()
        assert source.kernel.WriteConsoleInputW(source.handle, records, 2, ctypes.byref(count))
        assert count.value == 2
        return super().read_keys(timeout)


def main():
    if os.name != 'nt' or not sys.stdin.isatty() or not sys.stdout.isatty():
        print('NOT RUN: requires Windows and a real input/output TTY')
        return 2
    original_modes = console_modes()
    (ROOT / '.tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as directory:
        keys = [('1', 0x31), ('e', 0x45), ('2', 0x32), ('e', 0x45), ('3', 0x33),
                ('e', 0x45), (']', 0xDD), ('e', 0x45), ('\x00', 0x27), ('\x00', 0x26),
                ('+', 0xBB), ('h', 0x48), ('h', 0x48), (' ', 0x20), (' ', 0x20), ('q', 0x51)]
        terminal = ProbeTerminal(keys)
        app = Explorer(export_dir=Path(directory))
        identity = app.tree
        app.run(terminal)
        assert app.tree is identity
        assert (app.view.mode, app.view.yaw, app.view.pitch, app.view.angle4) == ('4d', 350, 13, 10)
        assert app.view.zoom > 1 and not app.animating
        assert console_modes() == original_modes, 'Q did not restore console modes'
        files = sorted(Path(directory).glob('*.txt'))
        assert len(files) == 4
        assert len({path.read_bytes() for path in files}) == 4
        assert any('HELP' in f.text() for f in terminal.frames)
        # First export must be the shared tree, not a different 2D generator.
        expected = render(generate_tree(42), View(mode='2d'), *app.viewport).text().encode('ascii')
        assert (Path(directory) / 'tree-42-2d-001.txt').read_bytes() == expected
    ctrl_c_clean = False
    try:
        Explorer().run(ProbeTerminal([('\x03', 0x43)]))
    except KeyboardInterrupt:
        ctrl_c_clean = True
    assert ctrl_c_clean, 'Native Ctrl+C key was lost'
    assert console_modes() == original_modes, 'Ctrl+C did not restore console modes'
    escaped = Explorer()
    escaped.run(ProbeTerminal([('\x1b', 0x1B)]))
    assert not escaped.running
    assert console_modes() == original_modes, 'Esc did not restore console modes'
    report = {'result': 'PASS', 'platform': sys.platform, 'python': sys.version.split()[0],
              'native_console_key_events': True, 'mode_switches_keep_tree': True,
              'camera_xw_zoom_help_animation_export': True, 'q_restores_console_modes': True,
              'ctrl_c_restores_console_modes': True, 'escape_restores_console_modes': True,
              'physical_resize': 'NOT RUN'}
    destination = ROOT / 'verification'
    destination.mkdir(exist_ok=True)
    (destination / 'native-tty.json').write_text(json.dumps(report, indent=2) + '\n', encoding='ascii')
    print('PASS: native Windows TTY, keys, projections, exports, Q, Esc, Ctrl+C and console restoration')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
