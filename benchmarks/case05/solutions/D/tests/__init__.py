"""Run all tests with python -m unittest discover -v."""

from pathlib import Path

(Path(__file__).resolve().parent.parent / ".tmp").mkdir(exist_ok=True)
