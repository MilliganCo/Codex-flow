"""Finite integration driver, launched in its own hidden Windows console.

This tests real msvcrt input and console VT output, without a visible window,
network, third-party terminal emulator or modifications to the user's console.
"""

import ctypes
from ctypes import wintypes as wt
import json
import msvcrt
from pathlib import Path
import sys

from ascii_tree.app import Explorer, run_loop
from ascii_tree.cli import main
from ascii_tree.terminal import Terminal


class Char(ctypes.Union):
    _fields_ = [("UnicodeChar", wt.WCHAR), ("AsciiChar", ctypes.c_char)]


class KeyEvent(ctypes.Structure):
    _fields_ = [("bKeyDown", wt.BOOL), ("wRepeatCount", wt.WORD),
                ("wVirtualKeyCode", wt.WORD), ("wVirtualScanCode", wt.WORD),
                ("uChar", Char), ("dwControlKeyState", wt.DWORD)]


class Event(ctypes.Union):
    _fields_ = [("KeyEvent", KeyEvent), ("padding", ctypes.c_byte * 16)]


class InputRecord(ctypes.Structure):
    _fields_ = [("EventType", wt.WORD), ("Event", Event)]


class Coord(ctypes.Structure):
    _fields_ = [("X", wt.SHORT), ("Y", wt.SHORT)]


class Rect(ctypes.Structure):
    _fields_ = [("Left", wt.SHORT), ("Top", wt.SHORT),
                ("Right", wt.SHORT), ("Bottom", wt.SHORT)]


def run(directory: Path):
    report_stream = sys.stdout
    console_in = open("CONIN$", "r", encoding="utf-8")
    console_out = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    sys.stdin, sys.stdout = console_in, console_out
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetStdHandle.argtypes = [wt.DWORD, wt.HANDLE]
    kernel.GetConsoleMode.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
    kernel.WriteConsoleInputW.argtypes = [wt.HANDLE, ctypes.POINTER(InputRecord), wt.DWORD, ctypes.POINTER(wt.DWORD)]
    kernel.SetConsoleWindowInfo.argtypes = [wt.HANDLE, wt.BOOL, ctypes.POINTER(Rect)]
    kernel.SetConsoleScreenBufferSize.argtypes = [wt.HANDLE, Coord]
    input_handle = msvcrt.get_osfhandle(console_in.fileno())
    output_handle = msvcrt.get_osfhandle(console_out.fileno())
    kernel.SetStdHandle(wt.DWORD(-10), input_handle)
    kernel.SetStdHandle(wt.DWORD(-11), output_handle)
    before = wt.DWORD()
    assert kernel.GetConsoleMode(output_handle, ctypes.byref(before))
    assert sys.stdin.isatty() and sys.stdout.isatty()

    def resize(width, height):
        # Reopen CONOUT$: the original handle refers to the inactive main
        # buffer while VT is displaying the alternate buffer.
        with open("CONOUT$", "w") as active:
            active_handle = msvcrt.get_osfhandle(active.fileno())
            small = Rect(0, 0, 29, 9)
            assert kernel.SetConsoleWindowInfo(active_handle, True, ctypes.byref(small)), ctypes.get_last_error()
            assert kernel.SetConsoleScreenBufferSize(active_handle, Coord(width, height)), ctypes.get_last_error()
            rectangle = Rect(0, 0, width - 1, height - 1)
            assert kernel.SetConsoleWindowInfo(active_handle, True, ctypes.byref(rectangle)), ctypes.get_last_error()

    def send(key):
        event = InputRecord()
        event.EventType = 1
        record = event.Event.KeyEvent
        record.bKeyDown, record.wRepeatCount = True, 1
        if key in ("left", "up"):
            record.wVirtualKeyCode = {"left": 0x25, "up": 0x26}[key]
            record.wVirtualScanCode = {"left": 0x4B, "up": 0x48}[key]
            record.dwControlKeyState = 0x100  # ENHANCED_KEY
        else:
            record.uChar.UnicodeChar = key
        count = wt.DWORD()
        assert kernel.WriteConsoleInputW(input_handle, ctypes.byref(event), 1, ctypes.byref(count))
        assert count.value == 1

    resize(100, 40)
    actions = iter(("1", "2", "left", "up", "3", "]", "]", "+", " ",
                    None, None, " ", "e", "h", "h", "resize", "r", "g", "q"))
    frames = []
    sizes = []

    class DrivenTerminal(Terminal):
        def draw(self, rows):
            super().draw(rows)
            frames.append(rows)
            sizes.append((len(rows[0]), len(rows)))
            action = next(actions, "q")
            if action == "resize":
                # Conhost rejects SetConsoleScreenBufferSize on its VT alternate
                # buffer (ERROR_INVALID_PARAMETER). Recreate that buffer around
                # this fixture resize. Live window dragging is a manual check;
                # live resize events are covered separately by FakeTerminal.
                self.__exit__(None, None, None)
                resize(40, 12)
                self.__enter__()
                send("r")
            elif action is not None:
                send(action)

    state = Explorer()
    original = state.tree
    result = run_loop(state, DrivenTerminal(), directory, fps=12, duration=8)
    assert result == 0 and state.seed == 43 and state.tree is not original
    assert state.mode == "4d"
    assert (100, 40) in sizes and (40, 12) in sizes, sorted(set(sizes))
    assert any("2D" in rows[0] for rows in frames)
    assert any("4D DATA -> 3D -> SCREEN" in "\n".join(rows) for rows in frames)
    assert any("HELP" in rows[0] for rows in frames)
    assert list(directory.glob("*.txt"))
    after = wt.DWORD()
    assert kernel.GetConsoleMode(output_handle, ctypes.byref(after))
    assert before.value == after.value

    # Exercise the actual CLI and actual Windows Ctrl+C event in this console.
    import threading
    import time
    import signal

    # Background test launchers may inherit the process-level Ctrl+C ignore
    # flag. This isolated console must behave like an ordinary user console.
    kernel.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, wt.BOOL]
    assert kernel.SetConsoleCtrlHandler(None, False)
    signal.signal(signal.SIGINT, signal.default_int_handler)

    def interrupt():
        time.sleep(0.25)
        assert kernel.GenerateConsoleCtrlEvent(0, 0)

    worker = threading.Thread(target=interrupt, daemon=True)
    worker.start()
    ctrl_c_code = main(["view", "--duration", "3"])
    worker.join(timeout=2)
    assert ctrl_c_code == 130, ctrl_c_code
    assert kernel.GetConsoleMode(output_handle, ctypes.byref(after))
    assert before.value == after.value
    report_stream.write(json.dumps({"native_console": True, "frames": len(frames),
                                    "sizes": sorted(set(sizes)), "seed_after_g": state.seed,
                                    "ctrl_c_code": ctrl_c_code, "console_mode_restored": True}) + "\n")
    report_stream.flush()


if __name__ == "__main__":
    run(Path(sys.argv[1]))
