import math
import unittest

from ascii_tree.geometry import Camera, project_4d, rotate_xw, xw_matrix
from ascii_tree.model import Point4


class GeometryTests(unittest.TestCase):
    def test_xw_quarter_turn_mixes_w_with_x(self):
        result = rotate_xw(Point4(2, 3, 4, 5), 90)
        self.assertAlmostEqual(result.x, -5)
        self.assertEqual((result.y, result.z), (3, 4))
        self.assertAlmostEqual(result.w, 2)

    def test_matrix_is_orthogonal_and_not_degenerate(self):
        matrix = xw_matrix(37)
        self.assertGreater(abs(matrix[0][3]), 0.5)
        for i in range(4):
            for j in range(4):
                self.assertAlmostEqual(sum(matrix[k][i] * matrix[k][j] for k in range(4)), float(i == j))
        # Explicit XW minor determinant (YZ block is identity).
        self.assertAlmostEqual(matrix[0][0] * matrix[3][3] - matrix[0][3] * matrix[3][0], 1)

    def test_rotation_preserves_four_dimensional_norm_and_inverts(self):
        point = Point4(2, -3, 7, 5)
        result = rotate_xw(point, 51)
        self.assertAlmostEqual(sum(v * v for v in (point.x, point.y, point.z, point.w)),
                               sum(v * v for v in (result.x, result.y, result.z, result.w)))
        inverse = rotate_xw(result, -51)
        self.assertAlmostEqual(inverse.x, point.x)
        self.assertAlmostEqual(inverse.w, point.w)

    def test_perspective_4d_uses_w_and_clips_eye_plane(self):
        self.assertEqual(project_4d(Point4(2, 4, 6, 12)), (4, 8, 12, 2))
        self.assertIsNone(project_4d(Point4(1, 1, 1, 24)))
        self.assertIsNone(project_4d(Point4(1, 1, 1, 25)))
        self.assertIsNone(project_4d(Point4(1, 1, 1, math.nan)))

    def test_3d_camera_rotates_spatial_coordinates_and_clips(self):
        x, y, z = Camera(yaw=90, pitch=0).transform((2, 3, 4))
        self.assertAlmostEqual(x, 4)
        self.assertAlmostEqual(z, -2)
        self.assertEqual(y, 3)
        self.assertIsNone(Camera(yaw=0, pitch=0).project((0, 0, 34)))


if __name__ == "__main__":
    unittest.main()
