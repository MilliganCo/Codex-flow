from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def temporary_directory():
    base = ROOT / ".tmp"
    base.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="tree-test-", dir=base)


class FakeTerminal:
    def __init__(self, keys=("q",), sizes=((100, 40),)):
        self.keys = iter(keys)
        self.sizes = iter(sizes)
        self.current_size = (100, 40)
        self.draws = []
        self.entered = False
        self.closed = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *args):
        self.closed = True

    def size(self):
        self.current_size = next(self.sizes, self.current_size)
        return self.current_size

    def draw(self, rows):
        self.draws.append(rows)

    def read_key(self, timeout):
        key = next(self.keys, "q")
        if isinstance(key, BaseException):
            raise key
        return key
