#!/usr/bin/env python3
"""Project-local runtime; existing offline installer remains available unchanged."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'runtime'))
from codex_flow.cli import main
if __name__ == '__main__':
    raise SystemExit(main())
