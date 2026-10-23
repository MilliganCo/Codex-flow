from dataclasses import replace
import itertools
import math
from pathlib import Path
import unittest

from ascii_tree.geometry import View, Projector, rotate_xw, rotation_xw, perspective_factor
from ascii_tree.model import Point4, Segment, Tree, generate_tree
from ascii_tree.render import render
from tests.support import temporary_directory


def differing_cells(a, b):
    return sum(x != y for x, y in zip(a.text(), b.text()))


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_dimensions_ascii_and_determinism_all_modes(self):
        for mode, size in itertools.product(('2d', '3d', '4d'), ((80, 30), (100, 40))):
            with self.subTest(mode=mode, size=size):
                view = View(mode=mode, angle4=25)
                a = render(self.tree, view, *size)
                self.assertEqual(a, render(self.tree, view, *size))
                self.assertEqual(a.height, size[1])
                self.assertTrue(all(len(row) == size[0] for row in a.lines))
                self.assertTrue(all(32 <= ord(c) <= 126 for row in a.lines for c in row))
                self.assertNotIn('\x1b', a.text())
                self.assertGreater(sum(c != ' ' for row in a.lines for c in row), 100)

    def test_export_has_exact_ascii_lf_bytes(self):
        frame = render(self.tree, View(mode='4d'), 80, 30)
        with temporary_directory() as directory:
            target = frame.save(Path(directory) / 'frame.txt')
            data = target.read_bytes()
            self.assertEqual(len(data), 81 * 30)
            self.assertEqual(data, frame.text().encode('ascii'))
            self.assertNotIn(b'\r', data)
            self.assertNotIn(b'\x1b', data)

    def test_camera_rotation_changes_shape_not_only_horizontal_position(self):
        a = render(self.tree, View(yaw=0))
        b = render(self.tree, View(yaw=75, pitch=25))
        self.assertGreater(differing_cells(a, b), 300)
        a_counts = [sum(c != ' ' for c in row) for row in a.lines]
        b_counts = [sum(c != ' ' for c in row) for row in b.lines]
        self.assertNotEqual(a_counts, b_counts)

    def test_occlusion_is_depth_correct_and_independent_of_draw_order(self):
        # A near horizontal branch must hide a far vertical branch at crossing.
        near = Segment(Point4(-4, 0, 2, 0), Point4(4, 0, 2, 1), .02, .02, None, 1)
        far = Segment(Point4(0, -4, -2, 0), Point4(0, 4, -2, 1), .02, .02, None, 1)
        tree = Tree(0, (near, far), (), Point4(0, 0, 0, 0), 6)
        view = View(yaw=0, pitch=0)
        frame = render(tree, view, 81, 31)
        self.assertEqual(frame.lines[15][40], '-')
        self.assertEqual(frame, render(replace(tree, segments=(far, near)), view, 81, 31))
        far_in_front = replace(far, start=Point4(0, -4, 4, 0), end=Point4(0, 4, 4, 1))
        self.assertEqual(render(replace(tree, segments=(near, far_in_front)), view, 81, 31).lines[15][40], '|')

    def test_xw_matrix_orthogonal_nondegenerate_and_mixes_w(self):
        angle = math.radians(37)
        matrix = rotation_xw(angle)
        for i, j in itertools.product(range(4), repeat=2):
            dot = sum(matrix[k][i] * matrix[k][j] for k in range(4))
            self.assertAlmostEqual(dot, 1 if i == j else 0)
        determinant = 0
        for permutation in itertools.permutations(range(4)):
            inversions = sum(permutation[i] > permutation[j] for i in range(4) for j in range(i + 1, 4))
            determinant += (-1) ** inversions * math.prod(matrix[i][permutation[i]] for i in range(4))
        self.assertAlmostEqual(determinant, 1)
        point = Point4(1, 2, 3, 4)
        rotated = rotate_xw(point, angle)
        for i, axis in enumerate('xyzw'):
            self.assertAlmostEqual(getattr(rotated, axis), sum(matrix[i][j] * getattr(point, a) for j, a in enumerate('xyzw')))
        restored = rotate_xw(rotated, -angle)
        for axis in 'xyzw':
            self.assertAlmostEqual(getattr(restored, axis), getattr(point, axis))
        basis_w = rotate_xw(Point4(0, 0, 0, 1), math.pi / 2)
        self.assertAlmostEqual(basis_w.x, -1)
        self.assertAlmostEqual(basis_w.w, 0)

    def test_xw_rotation_changes_frame_using_same_geometry(self):
        original = self.tree.segments
        a = render(self.tree, View(mode='4d', angle4=0))
        b = render(self.tree, View(mode='4d', angle4=45))
        self.assertGreater(differing_cells(a, b), 250)
        self.assertIs(self.tree.segments, original)

    def test_4d_projection_uses_perspective_w(self):
        projector = Projector(self.tree, View(mode='4d', yaw=0, pitch=0), 100, 40)
        center = self.tree.center
        a = projector.project(Point4(2, center.y, 0, center.w))
        b = projector.project(Point4(2, center.y, 0, center.w + 5))
        self.assertGreater(b.x, a.x)

    def test_perspective_division_guard(self):
        for depth in (0, -1, .5, math.inf, math.nan):
            self.assertIsNone(perspective_factor(depth))
        projector = Projector(self.tree, View(mode='4d'), 80, 30)
        self.assertIsNone(projector.project(Point4(0, 0, 0, self.tree.center.w + 40)))
        projector = Projector(self.tree, View(yaw=0, pitch=0), 80, 30)
        self.assertIsNone(projector.project(Point4(0, 0, 45, 0)))

    def test_minimum_narrow_dimensions_and_zoom(self):
        for size, mode in itertools.product(((1, 1), (2, 2), (8, 4), (20, 10)), ('2d', '3d', '4d')):
            with self.subTest(size=size, mode=mode):
                frame = render(self.tree, View(mode=mode, zoom=8, angle4=90), *size)
                self.assertEqual((frame.width, frame.height), size)

    def test_animation_is_deterministic_and_changes_frame(self):
        for mode in ('2d', '3d', '4d'):
            a = render(self.tree, View(mode=mode))
            b = render(self.tree, View(mode=mode, time=2))
            self.assertNotEqual(a, b)
            self.assertEqual(b, render(self.tree, View(mode=mode, time=2)))

    def test_extreme_finite_angles_and_time_do_not_overflow(self):
        self.assertEqual(render(self.tree, View(time=1e308, yaw=1e308, angle4=-1e308), 20, 10).height, 10)

    def test_invalid_inputs_are_rejected(self):
        for size in ((0, 30), (80, 0), (501, 40), (80, 201)):
            with self.assertRaises(ValueError):
                render(self.tree, width=size[0], height=size[1])
        for view in (View(mode='5d'), View(zoom=0), View(zoom=9), View(yaw=math.nan)):
            with self.assertRaises(ValueError):
                render(self.tree, view)


if __name__ == '__main__':
    unittest.main()
