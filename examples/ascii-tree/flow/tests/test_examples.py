import hashlib
import json
from pathlib import Path
import unittest

from ascii_tree.model import generate_tree
from ascii_tree.render import RenderOptions, render


class ExampleTests(unittest.TestCase):
    def test_saved_examples_match_parameters_hashes_and_current_renderer(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        manifest = json.loads((examples / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest), 6)
        modes, seeds, angles4d = set(), set(), set()
        for entry in manifest:
            with self.subTest(file=entry["file"]):
                data = (examples / entry["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
                options = RenderOptions(**entry["options"])
                self.assertEqual(data, render(generate_tree(entry["seed"]), options).encode("ascii"))
                self.assertEqual(len(data.splitlines()), 40)
                self.assertTrue(all(len(line) == 100 for line in data.splitlines()))
                self.assertTrue(data.isascii())
                self.assertNotIn(b"\x1b", data)
                modes.add(options.mode)
                seeds.add(entry["seed"])
                if options.mode == "4d":
                    angles4d.add(options.angle4d)
        self.assertEqual(modes, {"2d", "3d", "4d"})
        self.assertEqual(seeds, {7, 42})
        self.assertEqual(angles4d, {0, 65})
