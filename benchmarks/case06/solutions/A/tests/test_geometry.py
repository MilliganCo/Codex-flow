import math
import unittest

from ascii_tree.geometry import Point4, project4, rotate3, rotation4, transform4


class GeometryTests(unittest.TestCase):
    def test_4d_rotation_is_orthogonal_and_invertible_in_every_plane(self):
        p = Point4(2, 3, 5, 7)
        for plane in ("xw", "yw", "zw"):
            with self.subTest(plane=plane):
                matrix = rotation4(0.73, plane)
                for i in range(4):
                    for j in range(4):
                        self.assertAlmostEqual(sum(matrix[i][k] * matrix[j][k] for k in range(4)), float(i == j))
                q = transform4(p, matrix)
                self.assertAlmostEqual(sum(x * x for x in p.values()), sum(x * x for x in q.values()))
                back = transform4(q, rotation4(-0.73, plane))
                for a, b in zip(p.values(), back.values()):
                    self.assertAlmostEqual(a, b)

    def test_xw_quarter_turn_mixes_spatial_and_growth_coordinates(self):
        q = transform4(Point4(2, 3, 5, 7), rotation4(math.pi / 2))
        self.assertAlmostEqual(q.x, -7)
        self.assertAlmostEqual(q.w, 2)
        self.assertEqual((q.y, q.z), (3, 5))

    def test_4d_perspective_and_near_hyperplane(self):
        self.assertEqual(project4(Point4(2, 3, 4, 5), 10), (4, 6, 8))
        for w in (9.9, 10, 11, 1000):
            self.assertIsNone(project4(Point4(1, 2, 3, w), 10))

    def test_true_3d_rotation_changes_depth(self):
        x, y, z = rotate3(2, 3, 4, math.pi / 2, 0)
        self.assertAlmostEqual(x, 4)
        self.assertEqual(y, 3)
        self.assertAlmostEqual(z, -2)

    def test_invalid_hyperplane_is_rejected(self):
        with self.assertRaises(ValueError):
            rotation4(1, "xx")
