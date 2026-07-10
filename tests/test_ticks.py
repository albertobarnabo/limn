import unittest
from datetime import datetime

from limn.ticks import (linear_ticks, time_ticks, log_ticks,
                        axis_formatter, fmt_value)


class TestLinearTicks(unittest.TestCase):
    def assert_contains_data(self, ticks, lo, hi):
        self.assertLessEqual(ticks[0], lo)
        self.assertGreaterEqual(ticks[-1], hi)

    def assert_even_steps(self, ticks):
        steps = [round(b - a, 9) for a, b in zip(ticks, ticks[1:])]
        self.assertEqual(len(set(steps)), 1, "uneven steps: %r" % ticks)

    def test_canonical_ranges(self):
        cases = [(0, 100), (0, 1), (-50, 50), (0.001, 0.008),
                 (12, 87), (1e6, 3e6), (-3, 17), (0, 0.0007)]
        for lo, hi in cases:
            ticks = linear_ticks(lo, hi)
            self.assert_contains_data(ticks, lo, hi)
            self.assert_even_steps(ticks)
            self.assertGreaterEqual(len(ticks), 2)
            self.assertLessEqual(len(ticks), 10)

    def test_zero_to_hundred_is_classic(self):
        self.assertEqual(linear_ticks(0, 100), [0, 25, 50, 75, 100])

    def test_prefers_nice_steps(self):
        # 0..73 should label with a nice step (25s), not 73/4ths
        ticks = linear_ticks(0, 73)
        step = ticks[1] - ticks[0]
        self.assertIn(step, (10, 20, 25, 50))

    def test_degenerate_single_value(self):
        ticks = linear_ticks(5, 5)
        self.assert_contains_data(ticks, 5, 5)
        ticks = linear_ticks(0, 0)
        self.assertGreaterEqual(len(ticks), 2)

    def test_negative_only_range(self):
        ticks = linear_ticks(-90, -10)
        self.assert_contains_data(ticks, -90, -10)
        self.assert_even_steps(ticks)

    def test_zero_is_exact(self):
        for t in linear_ticks(-10, 10):
            if abs(t) < 1e-12:
                self.assertEqual(t, 0.0)

    def test_deterministic(self):
        self.assertEqual(linear_ticks(3, 19), linear_ticks(3, 19))


class TestTimeTicks(unittest.TestCase):
    def test_month_span_gives_month_starts(self):
        ticks = time_ticks(datetime(2026, 1, 15), datetime(2026, 6, 20))
        for t, _label in ticks:
            self.assertEqual(t.day, 1)

    def test_quarters_align_to_calendar_quarters(self):
        ticks = time_ticks(datetime(2024, 2, 1), datetime(2026, 3, 1))
        months = {t.month for t, _l in ticks}
        self.assertTrue(months <= {1, 4, 7, 10}, months)

    def test_year_label_appears_once_then_on_change(self):
        ticks = time_ticks(datetime(2025, 10, 15), datetime(2026, 4, 10))
        labels = [l for _t, l in ticks]
        with_year = [l for l in labels if any(c.isdigit() and len(w) == 4
                     for w in l.split() for c in w)]
        self.assertEqual(len(with_year), 2)   # first tick + January

    def test_week_ticks_are_mondays(self):
        ticks = time_ticks(datetime(2026, 7, 1), datetime(2026, 8, 20))
        for t, _l in ticks:
            self.assertEqual(t.weekday(), 0)

    def test_hour_span(self):
        ticks = time_ticks(datetime(2026, 7, 10, 9), datetime(2026, 7, 10, 17))
        self.assertGreaterEqual(len(ticks), 3)
        self.assertIn(":", ticks[0][1])

    def test_multiyear(self):
        ticks = time_ticks(datetime(1995, 3, 1), datetime(2026, 1, 1))
        self.assertTrue(all(t.month == 1 and t.day == 1 for t, _l in ticks))

    def test_within_bounds(self):
        lo, hi = datetime(2026, 1, 3), datetime(2026, 11, 27)
        for t, _l in time_ticks(lo, hi):
            self.assertTrue(lo <= t <= hi)


class TestLogTicks(unittest.TestCase):
    def test_decades(self):
        self.assertEqual(log_ticks(1, 1000), [1, 10, 100, 1000])

    def test_wide_range_strides(self):
        ticks = log_ticks(1, 1e12, target=6)
        self.assertLessEqual(len(ticks), 8)

    def test_fractional(self):
        ticks = log_ticks(0.002, 5)
        self.assertLessEqual(ticks[0], 0.002)
        self.assertGreaterEqual(ticks[-1], 5)


class TestFormatting(unittest.TestCase):
    def test_axis_consistent_scale(self):
        fmt = axis_formatter([0, 500_000, 1_000_000, 1_500_000])
        self.assertEqual([fmt(t) for t in [0, 500_000, 1_000_000, 1_500_000]],
                         ["0.0M", "0.5M", "1.0M", "1.5M"])

    def test_axis_small_integers(self):
        fmt = axis_formatter([0, 25, 50, 75, 100])
        self.assertEqual(fmt(75), "75")

    def test_axis_thousands_commas(self):
        fmt = axis_formatter([0, 2500, 5000])
        self.assertEqual(fmt(2500), "2,500")

    def test_axis_units(self):
        fmt = axis_formatter([0, 50, 100], percent=True)
        self.assertEqual(fmt(50), "50%")
        fmt = axis_formatter([0, 1000, 2000], currency="€")
        self.assertEqual(fmt(1000), "€1,000")

    def test_axis_negative_currency(self):
        fmt = axis_formatter([-2000, 0, 2000], currency="$")
        self.assertEqual(fmt(-2000), "-$2,000")

    def test_no_negative_zero(self):
        fmt = axis_formatter([-1, 0, 1])
        self.assertEqual(fmt(-0.0), "0")

    def test_fmt_value(self):
        self.assertEqual(fmt_value(1_500_000), "1.5M")
        self.assertEqual(fmt_value(999), "999")
        self.assertEqual(fmt_value(0.25), "0.25")
        self.assertEqual(fmt_value(42.0), "42")
        self.assertEqual(fmt_value(12_000), "12k")
        self.assertEqual(fmt_value(None), "–")
        self.assertEqual(fmt_value(45.0, percent=True), "45%")


if __name__ == "__main__":
    unittest.main()
