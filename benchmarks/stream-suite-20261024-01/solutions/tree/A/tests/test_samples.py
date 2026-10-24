import hashlib
import json
from pathlib import Path
import unittest

from ascii_tree.model import generate_tree
from ascii_tree.render import RenderSettings, render

ROOT = Path(__file__).resolve().parents[1]


class SampleTests(unittest.TestCase):
    def test_saved_examples_match_parameters_and_hashes(self):
        manifest = json.loads((ROOT / "samples" / "manifest.json").read_text(encoding="ascii"))
        self.assertEqual(len(manifest), 8)
        for entry in manifest:
            with self.subTest(file=entry["file"]):
                data = (ROOT / "samples" / entry["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
                settings = RenderSettings(**{k: v for k, v in entry.items()
                                             if k not in ("file", "seed", "sha256")})
                self.assertEqual(data, render(generate_tree(entry["seed"]), settings).encode("ascii"))
