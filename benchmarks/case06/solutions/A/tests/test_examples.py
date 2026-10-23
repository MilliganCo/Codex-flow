import hashlib
import json
from pathlib import Path
import unittest

from ascii_tree.model import generate_tree
from ascii_tree.render import RenderOptions, render_tree


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class ExampleTests(unittest.TestCase):
    def test_saved_frames_match_manifest_and_current_renderer(self):
        manifest = json.loads((EXAMPLES / "manifest.json").read_text(encoding="ascii"))
        self.assertEqual(len(manifest), 6)
        trees = {seed: generate_tree(seed) for seed in (42, 7)}
        for case in manifest:
            with self.subTest(file=case["file"]):
                data = (EXAMPLES / case["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), case["sha256"])
                self.assertEqual(len(data), case["bytes"])
                self.assertTrue(all(c == 10 or 32 <= c <= 126 for c in data))
                self.assertEqual(data, render_tree(trees[case["seed"]], RenderOptions(**case["options"])).encode("ascii"))

    def test_saved_4d_rotation_and_second_seed_are_visibly_different(self):
        a = (EXAMPLES / "seed42_4d_xw_000.txt").read_bytes()
        b = (EXAMPLES / "seed42_4d_xw_048.txt").read_bytes()
        self.assertGreater(sum(x != y for x, y in zip(a, b)), 500)
        self.assertNotEqual((EXAMPLES / "seed42_3d.txt").read_bytes(), (EXAMPLES / "seed7_3d.txt").read_bytes())
