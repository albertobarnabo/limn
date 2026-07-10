import unittest
from datetime import datetime

from limn.scales import Linear, Time, Log, Band


class TestLinear(unittest.TestCase):
    def test_maps_endpoints(self):
        s = Linear(0, 100)
        self.assertEqual(s.to_px(s.lo, 0, 200), 0)
        self.assertEqual(s.to_px(s.hi, 0, 200), 200)
        self.assertIsNone(s.to_px(None, 0, 200))

    def test_include_zero(self):
        s = Linear(40, 90, include_zero=True)
        self.assertLessEqual(s.lo, 0)

    def test_padding_never_crosses_zero(self):
        s = Linear(0.6, 82, pad_frac=0.05)
        self.assertGreaterEqual(s.lo, 0.0, "padding invented negative space")
        s = Linear(-82, -0.6, pad_frac=0.05)
        self.assertLessEqual(s.hi, 0.0)

    def test_domain_snaps_to_ticks(self):
        s = Linear(3, 97)
        self.assertLessEqual(s.lo, 3)
        self.assertGreaterEqual(s.hi, 97)
        self.assertEqual(s.lo, s.ticks[0])


class TestTime(unittest.TestCase):
    def test_contains_data(self):
        lo, hi = datetime(2026, 1, 15), datetime(2026, 3, 2)
        s = Time(lo, hi)
        self.assertLessEqual(s.lo, lo)
        self.assertGreaterEqual(s.hi, hi)
        px = s.to_px(datetime(2026, 2, 1), 0, 100)
        self.assertTrue(0 <= px <= 100)

    def test_degenerate_single_instant(self):
        t = datetime(2026, 1, 1)
        s = Time(t, t)
        self.assertLess(s.lo, s.hi)


class TestLog(unittest.TestCase):
    def test_decade_mapping(self):
        s = Log(1, 1000)
        mid = s.to_px(10, 0, 300)
        self.assertAlmostEqual(mid, 100, delta=1)

    def test_rejects_nonpositive(self):
        with self.assertRaises(ValueError):
            Log(0, 10)

    def test_nonpositive_values_unmapped(self):
        s = Log(1, 100)
        self.assertIsNone(s.to_px(0, 0, 100))
        self.assertIsNone(s.to_px(-5, 0, 100))


class TestBand(unittest.TestCase):
    def test_centers_and_width(self):
        b = Band(["a", "b", "c", "b"])          # dupes collapse, order kept
        self.assertEqual(b.categories, ["a", "b", "c"])
        self.assertAlmostEqual(b.center("a", 0, 300), 50)
        self.assertAlmostEqual(b.center("c", 0, 300), 250)
        self.assertLess(b.bandwidth(0, 300), b.slot(0, 300))

    def test_unknown_category(self):
        self.assertIsNone(Band(["a"]).center("zzz", 0, 100))


if __name__ == "__main__":
    unittest.main()
