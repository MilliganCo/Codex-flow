"""Interactive controller, deliberately independent of terminal I/O for testing."""

from dataclasses import dataclass, replace
from pathlib import Path
import time

from .geometry import View
from .model import generate_tree
from .render import Frame, render


HELP = (
    'ASCII TREE EXPLORER / HELP',
    '',
    '1 / 2 / 3   : 2D / 3D / 4D (same tree)',
    'Arrow keys  : orbit / tilt in 3D and 4D',
    '[ / ]       : XW rotation -/+ 10 deg in 4D',
    '+ / -       : zoom in / out (also =)',
    'Space       : start / pause wind and orbit',
    'G           : grow a new seed',
    'R           : reset orientation, zoom, time',
    'E           : export the tree viewport as ASCII .txt',
    'H / ?       : toggle help',
    'Q / Esc     : quit (Ctrl+C also restores terminal)',
    '',
    '4D: W records growth distance along each branch.',
    'XW rotation mixes X and W, then projects 4D -> 3D',
    '-> 2D. You see a projection of four-dimensional data.',
    '',
    '2D fixes the camera to XY; zoom and wind still work.',
    'Resize freely. A larger window reveals more detail.',
)


def wrapped_lines(lines, width):
    """Wrap at spaces where possible, including in narrow terminals."""
    result = []
    for line in lines:
        if not line:
            result.append('')
        while line:
            cut = min(len(line), width)
            if cut < len(line):
                space = line.rfind(' ', 0, cut + 1)
                if space > width // 3:
                    cut = space
            result.append(line[:cut])
            line = line[cut:].lstrip()
    return result


@dataclass(slots=True)
class Explorer:
    seed: int = 42
    view: View = View()
    export_dir: Path = Path('exports')

    def __post_init__(self):
        self.tree = generate_tree(self.seed)
        self.running = True
        self.animating = False
        self.help_open = False
        self.help_page = 0
        self.notice = 'H: help | E: export | Space: animate | Q: quit'
        self.export_count = 0
        self.viewport = (100, 35)
        self.last_frame = None

    # Fields below are part of slots, initialized in __post_init__.
    tree: object = None
    running: bool = True
    animating: bool = False
    help_open: bool = False
    help_page: int = 0
    notice: str = ''
    export_count: int = 0
    viewport: tuple[int, int] = (100, 35)
    last_frame: Frame | None = None

    def handle(self, key: str):
        key = key.lower()
        if key == '\x03':
            raise KeyboardInterrupt
        if key in ('q', 'escape'):
            self.running = False
        elif key in ('h', '?'):
            self.help_open = not self.help_open
            self.help_page = 0
        elif self.help_open and key in ('down', 'right', 'enter'):
            self.help_page += 1
        elif self.help_open and key in ('up', 'left'):
            self.help_page = max(0, self.help_page - 1)
        elif key in ('1', '2', '3'):
            self.view = replace(self.view, mode={'1': '2d', '2': '3d', '3': '4d'}[key])
            self.notice = 'Same geometry; 4D -> 3D -> 2D projection' if key == '3' else 'Same geometry; camera changed'
        elif key in ('left', 'right') and self.view.mode != '2d':
            self.view = replace(self.view, yaw=(self.view.yaw + (10 if key == 'right' else -10)) % 360)
        elif key in ('up', 'down') and self.view.mode != '2d':
            self.view = replace(self.view, pitch=max(-80, min(80, self.view.pitch + (5 if key == 'up' else -5))))
        elif key in ('[', ']') and self.view.mode == '4d':
            self.view = replace(self.view, angle4=(self.view.angle4 + (10 if key == ']' else -10)) % 360)
        elif key in ('+', '=', '-'):
            self.view = replace(self.view, zoom=max(0.1, min(8, self.view.zoom * (1 / 1.15 if key == '-' else 1.15))))
        elif key == 'space':
            self.animating = not self.animating
        elif key == 'r':
            self.view = View(mode=self.view.mode)
            self.notice = 'Orientation, zoom and animation time reset'
        elif key == 'g':
            self.seed = (self.seed + 0x9E3779B9) % (2 ** 32)
            self.tree = generate_tree(self.seed)
            self.notice = 'New procedural tree; seed = ' + str(self.seed)
        elif key == 'e':
            self.export_current()

    def advance(self, seconds: float):
        if self.animating and not self.help_open:
            self.view = replace(self.view, time=self.view.time + max(0, min(seconds, 0.25)))

    def export_current(self):
        # Exclusive creation never overwrites another session's export.
        try:
            self.export_dir.mkdir(parents=True, exist_ok=True)
            frame = render(self.tree, self.view, *self.viewport)
            while True:
                self.export_count += 1
                target = self.export_dir / f'tree-{self.seed}-{self.view.mode}-{self.export_count:03d}.txt'
                try:
                    with target.open('xb') as stream:
                        stream.write(frame.text().encode('ascii'))
                    break
                except FileExistsError:
                    continue
            self.notice = 'Saved: ' + str(target)
        except OSError as error:
            self.notice = 'Export failed: ' + (error.strerror or type(error).__name__)

    def screen(self, width: int, height: int) -> Frame:
        width, height = max(1, min(500, width)), max(1, min(200, height))
        # Reserve a margin row: writing the physical bottom-right cell can
        # scroll Windows Terminal and many VT emulators.
        rows = max(1, height - 1)
        chrome = 5 if rows >= 12 else 2 if rows >= 5 else 0
        self.viewport = (width, max(1, rows - chrome))
        self.last_frame = render(self.tree, self.view, *self.viewport)
        if self.help_open:
            body = wrapped_lines(HELP, width)
            capacity = max(1, rows - 2)
            pages = max(1, (len(body) + capacity - 1) // capacity)
            self.help_page %= pages
            start = self.help_page * capacity
            lines = body[start:start + capacity]
            lines += [f'Help {self.help_page + 1}/{pages}: arrows/Enter next; H close']
        elif chrome:
            effective_yaw = self.view.yaw + (self.view.time * 12 if self.view.mode != '2d' else 0)
            effective_xw = self.view.angle4 + (self.view.time * 16 if self.view.mode == '4d' else 0)
            lines = [f'ASCII TREE EXPLORER | {self.view.mode.upper()} | seed {self.seed} | ' + ('PLAY' if self.animating else 'PAUSED')]
            if chrome == 5:
                lines += [f'yaw {effective_yaw % 360:5.1f}  tilt {self.view.pitch:5.1f}  XW {effective_xw % 360:5.1f}  zoom {self.view.zoom:.2f}  t {self.view.time:.1f}',
                          '4D: projection of (X,Y,Z,W) via XW rotation -> 3D -> 2D' if self.view.mode == '4d' else 'One procedural tree | branches, taper, foliage | depth-tested ASCII']
            lines += list(self.last_frame.lines)
            if chrome == 5:
                lines += ['1/2/3:mode Arrows:orbit []:XW +/-:zoom Space:play G:new R:reset E:save H:? Q:quit']
            # OS error strings / user paths may be Unicode; UI stays ASCII.
            lines += [self.notice.encode('ascii', 'replace').decode('ascii')]
        else:
            lines = list(self.last_frame.lines)
        lines = lines[:rows]
        lines += [''] * (rows - len(lines))
        return Frame(tuple(line[:width].ljust(width) for line in lines))

    def run(self, terminal, clock=time.monotonic):
        """At most 10 FPS; paused views redraw only for input or resize."""
        dirty, previous_size = True, None
        previous_time = clock()
        next_frame = previous_time
        with terminal:
            while self.running:
                now = clock()
                self.advance(now - previous_time)
                previous_time = now
                size = terminal.size()
                if dirty or size != previous_size or (self.animating and now >= next_frame):
                    terminal.draw(self.screen(*size))
                    previous_size = size
                    next_frame = now + 0.1
                    dirty = False
                for key in terminal.read_keys(0.03):
                    self.handle(key)
                    dirty = True

