from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = ROOT / ".tmp"
TEMP_ROOT.mkdir(exist_ok=True)


def temporary_directory():
    return tempfile.TemporaryDirectory(dir=TEMP_ROOT)
