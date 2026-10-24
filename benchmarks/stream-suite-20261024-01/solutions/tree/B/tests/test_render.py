from dataclasses import replace
import math
import unittest

from ascii_tree.model import Point, Segment, Tree, generate_tree
from ascii_tree.render import Projected, Raster, View, project, project_4d, render_tree, rotate_xw


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_deterministic_frames(self):
        for mode in ('2d', '3d', '4d'):
            view = View(mode=mode, angle4d=37, time=2.5)
            self.assertEqual(render_tree(self.tree, 100, 40, view),
                             render_tree(generate_tree(42), 100, 40, view))

    def test_exact_ascii_dimensions(self):
        for width, height in ((80, 30), (100, 40), (1, 1), (2, 3), (12, 4), (500, 250)):
            for mode in ('2d', '3d', '4d'):
                frame = render_tree(self.tree, width, height, View(mode=mode))
                self.assertEqual(len(frame), (width+1)*height)
                self.assertEqual(len(frame.splitlines()), height)
                self.assertTrue(all(len(line) == width for line in frame.splitlines()))
                self.assertTrue(all(c == '\n' or 32 <= ord(c) <= 126 for c in frame))
                self.assertNotIn('\x1b', frame)
                if width >= 80:
                    self.assertGreater(len(frame.replace(' ', '').replace('\n', '')), 40)

    def test_3d_orbit_and_tilt_change_projection(self):
        base = render_tree(self.tree, view=View())
        self.assertNotEqual(base, render_tree(self.tree, view=View(yaw=68)))
        self.assertNotEqual(base, render_tree(self.tree, view=View(pitch=45)))
        # 2D has a fixed orthographic camera.
        self.assertEqual(render_tree(self.tree, view=View(mode='2d')),
                         render_tree(self.tree, view=View(mode='2d', yaw=90, pitch=45)))

    def test_occlusion_at_crossing_is_order_independent(self):
        near = (Projected(2, 5, 10, 1), Projected(12, 5, 10, 1), 'N')
        far = (Projected(7, 1, 20, 1), Projected(7, 9, 20, 1), 'F')
        results = []
        for order in ((near, far), (far, near)):
            raster = Raster(15, 11)
            for a, b, char in order:
                raster.line(a, b, .1, .1, char)
            self.assertEqual(raster.pixels[5*15+7], 'N')
            self.assertAlmostEqual(raster.depth[5*15+7], 10, delta=.5)
            results.append(raster.text())
        self.assertEqual(*results)
        # Swap depths: the formerly distant branch must now win.
        raster = Raster(15, 11)
        raster.line(replace(near[0], depth=20), replace(near[1], depth=20), .1, .1, 'N')
        raster.line(replace(far[0], depth=10), replace(far[1], depth=10), .1, .1, 'F')
        self.assertEqual(raster.pixels[5*15+7], 'F')

    def test_perspective_depth_interpolation(self):
        raster = Raster(11, 3)
        raster.line(Projected(0, 1, 10, 1), Projected(10, 1, 30, 1), .01, .01, '#')
        self.assertAlmostEqual(raster.depth[16], 15, delta=.02)

    def test_camera_rotation_reverses_world_space_occlusion(self):
        horizontal = Segment(Point(-2, 6, -2, .5), Point(2, 6, -2, .5), .01, .01, None, 1)
        vertical = Segment(Point(0, 4, 2, .5), Point(0, 8, 2, .5), .01, .01, None, 1)
        tree = Tree(0, (horizontal, vertical), ())
        front = render_tree(tree, 21, 15, View(yaw=0, pitch=0)).splitlines()[7][10]
        back = render_tree(tree, 21, 15, View(yaw=180, pitch=0)).splitlines()[7][10]
        self.assertEqual(front, '-')
        self.assertEqual(back, '|')
        reversed_tree = Tree(0, (vertical, horizontal), ())
        self.assertEqual(render_tree(tree), render_tree(reversed_tree))

    def test_real_tree_segment_order_does_not_affect_frame(self):
        reversed_tree = Tree(42, tuple(reversed(self.tree.segments)), tuple(reversed(self.tree.leaves)))
        self.assertEqual(render_tree(self.tree), render_tree(reversed_tree))

    def test_digital_centerline_is_connected(self):
        tree = Tree(42, self.tree.segments, ())
        frame = render_tree(tree, 100, 40, View(mode='2d')).splitlines()
        occupied = {(x, y) for y, row in enumerate(frame) for x, c in enumerate(row) if c != ' '}
        visited = {next(iter(occupied))}
        pending = list(visited)
        while pending:
            x, y = pending.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbor = (x+dx, y+dy)
                    if neighbor in occupied and neighbor not in visited:
                        visited.add(neighbor)
                        pending.append(neighbor)
        self.assertEqual(occupied, visited)

    def test_true_xw_rotation_orthogonal_invertible(self):
        p = Point(3, 4, 5, 2)
        self.assertEqual(rotate_xw(p, 0), p)
        for angle in (17, 45, 90, 180, -37):
            q = rotate_xw(p, angle)
            self.assertEqual((q.y, q.z), (p.y, p.z))
            self.assertAlmostEqual(q.x*q.x+q.w*q.w, p.x*p.x+p.w*p.w)
            inverse = rotate_xw(q, -angle)
            self.assertAlmostEqual(inverse.x, p.x)
            self.assertAlmostEqual(inverse.w, p.w)
        q = rotate_xw(p, 90)
        self.assertAlmostEqual(q.x, -p.w)
        self.assertAlmostEqual(q.w, p.x)
        self.assertNotEqual(project_4d(p, 0), project_4d(p, 45))

    def test_variable_w_and_xw_rotation_change_frame(self):
        self.assertGreater(len({s.end.w for s in self.tree.segments}), 10)
        frames = [render_tree(self.tree, view=View(mode='4d', angle4d=a)) for a in (0, 35, 80)]
        self.assertEqual(len(set(frames)), 3)

    def test_projection_clips_eye_planes(self):
        self.assertIsNone(project_4d(Point(0, 0, 0, 2.5), 0))
        self.assertIsNone(project(Point(0, 6, -24, .5), View(yaw=0, pitch=0), 80, 30))
        for angle in range(0, 360, 15):
            frame = render_tree(self.tree, 3, 2, View(mode='4d', angle4d=angle, zoom=5))
            self.assertEqual(len(frame), 8)
        raster = Raster(4, 3)
        raster.line(Projected(-1e10, 1, 10, 1), Projected(1e10, 1, 10, 1), .01, .01, '#')
        self.assertIn('#', raster.text())

    def test_parameter_validation(self):
        for params in ({'zoom': 0}, {'zoom': 6}, {'yaw': math.inf}, {'angle4d': math.nan},
                       {'aspect': 0}, {'mode': '5d'}):
            with self.assertRaises(ValueError):
                View(**params)
        for dimensions in ((0, 3), (80, 0), (-1, 30), (501, 40), (100, 251)):
            with self.assertRaises(ValueError):
                render_tree(self.tree, *dimensions)
