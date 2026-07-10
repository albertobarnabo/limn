import math
import unittest
from datetime import date, datetime

from limn.coerce import (is_missing, parse_number, parse_temporal,
                         proves_decimal_comma, temporal_ambiguous)


def num(v, **kw):
    parsed = parse_number(v, **kw)
    return None if parsed is None else parsed[0]


class TestParseNumber(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(num("42"), 42.0)
        self.assertEqual(num("-3.5"), -3.5)
        self.assertEqual(num("+7"), 7.0)
        self.assertEqual(num(13), 13.0)
        self.assertEqual(num(2.5), 2.5)
        self.assertEqual(num("1e3"), 1000.0)

    def test_thousands_us(self):
        self.assertEqual(num("1,234"), 1234.0)
        self.assertEqual(num("1,234,567.89"), 1234567.89)

    def test_thousands_european(self):
        self.assertEqual(num("1.234.567,89"), 1234567.89)
        self.assertEqual(num("3,14"), 3.14)          # decimal comma, provable
        self.assertEqual(num("1,234", decimal_comma=True), 1.234)

    def test_thousands_space(self):
        self.assertEqual(num("1 234 567,89"), 1234567.89)
        self.assertEqual(num("12 345"), 12345.0)

    def test_invalid_grouping_rejected(self):
        self.assertIsNone(num("1,23,4"))
        self.assertIsNone(num("12.34.56"))           # not 3-digit groups

    def test_currency(self):
        value, hint = parse_number("$1,234.50")
        self.assertEqual(value, 1234.5)
        self.assertEqual(hint.currency, "$")
        self.assertEqual(num("€ 99"), 99.0)
        self.assertEqual(num("1234 EUR"), 1234.0)
        self.assertEqual(num("USD 5.5"), 5.5)

    def test_percent(self):
        value, hint = parse_number("45%")
        self.assertEqual(value, 45.0)
        self.assertTrue(hint.percent)
        self.assertEqual(parse_number("3.2 %")[0], 3.2)

    def test_accounting_negative(self):
        self.assertEqual(num("(1,234)"), -1234.0)
        self.assertEqual(num("($500)"), -500.0)

    def test_unicode_minus(self):
        self.assertEqual(num("−12"), -12.0)

    def test_magnitude_suffixes(self):
        self.assertEqual(num("150k"), 150_000.0)
        self.assertEqual(num("3.2M"), 3_200_000.0)
        self.assertEqual(num("1.4bn"), 1_400_000_000.0)
        self.assertEqual(num("$2.5B"), 2_500_000_000.0)
        self.assertEqual(num("7T"), 7e12)

    def test_not_numbers(self):
        for v in ("hello", "12abc", "", "N/A", None, True, "1-2", "one"):
            self.assertIsNone(num(v), repr(v))

    def test_nan_is_not_a_number_here(self):
        self.assertIsNone(num(float("nan")))

    def test_proves_decimal_comma(self):
        self.assertTrue(proves_decimal_comma("3,14"))
        self.assertTrue(proves_decimal_comma("1.234,56"))
        self.assertFalse(proves_decimal_comma("1,234"))     # ambiguous
        self.assertFalse(proves_decimal_comma("1,234.5"))   # provably US
        self.assertFalse(proves_decimal_comma("plain"))


class TestParseTemporal(unittest.TestCase):
    def test_iso(self):
        self.assertEqual(parse_temporal("2026-07-10"), datetime(2026, 7, 10))
        self.assertEqual(parse_temporal("2026-07-10T14:30:00"),
                         datetime(2026, 7, 10, 14, 30))
        self.assertIsNotNone(parse_temporal("2026-07-10T14:30:00Z"))

    def test_python_objects(self):
        self.assertEqual(parse_temporal(date(2026, 1, 2)), datetime(2026, 1, 2))
        dt = datetime(2026, 1, 2, 3, 4)
        self.assertEqual(parse_temporal(dt), dt)

    def test_named_months(self):
        self.assertEqual(parse_temporal("Mar 3, 2026"), datetime(2026, 3, 3))
        self.assertEqual(parse_temporal("3 March 2026"), datetime(2026, 3, 3))
        self.assertEqual(parse_temporal("Mar 2026"), datetime(2026, 3, 1))

    def test_month_keys(self):
        self.assertEqual(parse_temporal("2024-01"), datetime(2024, 1, 1))
        self.assertEqual(parse_temporal("2024/07"), datetime(2024, 7, 1))

    def test_slashed(self):
        self.assertEqual(parse_temporal("2026/07/10"), datetime(2026, 7, 10))
        self.assertEqual(parse_temporal("13/02/2026"), datetime(2026, 2, 13))
        self.assertEqual(parse_temporal("02/13/2026"), datetime(2026, 2, 13))
        self.assertEqual(parse_temporal("07/10/2026", dayfirst=True),
                         datetime(2026, 10, 7))
        self.assertEqual(parse_temporal("07/10/2026", dayfirst=False),
                         datetime(2026, 7, 10))

    def test_two_digit_years(self):
        self.assertEqual(parse_temporal("1/2/26").year, 2026)
        self.assertEqual(parse_temporal("1/2/99").year, 1999)

    def test_dotted(self):
        self.assertEqual(parse_temporal("10.07.2026", dayfirst=True),
                         datetime(2026, 7, 10))

    def test_not_dates(self):
        for v in ("2026", "hello", "32/13/2026", "", None, 42):
            self.assertIsNone(parse_temporal(v), repr(v))

    def test_ambiguity_detector(self):
        self.assertTrue(temporal_ambiguous("07/10/2026"))
        self.assertFalse(temporal_ambiguous("13/02/2026"))
        self.assertFalse(temporal_ambiguous("2026-07-10"))
        self.assertFalse(temporal_ambiguous("7/7/26"))      # same either way


class TestMissing(unittest.TestCase):
    def test_missing_vocabulary(self):
        for v in (None, "", "  ", "N/A", "na", "NULL", "-", "—", "nan",
                  "#N/A", float("nan"), "None"):
            self.assertTrue(is_missing(v), repr(v))

    def test_not_missing(self):
        for v in (0, 0.0, "0", False, "no", "x"):
            self.assertFalse(is_missing(v), repr(v))


if __name__ == "__main__":
    unittest.main()
