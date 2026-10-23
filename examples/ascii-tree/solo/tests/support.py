from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = ROOT / ".tmp" / "tests"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)
