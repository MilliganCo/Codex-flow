"""Finite verification and machine-readable evidence: python tools/verify.py."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ascii_tree.model import generate_tree
from ascii_tree.render import Camera, render


def main():
    report = {"python": sys.version, "platform": platform.platform(), "checks": []}
    for name, arguments in (("unittest", ["-m", "unittest", "discover", "-s", "tests", "-v"]),
                            ("smoke", ["tools/smoke.py"])):
        start = time.perf_counter()
        result = subprocess.run([sys.executable, *arguments], cwd=ROOT,
                                capture_output=True, text=True, timeout=90)
        report["checks"].append({"name": name, "return_code": result.returncode,
                                  "seconds": round(time.perf_counter() - start, 3),
                                  "stdout": result.stdout, "stderr": result.stderr})
        print(f"{'PASS' if result.returncode == 0 else 'FAIL'}: {name}")
    artifacts = []
    for entry in json.loads((ROOT / "samples" / "manifest.json").read_text()):
        data = (ROOT / "samples" / entry["file"]).read_bytes()
        camera = Camera(mode=entry["mode"], angle4d=entry["angle4d"])
        regenerated = render(generate_tree(entry["seed"]), 100, 40, camera).encode("ascii")
        passed = (hashlib.sha256(data).hexdigest() == entry["sha256"] and data == regenerated
                  and len(data.splitlines()) == 40 and all(len(row) == 100 for row in data.splitlines())
                  and all(32 <= b <= 126 or b == 10 for b in data))
        artifacts.append({"file": entry["file"], "passed": passed})
    report["artifacts"] = artifacts
    print(f"{'PASS' if all(a['passed'] for a in artifacts) else 'FAIL'}: saved frame reproducibility")
    tree = generate_tree(42)
    timings = {}
    for mode in ("2d", "3d", "4d"):
        samples = []
        for index in range(10):
            start = time.perf_counter()
            render(tree, 100, 40, Camera(mode=mode, time=index / 10))
            samples.append((time.perf_counter() - start) * 1000)
        timings[mode] = {"median_ms": round(statistics.median(samples), 2),
                         "max_ms": round(max(samples), 2), "frames": 10}
    report["render_100x40_benchmark"] = timings
    passed = all(c["return_code"] == 0 for c in report["checks"]) and all(a["passed"] for a in artifacts)
    report["passed"] = passed
    folder = ROOT / "verification"
    folder.mkdir(exist_ok=True)
    (folder / "automated.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(timings))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
