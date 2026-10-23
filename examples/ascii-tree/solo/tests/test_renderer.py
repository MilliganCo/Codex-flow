from dataclasses import replace
import unittest

from ascii_tree.geometry import Vec4, camera_rotate, perspective, project4, rotation4, transform4
from ascii_tree.model import Segment, Tree, generate_tree
from ascii_tree.renderer import DepthBuffer, Projector, RenderOptions, ScreenPoint, raster_segment, render_tree


class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_deterministic_ascii_exact_dimensions(self):
        for mode in ("2d", "3d", "4d"):
            for width, height in ((80, 30), (100, 40)):
                with self.subTest(mode=mode, size=(width, height)):
                    options = RenderOptions(width, height, mode)
                    frame = render_tree(self.tree, options)
                    self.assertEqual(frame, render_tree(self.tree, options))
                    self.assertEqual(frame.height, height)
                    self.assertTrue(all(len(row) == width for row in frame.rows))
                    data = frame.text().encode("ascii")
                    self.assertEqual(len(data), (width + 1) * height)
                    self.assertNotIn(b"\x1b", data)
                    self.assertTrue(all(32 <= c <= 126 or c == 10 for c in data))
                    self.assertGreater(sum(c != " " for row in frame.rows for c in row), 100)

    def test_camera_rotation_is_geometric(self):
        original = RenderOptions()
        a = render_tree(self.tree, original)
        for options in (replace(original, yaw=70), replace(original, pitch=35)):
            b = render_tree(self.tree, options)
            changes = sum(x != y for x, y in zip(a.text(), b.text()))
            self.assertGreater(changes, 200)

    def test_aspect_ratio_and_connected_tapered_skeleton(self):
        for aspect in (.4, .5, .8):
            projector = Projector(self.tree, RenderOptions(mode="2d", aspect=aspect))
            center = projector.project(Vec4(0, projector.center.y, 0, 0))
            diagonal = projector.project(Vec4(1, projector.center.y + 1, 0, 0))
            self.assertAlmostEqual((diagonal.x - center.x) / (center.y - diagonal.y), 1 / aspect)
        skeleton = Tree(self.tree.seed, self.tree.vertices, self.tree.segments, ())
        frame = render_tree(skeleton, RenderOptions(mode="2d"))
        pixels = {(x, y) for y, row in enumerate(frame.rows) for x, char in enumerate(row) if char != " "}
        pending = [next(iter(pixels))]
        visited = set(pending)
        while pending:
            x, y = pending.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbor = x + dx, y + dy
                    if neighbor in pixels and neighbor not in visited:
                        visited.add(neighbor)
                        pending.append(neighbor)
        self.assertEqual(visited, pixels, "the projected woody silhouette must be connected")
        trunk = [segment for segment in self.tree.segments if segment.order == 0]
        self.assertGreater(trunk[0].radius_start, trunk[-1].radius_end * 10)

    def test_hyperrotation_changes_projection_for_each_plane(self):
        for plane in ("xw", "yw", "zw"):
            a = RenderOptions(mode="4d", plane=plane, angle4=0)
            b = replace(a, angle4=40)
            before, after = render_tree(self.tree, a), render_tree(self.tree, b)
            self.assertGreater(sum(x != y for x, y in zip(before.text(), after.text())), 150)

    def test_renderer_matches_explicit_4d_matrix_projection_pipeline(self):
        for plane in ("xw", "yw", "zw"):
            options = RenderOptions(mode="4d", plane=plane, angle4=37, yaw=24, pitch=12)
            projector = Projector(self.tree, options)
            for point in self.tree.vertices[::37]:
                centered = point.xyz - projector.center
                rotated4 = transform4(Vec4(centered.x, centered.y, centered.z, point.w), rotation4(37, plane))
                spatial = project4(rotated4, projector.distance)
                explicit = perspective(camera_rotate(spatial, 24, 12), projector.distance)
                actual = projector.project(point)
                self.assertIsNotNone(actual)
                self.assertAlmostEqual(actual.x, 49.5 + explicit[0] * projector.scale / options.aspect)
                self.assertAlmostEqual(actual.y, 19.5 - explicit[1] * projector.scale)
                self.assertAlmostEqual(actual.depth, explicit[2])
            self.assertIsNone(projector.project(Vec4(0, projector.center.y, 0, 1e9)))

    def test_depth_buffer_nearer_wins_in_either_order(self):
        for samples in (((8, "N"), (14, "F")), ((14, "F"), (8, "N"))):
            buffer = DepthBuffer(3, 3)
            for depth, char in samples:
                buffer.put(1, 1, depth, char)
            self.assertEqual(buffer.frame().rows[1], " N ")
            self.assertEqual(buffer.depth[1][1], 8)
            self.assertFalse(buffer.put(-1, 8, 0, "x"))

    def test_crossing_segments_occlude_independent_of_submission(self):
        lines = ((ScreenPoint(2, 5, 8, 1), ScreenPoint(18, 5, 8, 1)),
                 (ScreenPoint(10, 1, 14, 1), ScreenPoint(10, 9, 14, 1)))
        frames = []
        for order in ((0, 1), (1, 0)):
            buffer = DepthBuffer(21, 11)
            for i in order:
                raster_segment(buffer, *lines[i], .01, .01, 1, .5, 2)
            frames.append(buffer.frame())
            self.assertEqual(buffer.frame().rows[5][10], "-")
            self.assertLess(buffer.depth[5][10], 9)
        self.assertEqual(*frames)

    def test_real_tree_near_branch_hides_far_branch(self):
        # Exact overlap in orthographic 2D also consumes real Z occlusion.
        vertices = (Vec4(-2, 1, 0, 0), Vec4(2, 1, 0, 1),
                    Vec4(0, 0, 4, 0), Vec4(0, 2, 4, 1))
        near = Segment(0, 1, .02, .01, None, 2)
        far = Segment(2, 3, .02, .01, None, 2)
        a = render_tree(Tree(0, vertices, (near, far), ()), RenderOptions(31, 15, "2d"))
        b = render_tree(Tree(0, vertices, (far, near), ()), RenderOptions(31, 15, "2d"))
        self.assertEqual(a, b)
        self.assertIn("-", a.text())

    def test_small_extreme_and_time_frames(self):
        for size in ((1, 1), (2, 3), (8, 4), (20, 8)):
            for mode in ("2d", "3d", "4d"):
                frame = render_tree(self.tree, RenderOptions(*size, mode, angle4=90, zoom=5))
                self.assertEqual((frame.width, frame.height), size)
        for angle in (-180, -90, 90, 180, 1e9):
            frame = render_tree(self.tree, RenderOptions(mode="4d", angle4=angle))
            self.assertTrue(frame.text().isascii())
        base = RenderOptions(time=2.5)
        self.assertEqual(render_tree(self.tree, base), render_tree(self.tree, base))
        self.assertNotEqual(render_tree(self.tree, base), render_tree(self.tree, replace(base, time=0)))

    def test_invalid_options_rejected(self):
        for kwargs in ({"width": 0}, {"height": -1}, {"width": 1001}, {"width": 1000, "height": 1000},
                       {"yaw": float("nan")}, {"time": float("inf")}, {"zoom": 0},
                       {"mode": "5d"}, {"plane": "xy"}, {"aspect": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                RenderOptions(**kwargs)


if __name__ == "__main__":
    unittest.main()
