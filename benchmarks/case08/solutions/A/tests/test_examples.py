import hashlib
import json
from pathlib import Path
import unittest

from ascii_tree.geometry import generate_tree
from ascii_tree.render import RenderOptions, frame_bytes

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class ExampleTests(unittest.TestCase):
    def test_shipped_frames_match_current_renderer_and_manifest(self):
        manifest = json.loads((EXAMPLES / "manifest.json").read_text(encoding="ascii"))
        self.assertEqual({entry["seed"] for entry in manifest}, {7, 42})
        self.assertEqual({entry["options"]["mode"] for entry in manifest}, {"2d", "3d", "4d"})
        for entry in manifest:
            with self.subTest(file=entry["file"]):
                data = (EXAMPLES / entry["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
                tree = generate_tree(entry["seed"])
                self.assertEqual(data, frame_bytes(tree, RenderOptions(**entry["options"])))
                self.assertEqual(len(tree.nodes), entry["nodes"])

    def test_shipped_4d_before_after_are_different(self):
        self.assertNotEqual((EXAMPLES / "seed42-4d-xw0.txt").read_bytes(),
                            (EXAMPLES / "seed42-4d-xw55.txt").read_bytes())
