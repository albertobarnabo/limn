import unittest

from limn.marks import stack_series, bar_geometry, size_scale, contrast_ink
from limn.svg import rounded_bar, polyline_path, crisp
from limn.theme import PAPER, DUSK, ramp_color
from limn.metrics import text_width, truncate_to


class TestStacking(unittest.TestCase):
    def test_cumulative(self):
        xs, layers = stack_series([
            {"name": "a", "color": "x", "points": [(1, 10), (2, 20)]},
            {"name": "b", "color": "y", "points": [(1, 5), (2, 1)]},
        ])
        self.assertEqual(xs, [1, 2])
        self.assertEqual(layers[0]["upper"], [10, 20])
        self.assertEqual(layers[1]["lower"], [10, 20])
        self.assertEqual(layers[1]["upper"], [15, 21])

    def test_missing_contributes_zero(self):
        _xs, layers = stack_series([
            {"name": "a", "color": "x", "points": [(1, 10), (2, None)]},
            {"name": "b", "color": "y", "points": [(1, 1), (2, 2)]},
        ])
        self.assertEqual(layers[0]["upper"], [10, 0])
        self.assertEqual(layers[1]["upper"], [11, 2])


class TestBarGeometry(unittest.TestCase):
    def test_single_bar_capped(self):
        w, offsets = bar_geometry(1, 80, bar_max=24)
        self.assertEqual(w, 24)
        self.assertEqual(offsets, [-12])

    def test_group_fits_with_gaps(self):
        n, bw = 3, 50
        w, offsets = bar_geometry(n, bw, bar_max=24)
        total = n * w + (n - 1) * 2
        self.assertLessEqual(total, bw + 1e-9)
        self.assertAlmostEqual(offsets[1] - offsets[0], w + 2)

    def test_never_negative_width(self):
        w, _ = bar_geometry(10, 8, bar_max=24)
        self.assertGreaterEqual(w, 1)


class TestSizeScale(unittest.TestCase):
    def test_range(self):
        f = size_scale([0, 50, 100])
        self.assertAlmostEqual(f(0), 3.0)
        self.assertAlmostEqual(f(100), 11.0)
        self.assertTrue(3.0 < f(50) < 11.0)

    def test_constant_and_empty(self):
        self.assertEqual(size_scale([5, 5])(5), 7.0)
        self.assertIsInstance(size_scale([])(None), float)


class TestColor(unittest.TestCase):
    def test_contrast_ink_flips(self):
        self.assertEqual(contrast_ink("#0d366b", PAPER), "#ffffff")
        self.assertEqual(contrast_ink("#cde2fb", PAPER), PAPER.ink)

    def test_ramp_interpolation_endpoints(self):
        self.assertEqual(ramp_color(PAPER, 0.0), PAPER.ramp[0])
        self.assertEqual(ramp_color(PAPER, 1.0), PAPER.ramp[-1])
        self.assertTrue(ramp_color(PAPER, 0.5).startswith("#"))

    def test_fixed_slot_order_never_cycles(self):
        self.assertEqual(PAPER.series_color(0), PAPER.series[0])
        self.assertEqual(PAPER.series_color(8), PAPER.series[0])
        self.assertEqual(len(set(PAPER.series)), 8)
        self.assertEqual(len(set(DUSK.series)), 8)


class TestSvgPrimitives(unittest.TestCase):
    def test_rounded_bar_paths_close(self):
        for side in ("top", "bottom", "left", "right"):
            d = rounded_bar(10, 10, 30, 40, 4, side)
            self.assertTrue(d.startswith("M"))
            self.assertTrue(d.endswith("Z"))
            self.assertNotIn("nan", d)

    def test_polyline_gaps(self):
        d = polyline_path([(0, 0), (1, 1), None, (2, 2), (3, 3)])
        self.assertEqual(d.count("M"), 2)

    def test_crisp(self):
        self.assertEqual(crisp(10.7), 10.5)


class TestMetrics(unittest.TestCase):
    def test_monotonic(self):
        self.assertLess(text_width("hi", 11), text_width("hello", 11))
        self.assertLess(text_width("il", 11), text_width("WM", 11))

    def test_bold_is_wider(self):
        self.assertLess(text_width("Revenue", 11),
                        text_width("Revenue", 11, bold=True))

    def test_truncate_fits(self):
        s = truncate_to("a very long series name indeed", 11, 60)
        self.assertLessEqual(text_width(s, 11), 60)
        self.assertTrue(s.endswith("…"))
        self.assertEqual(truncate_to("ok", 11, 60), "ok")


if __name__ == "__main__":
    unittest.main()
