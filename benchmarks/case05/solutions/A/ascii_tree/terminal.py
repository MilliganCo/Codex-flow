"""Small VT terminal adapter: Windows console input or POSIX cbreak input."""

import os
import shutil
import sys
import time


class Terminal:
    def __init__(self, input_stream=None, output_stream=None):
        self.input = input_stream if input_stream is not None else sys.stdin
        self.output = output_stream if output_stream is not None else sys.stdout
        self._restore = None
        self._entered = False
        self._pending = ''
        self._pending_since = 0.0
        self._windows_input = None

    def __enter__(self):
        if not (self.input.isatty() and self.output.isatty()):
            raise OSError('Interactive view requires a TTY; use render instead')
        try:
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                import msvcrt

                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.GetConsoleMode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
                kernel.SetConsoleMode.argtypes = (wintypes.HANDLE, wintypes.DWORD)
                output_handle = msvcrt.get_osfhandle(self.output.fileno())
                saved_mode = wintypes.DWORD()
                if not kernel.GetConsoleMode(output_handle, ctypes.byref(saved_mode)):
                    raise OSError('Cannot read Windows console mode')
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING, with original bits retained.
                if not kernel.SetConsoleMode(output_handle, saved_mode.value | 0x0004):
                    raise OSError('Terminal does not support VT output')
                self._restore = lambda: kernel.SetConsoleMode(output_handle, saved_mode.value)
                from .winconsole import WindowsInput
                self._windows_input = WindowsInput(self.input)
            else:
                import termios
                import tty

                descriptor = self.input.fileno()
                original = termios.tcgetattr(descriptor)
                self._restore = lambda: termios.tcsetattr(descriptor, termios.TCSADRAIN, original)
                tty.setcbreak(descriptor)
            self._entered = True
            self.output.write('\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H')
            self.output.flush()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, exc_type, exc, traceback):
        try:
            if self._entered:
                self.output.write('\x1b[0m\x1b[?25h\x1b[?1049l')
                self.output.flush()
        finally:
            try:
                if self._windows_input is not None:
                    self._windows_input.restore()
            finally:
                if self._restore is not None:
                    self._restore()
                self._windows_input = None
                self._restore = None
                self._entered = False

    def size(self):
        try:
            size = os.get_terminal_size(self.output.fileno())
        except (OSError, ValueError):
            size = shutil.get_terminal_size((100, 40))
        return size.columns, size.lines

    def draw(self, frame):
        # Explicit cursor positioning avoids newline translation and frame spam.
        chunks = ['\x1b[H']
        for row, line in enumerate(frame.lines, 1):
            chunks.extend((f'\x1b[{row};1H', line, '\x1b[K'))
        chunks.append('\x1b[J')
        self.output.write(''.join(chunks))
        self.output.flush()

    @staticmethod
    def _key(char):
        return {' ': 'space', '\r': 'enter', '\n': 'enter', '\x1b': 'escape'}.get(char, char)

    def read_keys(self, timeout):
        if os.name == 'nt':
            return self._windows_input.read_keys(timeout)
        import select

        ready, _, _ = select.select([self.input], [], [], timeout)
        if ready:
            data = os.read(self.input.fileno(), 256)
            if not data:
                return ['q']
            self._pending += data.decode('ascii', errors='ignore')
            self._pending_since = time.monotonic()
        return self._parse_pending(time.monotonic())

    def _parse_pending(self, now):
        result = []
        arrows = {'\x1b[A': 'up', '\x1b[B': 'down', '\x1b[C': 'right', '\x1b[D': 'left',
                  '\x1bOA': 'up', '\x1bOB': 'down', '\x1bOC': 'right', '\x1bOD': 'left'}
        while self._pending:
            if self._pending.startswith('\x1b'):
                match = next((sequence for sequence in arrows if self._pending.startswith(sequence)), None)
                if match:
                    result.append(arrows[match])
                    self._pending = self._pending[len(match):]
                    continue
                if any(sequence.startswith(self._pending) for sequence in arrows) and now - self._pending_since < 0.04:
                    break
            result.append(self._key(self._pending[0]))
            self._pending = self._pending[1:]
        return result

