import hashlib
import json
import unittest

from ascii_tree.model import generate_tree
from ascii_tree.renderer import RenderOptions, render_tree
from tests.support import ROOT


class ExampleTests(unittest.TestCase):
    def test_shipped_frames_match_documented_inputs(self):
        examples = ROOT / "examples"
        manifest = json.loads((examples / "manifest.json").read_text(encoding="ascii"))
        trees = {item["seed"]: generate_tree(item["seed"]) for item in manifest}
        for item in manifest:
            with self.subTest(file=item["file"]):
                data = (examples / item["file"]).read_bytes()
                expected = render_tree(trees[item["seed"]], RenderOptions(**item["options"])).text().encode("ascii")
                self.assertEqual(data, expected)
                self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])
                self.assertEqual(trees[item["seed"]].fingerprint, item["tree_fingerprint"])
        self.assertEqual({item["options"]["mode"] for item in manifest if item["seed"] == 42}, {"2d", "3d", "4d"})
        before = (examples / "seed42_4d_xw_000.txt").read_bytes()
        after = (examples / "seed42_4d_xw_040.txt").read_bytes()
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
