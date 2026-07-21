"""Rendered-geometry invariants — the tests that would have caught the P0s.

The old suite checked that charts *rendered*; it never checked what they
rendered.  Every assertion here reads the finished SVG and asks a question
a reader would ask:

- can I tell the tick labels apart, and does each one name the value its
  gridline actually stands on?
- is every piece of text inside the canvas?
- do the bars come out in the order I asked for?
- does a value shown on the chart match the value in the data?

Each runs across the chart kinds and both themes.
"""

import re
import unittest
import xml.etree.ElementTree as ET

import limn
from limn.metrics import text_width
from limn.theme import THEMES
from limn.ticks import linear_ticks, axis_formatter

NS = "{http://www.w3.org/2000/svg}"


def render(fig):
    svg = fig.to_svg()
    return ET.fromstring(svg), svg


def text_nodes(root):
    """Every text element with the geometry needed to place it."""
    out = []
    for el in root.iter(NS + "text"):
        if not (el.text or "").strip():
            continue
        out.append({
            "text": el.text,
            "x": float(el.get("x", 0)),
            "y": float(el.get("y", 0)),
            "size": float(el.get("font-size", 11)),
            "anchor": el.get("text-anchor", "start"),
            "bold": el.get("font-weight") == "600",
        })
    return out


def horizontal_span(node):
    w = text_width(node["text"], node["size"], node["bold"])
    if node["anchor"] == "end":
        return node["x"] - w, node["x"]
    if node["anchor"] == "middle":
        return node["x"] - w / 2, node["x"] + w / 2
    return node["x"], node["x"] + w


def value_axis_labels(root):
    return [el.text for el in root.iter(NS + "text")
            if "tabular-nums" in (el.get("style") or "") and el.text]


# Every kind, built from data whose shape suits it.
def sample_figures():
    days = ["2026-%02d-%02d" % (1 + i // 4, 1 + (i * 3) % 27) for i in range(16)]
    return {
        "line": limn.line({"d": days, "north": [10 + i * 3 for i in range(16)],
                           "south": [40 - i for i in range(16)]}, x="d"),
        "line_small_ints": limn.line(
            [{"week": i + 1, "outages": v}
             for i, v in enumerate([1, 3, 2, 5, 4])], x="week", y="outages"),
        "area": limn.area({"d": days, "a": [5 + i for i in range(16)],
                           "b": [3 + i % 4 for i in range(16)]}, x="d"),
        "bar": limn.bar({"team": ["Alpha", "Beta", "Gamma", "Delta"],
                         "points": [1240, 980, 1530, 410]}, labels=True),
        "bar_h": limn.bar({"team": ["Customer support", "Platform"],
                           "delta": [-14.3, 12.4]},
                          horizontal=True, labels=True),
        "bar_grouped": limn.bar({"q": ["Q1", "Q2", "Q3"],
                                 "a": [3, 4, 5], "b": [2, 2, 3]}),
        "scatter": limn.scatter({"x": [1, 5, 9, 14], "y": [2, 8, 3, 11]},
                                x="x", y="y"),
        "hist": limn.hist([(i * 37) % 91 for i in range(300)]),
        "box": limn.box({"g": ["a"] * 12 + ["b"] * 12,
                         "v": list(range(12)) + list(range(6, 18))},
                        x="g", y="v"),
        "heatmap": limn.heatmap({"row": ["north", "south"],
                                 "Jan": [4, 8], "Feb": [6, 9]}),
        "facets": limn.line([{"m": i, "v": i * k, "p": "P%d" % k}
                             for k in (1, 2) for i in range(8)],
                            x="m", y="v", facet="p").size(760, 520),
    }


class TestTickLabelsAreReadable(unittest.TestCase):
    """The P0 that shipped: '0 · 2 · 2 · 4 · 4 · 6' on gridlines at .5"""

    def test_labels_are_distinct_on_every_kind_and_theme(self):
        for name, fig in sample_figures().items():
            for theme in THEMES:
                with self.subTest(kind=name, theme=theme):
                    root, _ = render(fig.theme(theme))
                    # Facet panels are nested <svg>s that deliberately repeat
                    # one shared axis, so distinctness is a per-panel claim.
                    panels = root.findall(NS + "svg") or [root]
                    for panel in panels:
                        labels = value_axis_labels(panel)
                        self.assertEqual(len(labels), len(set(labels)),
                                         "duplicate axis labels: %r" % labels)

    def test_labels_name_the_value_their_gridline_stands_on(self):
        domains = [(0, 100), (1, 5), (0, 12500), (41000, 52000), (0, 1),
                   (0.001, 0.008), (-50, 50), (0, 1.5e6), (3, 19), (98, 102)]
        for lo, hi in domains:
            with self.subTest(domain=(lo, hi)):
                ticks = linear_ticks(lo, hi)
                fmt = axis_formatter(ticks)
                step = min(abs(b - a) for a, b in zip(ticks, ticks[1:]))
                for t in ticks:
                    shown = float(fmt(t).replace(",", "")
                                  .replace("k", "e3").replace("M", "e6"))
                    self.assertLessEqual(
                        abs(shown - t), step * 0.02,
                        "tick at %g is labelled %r" % (t, fmt(t)))


class TestNothingLeavesTheCanvas(unittest.TestCase):
    """'A limn chart cannot clip its own labels' — asserted, not asserted-to."""

    def assert_inside(self, fig, label):
        root, _ = render(fig)
        w = float(root.get("width"))
        h = float(root.get("height"))
        for node in text_nodes(root):
            lo, hi = horizontal_span(node)
            self.assertGreaterEqual(lo, -1.5, "%s: %r off the left edge"
                                    % (label, node["text"]))
            self.assertLessEqual(hi, w + 1.5, "%s: %r off the right edge"
                                 % (label, node["text"]))
            self.assertTrue(-1 <= node["y"] <= h + 1,
                            "%s: %r off the top/bottom" % (label, node["text"]))

    def test_every_kind_and_theme(self):
        for name, fig in sample_figures().items():
            for theme in THEMES:
                with self.subTest(kind=name, theme=theme):
                    self.assert_inside(fig.theme(theme), "%s/%s" % (name, theme))

    def test_hostile_text(self):
        long_title = ("A very descriptive title about quarterly revenue "
                      "developments across every operating segment and "
                      "region in the current fiscal year")
        cases = [
            limn.hist([1, 2, 3, 4, 5]).title(long_title),
            limn.hist([1, 2, 3, 4, 5]).caption("source: " + "long " * 60),
            limn.hist([1, 2, 3, 4, 5]).subtitle("sub " * 80),
            limn.bar({"c": ["a name that is really quite long indeed %d" % i
                            for i in range(6)],
                      "v": [1, 2, 3, 4, 5, 6]}, horizontal=True, labels=True),
            limn.bar({"c": ["x%d" % i for i in range(80)],
                      "v": [i % 9 + 1 for i in range(80)]}),
            limn.line({"x": [1, 2, 3],
                       "an extremely long series name here": [1, 2, 3],
                       "another extremely long series name": [3, 2, 1]},
                      x="x"),
            limn.bar({"c": ["a", "b"], "v": [1_500_000_000, 2_000_000_000]},
                     labels=True),
            limn.bar({"c": ["a", "b"], "v": [3, 4]})
            .ylabel("Revenue in millions of United States dollars")
            .xlabel("The quarter of the fiscal year being reported"),
        ]
        for i, fig in enumerate(cases):
            for theme in THEMES:
                with self.subTest(case=i, theme=theme):
                    self.assert_inside(fig.theme(theme), "case %d" % i)


class TestBarsObeyTheirOrder(unittest.TestCase):
    """sort='-y' returned visibly ascending bars for grouped/stacked charts."""

    ROWS = [{"m": "Jan", "r": "N", "s": 1}, {"m": "Feb", "r": "N", "s": 2},
            {"m": "Mar", "r": "N", "s": 3}, {"m": "Jan", "r": "S", "s": 300},
            {"m": "Feb", "r": "S", "s": 200}, {"m": "Mar", "r": "S", "s": 100}]

    def rendered_order(self, fig):
        """Category labels, left to right as a reader meets them."""
        root, _ = render(fig)
        cats = [(n["x"], n["text"]) for n in text_nodes(root)
                if n["anchor"] == "middle" and n["text"] in
                ("Jan", "Feb", "Mar", "1", "2", "9", "10", "20")]
        return [t for _x, t in sorted(cats)]

    def test_descending_totals_are_descending(self):
        for stack in (True, False):
            with self.subTest(stack=stack):
                fig = limn.bar(self.ROWS, x="m", y="s", by="r", sort="-y",
                               stack=stack)
                self.assertEqual(self.rendered_order(fig),
                                 ["Jan", "Feb", "Mar"])

    def test_ascending_totals_are_ascending(self):
        fig = limn.bar(self.ROWS, x="m", y="s", by="r", sort="y", stack=True)
        self.assertEqual(self.rendered_order(fig), ["Mar", "Feb", "Jan"])

    def test_numeric_categories_sort_as_numbers(self):
        fig = limn.bar([{"b": b, "n": 1} for b in (1, 2, 10, 20, 9)],
                       x="b", y="n", sort="x")
        self.assertEqual(self.rendered_order(fig), ["1", "2", "9", "10", "20"])


class TestShownValuesMatchTheData(unittest.TestCase):
    def test_bar_labels_are_the_real_numbers(self):
        data = {"team": ["a", "b", "c"], "v": [1240, 980, 1530]}
        root, _ = render(limn.bar(data, labels=True))
        shown = {n["text"] for n in text_nodes(root)}
        for want in ("1,240", "980", "1,530"):
            self.assertIn(want, shown)

    def test_stacked_label_is_the_net_not_the_positive_part(self):
        root, _ = render(limn.bar({"c": ["a"], "up": [10], "down": [-5]},
                                  stack=True, labels=True))
        shown = {n["text"] for n in text_nodes(root)}
        self.assertIn("5", shown)
        self.assertNotIn("10", shown)

    def test_percent_and_currency_units_survive_to_the_axis(self):
        root, _ = render(limn.bar({"c": ["a", "b"], "v": ["45%", "30%"]}))
        self.assertTrue(any("%" in l for l in value_axis_labels(root)))
        root, _ = render(limn.bar({"c": ["a", "b"],
                                   "v": ["$1,200", "$3,400"]}))
        self.assertTrue(any("$" in l for l in value_axis_labels(root)))


class TestExtremeDomains(unittest.TestCase):
    """Astronomical and microscopic ranges must render, not explode."""

    def test_wide_domains_render_with_readable_labels(self):
        for lo, hi in [(0, 2e160), (1e-300, 1e300), (0, 1e18),
                       (-1e200, 1e200), (1e-9, 5e-9)]:
            with self.subTest(domain=(lo, hi)):
                fig = limn.line({"x": [1, 2, 3],
                                 "y": [lo, (lo + hi) / 2, hi]}, x="x", y="y")
                root, _ = render(fig)
                for label in value_axis_labels(root):
                    self.assertLessEqual(len(label), 12,
                                         "unreadable axis label %r" % label)

    def test_non_finite_values_do_not_crash(self):
        for bad in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(value=bad):
                render(limn.line({"x": [1, 2, 3], "y": [1.0, bad, 3.0]},
                                 x="x", y="y"))


class TestBarLabelsSurviveTheClip(unittest.TestCase):
    """A value label outside the plot rect must not be sliced by the clip
    that keeps out-of-range *marks* in check."""

    def test_negative_horizontal_labels_are_whole(self):
        fig = limn.bar([{"team": "Customer support", "delta": -14.3},
                        {"team": "Platform", "delta": 12.4}],
                       x="team", y="delta", horizontal=True,
                       labels=True).size(880, 520)
        _root, svg = render(fig)
        m = re.search(r'<clipPath[^>]*><rect x="([-\d.]+)"[^>]*'
                      r'width="([\d.]+)"', svg)
        cx, cw = float(m.group(1)), float(m.group(2))
        for node in text_nodes(ET.fromstring(svg)):
            if not re.fullmatch(r"-?[\d,.]+", node["text"]):
                continue
            lo, hi = horizontal_span(node)
            if node["anchor"] == "end" and lo < cx and hi < cx:
                continue           # a category label, legitimately outside
            self.assertGreaterEqual(lo, cx - 0.5,
                                    "%r is sliced by the clip" % node["text"])


class TestMarksStayInThePlot(unittest.TestCase):
    def test_clipped_charts_declare_a_clip_path(self):
        fig = limn.line({"x": [1, 2, 3], "y": [5, 5000, 5]},
                        x="x", y="y").ylim(0, 10)
        _root, svg = render(fig)
        self.assertIn("clip-path", svg)

    def test_no_nan_or_none_reaches_the_svg(self):
        for name, fig in sample_figures().items():
            for theme in THEMES:
                with self.subTest(kind=name, theme=theme):
                    _root, svg = render(fig.theme(theme))
                    self.assertNotIn("nan", svg.lower())
                    self.assertNotIn("None", svg)
                    self.assertNotIn("inf", re.sub(r"font-[a-z]+", "",
                                                   svg.lower()))


if __name__ == "__main__":
    unittest.main()
