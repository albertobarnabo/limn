import unittest
from datetime import datetime

from limn.ingest import ingest, IngestError, NUMBER, TEMPORAL, CATEGORY


class TestShapes(unittest.TestCase):
    def test_list_of_dicts(self):
        t = ingest([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}])
        self.assertEqual(t.names, ["a", "b"])
        self.assertEqual(t.col("a").kind, NUMBER)
        self.assertEqual(t.col("b").kind, CATEGORY)
        self.assertEqual(len(t), 2)

    def test_ragged_dicts_union_keys(self):
        t = ingest([{"a": 1}, {"a": 2, "b": 5}])
        self.assertEqual(t.names, ["a", "b"])
        self.assertEqual(t.col("b").values, [None, 5.0])

    def test_dict_of_lists(self):
        t = ingest({"x": [1, 2, 3], "y": [4, 5, 6]})
        self.assertEqual(t.col("y").values, [4.0, 5.0, 6.0])

    def test_plain_sequence(self):
        t = ingest([3, 1, 4, 1, 5])
        self.assertEqual(t.names, ["value"])
        self.assertEqual(t.col(0).kind, NUMBER)

    def test_generator(self):
        t = ingest(x * x for x in range(5))
        self.assertEqual(t.col(0).values, [0.0, 1.0, 4.0, 9.0, 16.0])

    def test_rows_with_header(self):
        t = ingest([["month", "sales"], ["Jan", 10], ["Feb", 20]])
        self.assertEqual(t.names, ["month", "sales"])
        self.assertEqual(t.col("sales").values, [10.0, 20.0])

    def test_rows_without_header(self):
        t = ingest([(1, 10), (2, 20)])
        self.assertEqual(t.names, ["col1", "col2"])

    def test_csv_text(self):
        t = ingest("date,revenue\n2026-01-01,\"1,204\"\n2026-02-01,980\n")
        self.assertEqual(t.col("date").kind, TEMPORAL)
        self.assertEqual(t.col("revenue").values, [1204.0, 980.0])

    def test_csv_semicolon_european(self):
        t = ingest("name;price\nwidget;3,14\ngadget;2,72\n")
        self.assertEqual(t.col("price").kind, NUMBER)
        self.assertEqual(t.col("price").values, [3.14, 2.72])

    def test_tsv(self):
        t = ingest("a\tb\n1\t2\n3\t4\n")
        self.assertEqual(t.col("b").values, [2.0, 4.0])

    def test_pandas_duck(self):
        class FakeFrame:
            columns = ["a"]
            def to_dict(self, orient):
                assert orient == "list"
                return {"a": [1, 2]}
        t = ingest(FakeFrame())
        self.assertEqual(t.col("a").values, [1.0, 2.0])

    def test_numpy_duck(self):
        class FakeArray:
            def tolist(self):
                return [1, 2, 3]
        t = ingest(FakeArray())
        self.assertEqual(t.col(0).values, [1.0, 2.0, 3.0])

    def test_empty_fails_helpfully(self):
        for bad in ([], {}, None):
            with self.assertRaises(IngestError):
                ingest(bad)

    def test_unknown_column_fails_helpfully(self):
        t = ingest({"a": [1]})
        with self.assertRaises(IngestError) as ctx:
            t.col("ghost")
        self.assertIn("'a'", str(ctx.exception))


class TestClassification(unittest.TestCase):
    def test_dirty_numeric_column(self):
        t = ingest({"price": ["$1,204", "$980", "N/A", "$1,150"]})
        col = t.col("price")
        self.assertEqual(col.kind, NUMBER)
        self.assertEqual(col.values, [1204.0, 980.0, None, 1150.0])
        self.assertEqual(col.currency, "$")

    def test_percent_column_keeps_its_unit(self):
        col = ingest({"growth": ["4.5%", "3.2%", "5.1%"]}).col("growth")
        self.assertEqual(col.kind, NUMBER)
        self.assertTrue(col.percent)

    def test_mostly_numbers_with_junk_notes(self):
        t = ingest({"n": ["1", "2", "3", "4", "oops"]})
        self.assertEqual(t.col("n").kind, NUMBER)
        self.assertEqual(t.col("n").values[-1], None)
        self.assertTrue(any("oops" in n for n in t.notes))

    def test_too_much_junk_becomes_category(self):
        t = ingest({"n": ["1", "a", "b", "c", "d"]})
        self.assertEqual(t.col("n").kind, CATEGORY)

    def test_temporal_column(self):
        col = ingest({"day": ["2026-01-01", "2026-01-02"]}).col("day")
        self.assertEqual(col.kind, TEMPORAL)
        self.assertEqual(col.values[0], datetime(2026, 1, 1))

    def test_dayfirst_forced_by_evidence(self):
        # 13/02 forces day-first; 07/10 then follows the column's convention
        col = ingest({"d": ["13/02/2026", "07/10/2026"]}).col("d")
        self.assertEqual(col.values[1], datetime(2026, 10, 7))

    def test_ambiguous_dates_resolved_by_chronology(self):
        # day-first reading (2/1, 3/1, 4/1 of January) is monotonic;
        # month-first (Jan 2, Mar 1, Apr 1... wait) — as month-first these
        # are Feb 1, Mar 1, Apr 1 which is ALSO monotonic — so pick a set
        # where only day-first is: 01/03, 02/03, 03/03 (three days in March)
        # month-first would be Jan 3, Feb 3, Mar 3 — also monotonic. Use
        # a genuinely disambiguating sequence instead:
        col = ingest({"d": ["05/03/2026", "12/03/2026", "04/04/2026"]}).col("d")
        # day-first: 5 Mar, 12 Mar, 4 Apr (monotonic).
        # month-first: May 3, Dec 3, Apr 4 (not monotonic).
        self.assertEqual(col.values[0], datetime(2026, 3, 5))

    def test_bools_are_categories(self):
        self.assertEqual(ingest({"ok": [True, False]}).col("ok").kind, CATEGORY)

    def test_year_numbers_stay_numbers(self):
        col = ingest({"year": [2019, 2020, 2021]}).col("year")
        self.assertEqual(col.kind, NUMBER)

    def test_european_decimal_comma_column(self):
        t = ingest({"v": ["3,14", "1,50", "2,00"]})
        self.assertEqual(t.col("v").values, [3.14, 1.5, 2.0])
        self.assertTrue(any("decimal comma" in n for n in t.notes))

    def test_all_missing_column(self):
        col = ingest({"v": ["N/A", None, ""]}).col("v")
        self.assertEqual(col.values, [None, None, None])


if __name__ == "__main__":
    unittest.main()
