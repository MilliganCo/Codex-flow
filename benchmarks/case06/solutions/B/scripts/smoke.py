"""One finite command, no downloads: run the acceptance regression suite."""

from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=root)
if result.returncode:
    raise SystemExit(result.returncode)
result = subprocess.run([sys.executable, "scripts/generate_samples.py", "--check"], cwd=root)
raise SystemExit(result.returncode)
