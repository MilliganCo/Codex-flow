"""Generate or verify the checked-in deterministic ASCII gallery."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.model import generate_tree
from ascii_tree.render import RenderOptions, render_tree

PRESETS = (
    ("seed42-2d.txt", 42, RenderOptions(mode="2d")),
    ("seed42-3d.txt", 42, RenderOptions(mode="3d")),
    ("seed42-4d-xw000.txt", 42, RenderOptions(mode="4d", angle4d=0)),
    ("seed42-4d-xw035.txt", 42, RenderOptions(mode="4d", angle4d=35)),
    ("seed7-3d.txt", 7, RenderOptions(mode="3d")),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare without changing files")
    args = parser.parse_args()
    directory = ROOT / "samples"
    if not args.check:
        directory.mkdir(exist_ok=True)
    manifest = []
    for filename, seed, options in PRESETS:
        tree = generate_tree(seed)
        raw = render_tree(tree, options).encode("ascii")
        path = directory / filename
        if args.check:
            if not path.exists() or path.read_bytes() != raw:
                print(f"FAIL: stale or missing {path}")
                return 1
        else:
            path.write_bytes(raw)
        manifest.append({"file": filename, "seed": seed, "options": asdict(options),
                         "segments": len(tree.segments), "leaves": len(tree.leaves),
                         "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    raw_manifest = (json.dumps(manifest, indent=2) + "\n").encode("ascii")
    path = directory / "manifest.json"
    if args.check:
        if not path.exists() or path.read_bytes() != raw_manifest:
            print("FAIL: stale or missing sample manifest")
            return 1
    else:
        path.write_bytes(raw_manifest)
    print(f"PASS: {len(PRESETS)} exact ASCII samples {'verified' if args.check else 'generated'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
