"""Win32 key events: no line buffering and no lost Ctrl+C in _getwch()."""

import time


def decode_key(down, char, virtual_key, repeat=1):
    if not down:
        return []
    named = {0x25: 'left', 0x26: 'up', 0x27: 'right', 0x28: 'down',
             0x1B: 'escape', 0x0D: 'enter'}
    key = named.get(virtual_key, {' ': 'space'}.get(char, char))
    return [key] * min(32, max(1, repeat)) if key and key != '\x00' else []


class WindowsInput:
    def __init__(self, stream):
        import ctypes
        from ctypes import wintypes
        import msvcrt

        class Character(ctypes.Union):
            _fields_ = [('UnicodeChar', wintypes.WCHAR), ('AsciiChar', ctypes.c_char)]

        class KeyEvent(ctypes.Structure):
            _fields_ = [('bKeyDown', wintypes.BOOL), ('wRepeatCount', wintypes.WORD),
                        ('wVirtualKeyCode', wintypes.WORD), ('wVirtualScanCode', wintypes.WORD),
                        ('uChar', Character), ('dwControlKeyState', wintypes.DWORD)]

        class Event(ctypes.Union):
            _fields_ = [('KeyEvent', KeyEvent), ('padding', ctypes.c_byte * 16)]

        class InputRecord(ctypes.Structure):
            _fields_ = [('EventType', wintypes.WORD), ('Event', Event)]

        self.ctypes = ctypes
        self.DWORD = wintypes.DWORD
        self.Record = InputRecord
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.GetConsoleMode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        self.kernel.SetConsoleMode.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        self.kernel.GetNumberOfConsoleInputEvents.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        self.kernel.ReadConsoleInputW.argtypes = (wintypes.HANDLE, ctypes.POINTER(InputRecord),
                                                  wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
        self.handle = msvcrt.get_osfhandle(stream.fileno())
        original = wintypes.DWORD()
        if not self.kernel.GetConsoleMode(self.handle, ctypes.byref(original)):
            raise OSError('Cannot read Windows console input mode')
        self.original_mode = original.value
        # Extended flags + resize events, without quick-edit, cooked input,
        # echo, VT-input translation or processed Ctrl+C. Raw Ctrl+C arrives
        # as a key event and unwinds the same cleanup path as SIGINT.
        mode = (original.value | 0x0080 | 0x0008) & ~(0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0040 | 0x0200)
        if not self.kernel.SetConsoleMode(self.handle, mode):
            raise OSError('Cannot enable Windows console key events')

    def restore(self):
        self.kernel.SetConsoleMode(self.handle, self.original_mode)

    def read_keys(self, timeout):
        deadline = time.monotonic() + timeout
        available = self.DWORD()
        while True:
            if not self.kernel.GetNumberOfConsoleInputEvents(self.handle, self.ctypes.byref(available)):
                raise OSError('Cannot poll Windows console input')
            if available.value or time.monotonic() >= deadline:
                break
            time.sleep(0.005)
        if not available.value:
            return []
        records = (self.Record * min(128, available.value))()
        count = self.DWORD()
        if not self.kernel.ReadConsoleInputW(self.handle, records, len(records), self.ctypes.byref(count)):
            raise OSError('Cannot read Windows console input')
        result = []
        for record in records[:count.value]:
            if record.EventType == 0x0001:
                key = record.Event.KeyEvent
                result.extend(decode_key(key.bKeyDown, key.uChar.UnicodeChar,
                                         key.wVirtualKeyCode, key.wRepeatCount))
        return result
