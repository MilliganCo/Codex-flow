from dataclasses import replace
import math
import unittest

from ascii_tree.geometry import perspective, project_4d, rotate_3d, rotate_xw, xw_matrix
from ascii_tree.model import Leaf, Segment, Tree, generate_tree
from ascii_tree.render import Camera, Raster, render


class GeometryTests(unittest.TestCase):
    def test_xw_matrix_mixes_and_preserves_norm(self):
        point = (1., 2., 3., 4.)
        matrix = xw_matrix(math.pi / 3)
        result = rotate_xw(point, math.pi / 3)
        self.assertAlmostEqual(sum(v*v for v in point), sum(v*v for v in result))
        self.assertNotEqual(result[0], point[0])
        self.assertNotEqual(result[3], point[3])
        self.assertGreater(abs(matrix[0][3]), .5)
        for i in range(4):
            for j in range(4):
                self.assertAlmostEqual(sum(matrix[k][i] * matrix[k][j] for k in range(4)),
                                       1 if i == j else 0)
        for i, value in enumerate(result):
            self.assertAlmostEqual(value, sum(matrix[i][j] * point[j] for j in range(4)))
        inverse = rotate_xw(result, -math.pi / 3)
        for a, b in zip(point, inverse):
            self.assertAlmostEqual(a, b)

    def test_perspective_near_plane_clips(self):
        for w in (4., 4. - 1e-12, 4. + 1e-12, 10.):
            self.assertIsNone(project_4d((1, 2, 3, w)))
        for z in (3.6, 3.6 - 1e-12, 3.6 + 1e-12, 10.):
            self.assertIsNone(perspective((1, 2, z)))
        self.assertEqual(project_4d((1, 2, 3, 0)), (1, 2, 3))
        self.assertEqual(perspective((1, 2, 0)), (1, 2, 0, 1))
        for distance in (0, -1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                project_4d((0, 0, 0, 0), distance)
            with self.assertRaises(ValueError):
                perspective((0, 0, 0), distance)

    def test_nonfinite_and_malformed_coordinates_rejected(self):
        for value in (math.inf, -math.inf, math.nan):
            with self.assertRaises(ValueError):
                rotate_xw((value, 0, 0, 0), 0)
            with self.assertRaises(ValueError):
                project_4d((0, 0, 0, value))
            with self.assertRaises(ValueError):
                perspective((0, 0, value))
            with self.assertRaises(ValueError):
                rotate_3d((0, 0, 0), value, 0)
        for point in ((), (1, 2, 3)):
            with self.assertRaises(ValueError):
                rotate_xw(point, 0)
            with self.assertRaises(ValueError):
                project_4d(point)
        for point in ((), (1, 2), (1, 2, 3, 4)):
            with self.assertRaises(ValueError):
                perspective(point)
        self.assertIsNone(perspective((1e308, 1e308, 3.5)))


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_frame_sizes_ascii_deterministic_all_modes(self):
        for mode in ("2d", "3d", "4d"):
            for width, height in ((80, 30), (100, 40), (1, 1), (2, 3), (12, 4)):
                camera = Camera(mode=mode)
                frame = render(self.tree, width, height, camera)
                self.assertEqual(frame, render(self.tree, width, height, camera))
                self.assertEqual(len(frame.splitlines()), height)
                self.assertTrue(all(len(line) == width for line in frame.splitlines()))
                self.assertTrue(all(32 <= ord(c) <= 126 or c == "\n" for c in frame))
                self.assertNotIn("\x1b", frame)

    def test_3d_camera_changes_frame(self):
        frames = [render(self.tree, camera=Camera(yaw=yaw, pitch=pitch))
                  for yaw, pitch in ((0, 0), (70, 0), (0, 35))]
        self.assertEqual(len(set(frames)), 3)
        self.assertGreater(sum(a != b for a, b in zip(frames[0], frames[1])), 150)

    def test_4d_angle_changes_frame_and_keeps_tree(self):
        original = self.tree.segments
        frames = [render(self.tree, camera=Camera(mode="4d", angle4d=a)) for a in (0, 45, 90)]
        self.assertEqual(len(set(frames)), 3)
        self.assertGreater(sum(a != b for a, b in zip(frames[0], frames[1])), 200)
        self.assertIs(self.tree.segments, original)

    def test_occlusion_crossing_segments_order_independent(self):
        def draw(reverse):
            raster = Raster(21, 11)
            segments = [((2., 5., -.5), (18., 5., -.5), "-", 2),
                        ((10., 1., .5), (10., 9., .5), "|", 1)]
            for a, b, char, owner in (reversed(segments) if reverse else segments):
                raster.segment(a, b, .36, .36, owner, char)
            self.assertEqual(raster.chars[5][10], "|")
            return raster.text()
        self.assertEqual(draw(False), draw(True))

    def test_real_render_path_occlusion(self):
        # Custom connected tree: crossings at different Z. Reverse sibling order
        # and preserve parent references; actual render() must give the same frame.
        root = Segment((0., 0., 0., 0.), (-2., 0., -.5, .1), .12, .1, None, 0)
        far = Segment(root.end, (2., 0., -.5, .3), .08, .04, 0, 1)
        connector = Segment(root.end, (0., -2., .5, .2), .08, .06, 0, 1)
        near = Segment(connector.end, (0., 2., .5, .3), .05, .04, 2, 2)
        tree1 = Tree(1, (root, far, connector, near), ())
        tree2 = Tree(1, (root, connector, replace(near, parent=1), far), ())
        a = render(tree1, 80, 30, Camera(yaw=0, pitch=0))
        b = render(tree2, 80, 30, Camera(yaw=0, pitch=0))
        self.assertEqual(a, b)
        behind_connector = replace(connector, end=(0., -2., -.5, .2))
        behind_near = replace(near, start=behind_connector.end, end=(0., 2., -.5, .3))
        behind = render(Tree(1, (root, far, behind_connector, behind_near), ()),
                        80, 30, Camera(yaw=0, pitch=0))
        # Mirror only Z: bounds stay identical, while the crossing's nearer wood
        # changes from horizontal to vertical through the real render() pipeline.
        self.assertEqual(behind.splitlines()[18][40], "_")
        self.assertEqual(a.splitlines()[18][40], "|")

    def test_subpixel_horizontal_branch_is_connected(self):
        raster = Raster(30, 10)
        raster.segment((2.2, 4.5, 0), (27.2, 4.5, 0), .02, .01, 1)
        self.assertGreater(sum(c != " " for c in raster.chars[4]), 20)

    def test_all_camera_validation_boundaries(self):
        for field in ("yaw", "pitch", "angle4d", "zoom", "aspect", "time"):
            for value in (math.inf, -math.inf, math.nan):
                with self.assertRaises(ValueError):
                    render(self.tree, camera=replace(Camera(), **{field: value}))
        for kwargs in ({"zoom": 0}, {"zoom": -.1}, {"zoom": 9}, {"aspect": 0},
                       {"aspect": 1e-14}, {"mode": "5d"}, {"time": 1e10}):
            with self.assertRaises(ValueError):
                render(self.tree, camera=replace(Camera(), **kwargs))
        for dimensions in ((0, 30), (-1, 4), (80, 0), (1001, 2), (10, 501),
                           (1000, 500), (1.2, 2), (True, 1)):
            with self.assertRaises(ValueError):
                render(self.tree, *dimensions)

    def test_safe_extreme_views_and_animation(self):
        for angle in (-1e308, 1e308, 90, 180, 270):
            frame = render(self.tree, 12, 4, Camera(mode="4d", yaw=angle, pitch=angle,
                                                  angle4d=angle, zoom=8))
            self.assertEqual(len(frame), 52)
        for mode in ("2d", "3d", "4d"):
            self.assertNotEqual(render(self.tree, camera=Camera(mode=mode)),
                                render(self.tree, camera=Camera(mode=mode, time=1.5)))

    def test_empty_and_nonfinite_tree_rejected(self):
        with self.assertRaises(ValueError):
            render(Tree(1, (), ()))
        broken = Segment((0., 0., 0., 0.), (math.nan, 1., 0., .1), .1, .1, None, 0)
        with self.assertRaises(ValueError):
            render(Tree(1, (broken,), ()))

    def test_near_plane_through_production_renderer(self):
        # W normalization maps this endpoint exactly to the 4D camera plane.
        # Clipping must return a bounded ASCII frame, without division or inf.
        w = .5 + 4 / 1.35
        segment = Segment((0., 0., 0., w), (0., 1., 0., w), .1, .05, None, 0)
        for delta in (0, -1e-12, 1e-12, 1):
            s = replace(segment, start=(0, 0, 0, w + delta), end=(0, 1, 0, w + delta))
            frame = render(Tree(0, (s,), ()), 20, 10,
                           Camera(mode="4d", yaw=0, pitch=0))
            self.assertEqual(len(frame), 210)
            self.assertEqual(set(frame), {" ", "\n"})
