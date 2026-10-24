"""One-command finite smoke test. Uses only this project's local tests."""

from pathlib import Path
import sys
import unittest


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    tests = root / "tests"
    if not tests.is_dir():
        print("Run this smoke test from the source distribution (tests/ is required).", file=sys.stderr)
        return 2
    suite = unittest.defaultTestLoader.discover(str(tests), top_level_dir=str(root))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
