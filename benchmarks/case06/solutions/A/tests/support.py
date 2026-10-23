"""Finite terminal driver: the production loop runs without a desktop/TTY."""


class FakeTerminal:
    def __init__(self, events=(), sizes=((99, 39),), interrupt=False, draw_error=False):
        self.events = iter(events)
        self.sizes = iter(sizes)
        self.current_size = None
        self.frames = []
        self.frame_sizes = []
        self.entered = False
        self.closed = False
        self.interrupt = interrupt
        self.draw_error = draw_error
        self.reads = 0

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *args):
        self.closed = True

    def size(self):
        self.current_size = next(self.sizes, self.current_size)
        return self.current_size

    def draw(self, frame):
        if self.draw_error:
            raise OSError("simulated output failure")
        self.frames.append(frame)
        self.frame_sizes.append(self.current_size)

    def read_keys(self, timeout):
        self.reads += 1
        if self.interrupt:
            raise KeyboardInterrupt
        # A hard stop guards tests against a broken loop.
        if self.reads > 100:
            raise AssertionError("event loop did not terminate")
        return next(self.events, ["q"])


class FakeClock:
    def __init__(self, step=0.10):
        self.value = 0.0
        self.step = step

    def __call__(self):
        self.value += self.step
        return self.value
