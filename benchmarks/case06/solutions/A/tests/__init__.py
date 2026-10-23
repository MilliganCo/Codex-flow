"""All temporary test artifacts stay inside the checkout."""

from pathlib import Path

(Path(__file__).resolve().parents[1] / ".tmp").mkdir(exist_ok=True)
