from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TEMP = ROOT / '.tmp'


def temporary_directory():
    TEMP.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(dir=TEMP)
