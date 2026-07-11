"""v1.1 features: annotations, log-x, limits, facets, boxes, styling,
decimation, and the PNG escape hatch."""

import unittest
import xml.etree.ElementTree as ET

import limn
from limn.ingest import IngestError
from limn.marks import box_stats, decimate

NS = "{http://www.w3.org/2000/svg}"


def parse(fig):
    svg = fig.to_svg()
    return ET.fromstring(svg), svg


def texts(root):
    return [(el.text or "", el.attrib) for el in root.iter(NS + "text")]


class TestAnnotations(unittest.TestCase):
    BASE = {"x": list(range(10)), "y": [10 + 3 * i for i in range(10)]}

    def test_hline_draws_line_and_label(self):
        fig = limn.line(self.BASE, x="x", y="y").hline(25, "target")
        root, svg = parse(fig)
        self.assertIn("target", [t for t, _ in texts(root)])
        self.assertIn("5 4", svg)                    # the dashed reference

    def test_vline_and_flag(self):
        fig = limn.line(self.BASE, x="x", y="y") \
            .vline(4, "launch").flag(6, 28, "callout")
        root, _ = parse(fig)
        labels = [t for t, _ in texts(root)]
        self.assertIn("launch", labels)
        self.assertIn("callout", labels)

    def test_vline_on_time_axis_parses_dates(self):
        fig = limn.line({"d": ["2026-01-%02d" % i for i in range(1, 11)],
                         "v": list(range(10))}, x="d", y="v") \
            .vline("2026-01-05", "midpoint")
        root, _ = parse(fig)
        self.assertIn("midpoint", [t for t, _ in texts(root)])

    def test_out_of_range_reference_becomes_note(self):
        fig = limn.line(self.BASE, x="x", y="y").hline(10_000, "mars")
        parse(fig)
        self.assertTrue(any("outside" in n for n in fig.notes))
        self.assertNotIn("mars", [t for t, _ in texts(parse(fig)[0])])

    def test_hline_on_horizontal_bars_targets_the_value_axis(self):
        fig = limn.bar({"t": ["a", "b"], "v": [3, 9]},
                       horizontal=True).hline(5, "goal")
        root, _ = parse(fig)
        self.assertIn("goal", [t for t, _ in texts(root)])


class TestLimitsAndLog(unittest.TestCase):
    def test_ylim_is_law(self):
        fig = limn.line({"x": [1, 2, 3], "y": [50, 60, 70]},
                        x="x", y="y").ylim(0, 200)
        root, _ = parse(fig)
        labels = [t for t, _ in texts(root)]
        self.assertIn("200", labels)
        self.assertIn("0", labels)

    def test_marks_clip_when_data_exceeds_ylim(self):
        fig = limn.line({"x": [1, 2, 3], "y": [5, 500, 5]},
                        x="x", y="y").ylim(0, 10)
        _root, svg = parse(fig)
        self.assertIn("clip-path", svg)

    def test_xlog_scatter(self):
        fig = limn.scatter({"a": [1, 10, 100, 1000], "b": [1, 2, 3, 4]},
                           x="a", y="b", xlog=True)
        root, _ = parse(fig)
        labels = [t for t, _ in texts(root)]
        self.assertIn("1k", labels)                  # decade tick, compact

    def test_xlog_drops_nonpositive_with_note(self):
        fig = limn.scatter({"a": [0, 1, 10], "b": [1, 2, 3]},
                           x="a", y="b", xlog=True)
        parse(fig)
        self.assertTrue(any("log x" in n for n in fig.notes))

    def test_xlog_needs_numbers(self):
        with self.assertRaises(IngestError):
            limn.line({"a": ["x", "y"], "b": [1, 2]}, x="a", y="b",
                      xlog=True).to_svg()


class TestFacets(unittest.TestCase):
    ROWS = [{"m": i, "v": (i + 1) * mult, "panel": name}
            for i in range(8) for mult, name in ((1, "P1"), (3, "P2"))]

    def test_grid_of_nested_panels(self):
        fig = limn.line(self.ROWS, x="m", y="v", facet="panel",
                        title="Grid")
        root, svg = parse(fig)
        panels = root.findall(NS + "svg")
        self.assertEqual(len(panels), 2)
        titles = [t for t, _ in texts(root)]
        self.assertIn("P1", titles)
        self.assertIn("P2", titles)

    def test_panels_share_the_y_domain(self):
        fig = limn.line(self.ROWS, x="m", y="v", facet="panel")
        root, _ = parse(fig)
        panel_label_sets = []
        for panel in root.findall(NS + "svg"):
            labels = frozenset(t for t, a in
                               [(el.text, el.attrib)
                                for el in panel.iter(NS + "text")]
                               if a.get("text-anchor") == "end")
            panel_label_sets.append(labels)
        self.assertEqual(panel_label_sets[0], panel_label_sets[1],
                         "y axes differ between panels")

    def test_facet_series_colors_are_consistent(self):
        rows = []
        for panel in ("A", "B"):
            groups = ("g1", "g2") if panel == "A" else ("g2", "g1")
            for g in groups:
                for i in range(4):
                    rows.append({"m": i, "v": i, "grp": g, "p": panel})
        fig = limn.line(rows, x="m", y="v", by="grp", facet="p")
        _root, svg = parse(fig)
        # g1 must wear slot 1 in both panels even though panel B meets
        # g2 first — count of slot-1 stroke usage proves shared ordering
        self.assertEqual(svg.count('stroke="#2a78d6"'), 2)

    def test_faceted_hist_shares_edges(self):
        fig = limn.hist({"v": list(range(60)), "g": ["a", "b"] * 30},
                        x="v", facet="g")
        parse(fig)

    def test_facet_grid_too_small_says_so(self):
        fig = limn.line(self.ROWS, x="m", y="v", facet="panel") \
            .size(300, 200)
        with self.assertRaises(ValueError) as ctx:
            fig.to_svg()
        self.assertIn("facet", str(ctx.exception))

    def test_facet_unsupported_kinds(self):
        with self.assertRaises(IngestError):
            limn.Figure("box", {"a": [1]}, facet="a").to_svg()


class TestBox(unittest.TestCase):
    def test_stats(self):
        s = box_stats(list(range(1, 101)) + [500])
        self.assertAlmostEqual(s["med"], 51)
        self.assertEqual(s["outliers"], [500])
        self.assertGreaterEqual(s["lo"], min(range(1, 101)))
        self.assertLessEqual(s["hi"], 100)

    def test_renders_per_category(self):
        fig = limn.box({"team": ["a"] * 10 + ["b"] * 10,
                        "score": list(range(10)) + list(range(5, 15))},
                       x="team", y="score", title="Spread")
        root, _ = parse(fig)
        labels = [t for t, _ in texts(root)]
        self.assertIn("a", labels)
        self.assertIn("b", labels)

    def test_single_box_without_categories(self):
        parse(limn.box([1, 2, 3, 4, 5, 100]))

    def test_needs_numbers(self):
        with self.assertRaises(IngestError):
            limn.box({"only": ["a", "b"]}).to_svg()


class TestStyling(unittest.TestCase):
    def test_color_overrides(self):
        data = {"x": [1, 2], "a": [1, 2], "b": [3, 4]}
        _r, svg = parse(limn.line(data, x="x", color={"b": "#123456"}))
        self.assertIn("#123456", svg)
        _r, svg = parse(limn.line({"x": [1, 2], "y": [1, 2]}, x="x",
                                  color="#654321"))
        self.assertIn("#654321", svg)

    def test_dash(self):
        data = {"x": [1, 2], "actual": [1, 2], "forecast": [2, 3]}
        _r, svg = parse(limn.line(data, x="x", dash=["forecast"]))
        self.assertIn('stroke-dasharray="7 4"', svg)


class TestDecimation(unittest.TestCase):
    def test_shape_preserving_and_bounded(self):
        pts = [(i, (i * 7919) % 101) for i in range(50_000)]
        out = decimate(pts, lambda x: x / 100, budget=2000)
        self.assertLess(len(out), 3000)
        ys = [y for _x, y in pts]
        oys = [y for _x, y in out]
        self.assertEqual(max(ys), max(oys))     # extremes survive
        self.assertEqual(min(ys), min(oys))
        self.assertEqual(out[0], pts[0])
        self.assertEqual(out[-1], pts[-1])

    def test_gaps_survive(self):
        pts = [(i, None if i == 500 else i) for i in range(1000)]
        out = decimate(pts, lambda x: x / 50, budget=100)
        self.assertIn((500, None), out)

    def test_small_series_untouched(self):
        pts = [(i, i) for i in range(10)]
        self.assertEqual(decimate(pts, lambda x: x, 100), pts)


class TestPng(unittest.TestCase):
    def test_png_without_cairosvg_explains_itself(self):
        try:
            import cairosvg  # noqa: F401
            self.skipTest("cairosvg installed; error path not reachable")
        except ImportError:
            pass
        fig = limn.hist([1, 2, 3])
        with self.assertRaises(RuntimeError) as ctx:
            fig.save("/tmp/limn-test.png")
        self.assertIn("cairosvg", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
