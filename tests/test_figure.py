import contextlib
import io
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import limn
from limn.ingest import IngestError
from limn.metrics import text_width

NS = "{http://www.w3.org/2000/svg}"


def parse(fig):
    svg = fig.to_svg()
    return ET.fromstring(svg), svg


def texts(root):
    return [(el.text or "", el.attrib) for el in root.iter(NS + "text")]


def text_content(root):
    return " | ".join(t for t, _a in texts(root))


DAYS = [datetime(2026, 1, 1) + timedelta(days=7 * i) for i in range(12)]


class TestEveryKindRenders(unittest.TestCase):
    def test_line_multi(self):
        fig = limn.line({"d": DAYS, "a": list(range(12)),
                         "b": [i * 2 for i in range(12)]}, x="d",
                        title="T")
        root, _svg = parse(fig)
        content = text_content(root)
        self.assertIn("a", content)      # legend + direct labels
        self.assertIn("b", content)

    def test_single_series_has_no_legend(self):
        fig = limn.line({"d": DAYS, "only": list(range(12))}, x="d")
        root, _ = parse(fig)
        rects = [el for el in root.iter(NS + "rect")
                 if el.get("width") == "10"]     # legend swatches are 10x10
        self.assertEqual(rects, [])

    def test_two_series_always_have_legend(self):
        fig = limn.line({"d": DAYS, "a": list(range(12)),
                         "b": list(range(12))}, x="d")
        root, _ = parse(fig)
        swatches = [el for el in root.iter(NS + "rect")
                    if el.get("width") == "10"]
        self.assertEqual(len(swatches), 2)

    def test_bar_grouped_and_stacked(self):
        data = {"q": ["Q1", "Q2"], "a": [1, 2], "b": [3, 4]}
        for stack in (False, True):
            root, svg = parse(limn.bar(data, stack=stack))
            self.assertGreaterEqual(
                sum(1 for _ in root.iter(NS + "path")), 4)

    def test_currency_axis(self):
        fig = limn.bar({"m": ["a", "b"], "v": ["$1,200", "$3,400"]})
        self.assertIn("$", text_content(parse(fig)[0]))

    def test_percent_axis(self):
        fig = limn.line({"x": [1, 2, 3], "y": ["10%", "20%", "15%"]}, x="x")
        self.assertIn("%", text_content(parse(fig)[0]))

    def test_hist_and_heatmap_and_scatter(self):
        parse(limn.hist([1, 2, 2, 3, 3, 3, 4, 9] * 10))
        parse(limn.heatmap([[1, 2], [3, 4]]))
        parse(limn.scatter({"x": [1, 2, 3], "y": [4, 5, 6]}, x="x", y="y"))

    def test_heatmap_annotations_flip_ink(self):
        fig = limn.heatmap({"row": ["r1", "r2"],
                            "A": [1, 100], "B": [50, 99]}).size(720, 432)
        root, _ = parse(fig)
        fills = {}
        for t, a in texts(root):
            fills.setdefault(t, set()).add(a.get("fill"))
        # (the ramp legend also prints "1" and "100", in muted ink)
        self.assertIn("#ffffff", fills["100"])       # dark cell, white ink
        self.assertNotIn("#ffffff", fills["1"])      # light cell, dark ink


class TestHonestFailures(unittest.TestCase):
    def test_empty(self):
        with self.assertRaises(IngestError):
            limn.line([])

    def test_all_missing(self):
        with self.assertRaises(IngestError):
            limn.line({"x": [1, 2], "y": [None, None]}, x="x", y="y").to_svg()

    def test_too_small(self):
        fig = limn.line({"x": [1, 2], "y": [3, 4]}, x="x").size(80, 60)
        with self.assertRaises(ValueError) as ctx:
            fig.to_svg()
        self.assertIn("too small", str(ctx.exception))

    def test_unknown_theme(self):
        with self.assertRaises(ValueError):
            limn.line({"x": [1], "y": [2]}).theme("neon").to_svg()

    def test_log_axis_with_no_positive_values(self):
        with self.assertRaises(IngestError):
            limn.line({"x": [1, 2], "y": [-1, -2]}, x="x",
                      ylog=True).to_svg()


class TestRobustFallbacks(unittest.TestCase):
    def test_stacked_area_with_negatives_falls_back(self):
        fig = limn.area({"x": [1, 2], "a": [3, 4], "b": [-1, 2]}, x="x")
        fig.to_svg()
        self.assertTrue(any("stacked area" in n for n in fig.notes))

    def test_line_gap_note(self):
        fig = limn.line({"x": [1, 2, 3], "y": [1, None, 3]}, x="x", y="y")
        fig.to_svg()
        self.assertTrue(any("gap" in n for n in fig.notes))

    def test_ylog_drops_nonpositive_with_note(self):
        fig = limn.line({"x": [1, 2, 3], "y": [0, 10, 100]}, x="x", y="y",
                        ylog=True)
        fig.to_svg()
        self.assertTrue(any("log axis" in n for n in fig.notes))


class TestLayoutInvariants(unittest.TestCase):
    """The promise: a limn chart cannot clip its own labels."""

    def assert_no_clipped_text(self, fig):
        root, svg = parse(fig)
        w = float(root.get("width"))
        h = float(root.get("height"))
        for content, attrs in texts(root):
            if not content:
                continue
            x = float(attrs.get("x", 0))
            size = float(attrs.get("font-size", 11))
            anchor = attrs.get("text-anchor", "start")
            width = text_width(content, size,
                               attrs.get("font-weight") == "600")
            if anchor == "end":
                lo, hi = x - width, x
            elif anchor == "middle":
                lo, hi = x - width / 2, x + width / 2
            else:
                lo, hi = x, x + width
            self.assertGreaterEqual(lo, -1, "%r clips left" % content)
            self.assertLessEqual(hi, w + 1, "%r clips right" % content)
            y = float(attrs.get("y", 0))
            self.assertTrue(-1 <= y <= h + 1, "%r clips vertically" % content)

    def test_no_clipping_across_kinds(self):
        long_names = {"category name that runs long %d" % i: [i * 3 + 1]
                      for i in range(3)}
        cases = [
            limn.line({"d": DAYS, "Alpha": list(range(12)),
                       "Beta metrics": [i * 9 for i in range(12)]},
                      x="d", title="A title that is reasonably long"),
            limn.bar({"team": list(long_names),
                      "v": [1_200_000, 3_400_000, 2_100_000]},
                     horizontal=True, labels=True),
            limn.bar({"q": ["Q1", "Q2", "Q3"], "big": [9e6, 2e6, 5e6]},
                     labels=True),
            limn.hist([i % 37 for i in range(500)]),
            limn.heatmap({"r": ["one", "two"], "A": [1, 2], "B": [3, 4]}),
        ]
        for fig in cases:
            for theme in ("paper", "dusk"):
                self.assert_no_clipped_text(fig.theme(theme))

    def test_many_categories_thin_their_labels(self):
        fig = limn.bar({"c": ["category %02d" % i for i in range(40)],
                        "v": [i % 7 for i in range(40)]})
        self.assert_no_clipped_text(fig)


class TestOutput(unittest.TestCase):
    def test_save_writes_and_notes_once(self):
        fig = limn.line({"x": [1, 2, 3], "y": [1, None, 3]}, x="x", y="y")
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "chart")     # extension auto-added
            with contextlib.redirect_stderr(err):
                fig.save(path)
                fig.save(path)                    # second save: no re-noise
            self.assertTrue(os.path.exists(path + ".svg"))
        self.assertEqual(err.getvalue().count("gap"), 1)

    def test_repr_svg_for_notebooks(self):
        fig = limn.hist([1, 2, 3, 4])
        self.assertTrue(fig._repr_svg_().startswith("<?xml"))

    def test_fluent_chain_returns_figure(self):
        fig = limn.hist([1, 2, 3]).title("t").subtitle("s").caption("c") \
            .xlabel("x").ylabel("y").size(800, 500).theme("dusk") \
            .legend("none").note("hand-made note")
        self.assertIn("hand-made note", fig.notes)
        parse(fig)


if __name__ == "__main__":
    unittest.main()
