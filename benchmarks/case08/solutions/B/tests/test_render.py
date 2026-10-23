from dataclasses import replace
import math
from pathlib import Path
import tempfile
import unittest
from ascii_tree.geometry import rotate_xw, xw_matrix, project, perspective_factor
from ascii_tree.model import Point, generate_tree
from ascii_tree.render import Canvas, RenderOptions, draw_segment, render, export_frame


class ProjectionTests(unittest.TestCase):
    def test_identity_and_norm_preserving_xw(self):
        p = Point(2., 3., -1., 5.)
        self.assertEqual(rotate_xw(p, 0.), p)
        q = rotate_xw(p, math.pi / 2)
        self.assertAlmostEqual(q.x, -5)
        self.assertAlmostEqual(q.w, 2)
        self.assertEqual((q.y, q.z), (p.y, p.z))
        self.assertAlmostEqual(q.x**2 + q.y**2 + q.z**2 + q.w**2, 39)

    def test_xw_matrix_is_nondegenerate_and_mixes_w(self):
        m = xw_matrix(.63)
        self.assertNotEqual(m[0][3], 0)
        self.assertNotEqual(m[3][0], 0)
        self.assertAlmostEqual(m[0][0] * m[3][3] - m[0][3] * m[3][0], 1)
        for i in range(4):
            for j in range(4):
                self.assertAlmostEqual(sum(m[k][i] * m[k][j] for k in range(4)), float(i == j))
        p = Point(2, 3, 4, 5)
        q = rotate_xw(p, .63)
        expected = [sum(a*b for a,b in zip(row, (2,3,4,5))) for row in m]
        for actual, value in zip((q.x,q.y,q.z,q.w), expected):
            self.assertAlmostEqual(actual, value)

    def test_4d_to_3d_to_2d_numeric(self):
        p = Point(2, 7.5, 3, 4)
        q = rotate_xw(p, .4)
        f4 = 24 / (24 - q.w)
        depth = 32 - q.z * f4
        x, y, d, _ = project(p, "4d", 0, 0, .4)
        self.assertAlmostEqual(x, q.x * f4 * 32 / depth)
        self.assertAlmostEqual(y, (q.y - 5.5) * f4 * 32 / depth)
        self.assertAlmostEqual(d, depth)

    def test_perspective_near_plane_guard(self):
        self.assertLessEqual(perspective_factor(24., 24.), 1 / .15)
        self.assertTrue(all(math.isfinite(v) for v in project(Point(1, 2, 32, 24), "4d", 0, 0, 0)))


class RasterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = generate_tree(42)

    def test_deterministic_frames(self):
        for mode in ("2d", "3d", "4d"):
            o = RenderOptions(80, 30, mode)
            self.assertEqual(render(self.tree, o), render(generate_tree(42), o))

    def test_sizes_printable_ascii_and_no_ansi(self):
        for width, height in ((80,30),(100,40),(20,6),(1,1),(2,2)):
            for mode in ("2d","3d","4d"):
                frame = render(self.tree, RenderOptions(width,height,mode))
                self.assertEqual(len(frame.splitlines()), height)
                self.assertTrue(all(len(line) == width for line in frame.splitlines()))
                self.assertTrue(all(c == "\n" or 32 <= ord(c) <= 126 for c in frame))
                self.assertNotIn("\x1b",frame)

    def test_3d_orbit_and_tilt_change_structure(self):
        base = RenderOptions(100,40,"3d",0,0)
        a = render(self.tree,base)
        for option in (replace(base,yaw=1.2), replace(base,pitch=.7)):
            b = render(self.tree,option)
            self.assertGreater(sum(x != y for x,y in zip(a,b)), 250)
            # Vertical distributions also change: this is not a horizontal shift.
            self.assertNotEqual([len(row.strip()) for row in a.splitlines()],
                                [len(row.strip()) for row in b.splitlines()])

    def test_4d_rotation_changes_frame(self):
        base = RenderOptions(100,40,"4d",angle4=0)
        a = render(self.tree,base)
        b = render(self.tree,replace(base,angle4=math.pi/4))
        self.assertGreater(sum(x != y for x,y in zip(a,b)),250)

    def test_nearer_segment_wins_independent_of_draw_order(self):
        for reverse in (False,True):
            canvas = Canvas(11,11)
            far = ((0,5,30),(10,5,30),"F")
            near = ((5,0,20),(5,10,20),"N")
            for a,b,glyph in ((near,far) if reverse else (far,near)):
                draw_segment(canvas,a,b,.1,.1,glyph=glyph)
            self.assertEqual(canvas.pixels[5][5],"N")
            self.assertAlmostEqual(canvas.depth[5][5],20)
            self.assertEqual(canvas.pixels[5][1],"F")

    def test_depth_interpolation_changes_occlusion_along_segment(self):
        canvas = Canvas(11,3)
        draw_segment(canvas,(0,1,30),(10,1,30),.1,.1,glyph="B")
        draw_segment(canvas,(0,1,40),(10,1,20),.1,.1,glyph="A")
        self.assertEqual(canvas.pixels[1][0],"B")
        self.assertEqual(canvas.pixels[1][10],"A")

    def test_taper_has_more_pixels_at_base(self):
        canvas = Canvas(21,21)
        draw_segment(canvas,(10,2,20),(10,18,20),3,.1)
        counts = [sum(c != " " for c in row) for row in canvas.pixels]
        self.assertGreater(counts[3],counts[17])

    def test_aspect_changes_horizontal_footprint(self):
        base = RenderOptions(140,30,"2d",aspect=.5)
        self.assertNotEqual(render(self.tree,base),render(self.tree,replace(base,aspect=1.)))

    def test_export_canonical_bytes(self):
        frame = render(self.tree,RenderOptions(80,30))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"tree.txt"
            export_frame(frame,path)
            data=path.read_bytes()
            self.assertEqual(data,frame.encode("ascii"))
            self.assertNotIn(b"\r",data)
            self.assertEqual(len(data),81*30)

    def test_invalid_parameters_rejected(self):
        for kwargs in ({"width":0},{"height":501},{"zoom":0},{"aspect":0},
                       {"mode":"5d"},{"yaw":float("nan")},{"angle4":float("inf")}):
            with self.assertRaises(ValueError):
                RenderOptions(**kwargs)
