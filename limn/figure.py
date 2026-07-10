"""The figure: where data, scales, and marks become a measured layout.

The discipline that separates limn from set-the-margins-and-pray
rendering: **every piece of text is measured before anything is placed.**
Left margin is the width of the widest y label; the right margin is the
width of the direct series labels; x labels thin themselves out instead of
overlapping or rotating.  A limn chart cannot clip its own labels.

The layout grammar is fixed and editorial: title and subtitle flush left
at the top, legend beneath them (always shown for two or more series —
identity is never color-alone), y tick labels left of the plot with the
axis line omitted (the gridlines carry the eye), a single baseline under
the plot, caption bottom-left.  A single series gets no legend: the title
already names it.
"""

import sys
import math

from .ingest import ingest, IngestError, NUMBER, TEMPORAL, CATEGORY
from .marks import (draw_lines, draw_areas, draw_bars, draw_scatter,
                    draw_heatmap, stack_series, size_scale, _emit_bar)
from .metrics import text_width, truncate_to
from .scales import Linear, Time, Log, Band
from .svg import El, document, to_string, crisp
from .theme import get_theme
from .ticks import axis_formatter, fmt_value

MIN_PLOT = 60  # px; below this the figure is too small to be honest


class Figure:
    """One chart.  Construct via limn.line/bar/…, then chain style calls."""

    def __init__(self, kind, data, x=None, y=None, by=None, size=None,
                 title=None, **opts):
        self.kind = kind
        self.table = None if kind == "heatmap" else ingest(data)
        self._raw = data
        self._x, self._y, self._by, self._size = x, y, by, size
        self._opts = opts
        self.notes = list(self.table.notes) if self.table else []
        self._title = title
        self._subtitle = None
        self._caption = None
        self._xlabel = None
        self._ylabel = None
        self._theme = "paper"
        self._w, self._h = 720.0, 432.0
        self._legend = "auto"
        self._notes_shown = False

    # -- fluent style ------------------------------------------------------

    def title(self, text):
        self._title = text
        return self

    def subtitle(self, text):
        self._subtitle = text
        return self

    def caption(self, text):
        self._caption = text
        return self

    def xlabel(self, text):
        self._xlabel = text
        return self

    def ylabel(self, text):
        self._ylabel = text
        return self

    def size(self, width, height):
        self._w, self._h = float(width), float(height)
        return self

    def theme(self, name):
        self._theme = name
        return self

    def legend(self, mode):
        """'auto' (default), 'none', or 'legend' (suppress direct labels)."""
        self._legend = mode
        return self

    def note(self, text):
        self.notes.append(text)
        return self

    # -- output ------------------------------------------------------------

    def to_svg(self):
        return to_string(self._build())

    def save(self, path):
        if not str(path).endswith(".svg"):
            path = str(path) + ".svg"
        svg = self.to_svg()
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        if self.notes and not self._notes_shown:
            for n in self.notes:
                print("limn · %s" % n, file=sys.stderr)
            self._notes_shown = True
        return self

    def _repr_svg_(self):
        return self.to_svg()

    # -- data resolution -----------------------------------------------------

    def _col(self, key):
        return self.table.col(key)

    def _resolve_xy(self):
        """Pick x and y columns per the chart kind's conventions."""
        t = self.table
        if self._x is not None:
            xcol = self._col(self._x)
        elif self.kind == "bar":
            xcol = t.first_of_kind(CATEGORY) or t.first_of_kind(TEMPORAL) \
                or t.columns[0]
        else:
            xcol = t.first_of_kind(TEMPORAL)

        ynames = self._y if isinstance(self._y, (list, tuple)) else \
            ([self._y] if self._y is not None else None)
        if ynames is None:
            exclude = {xcol.name} if xcol is not None else set()
            numerics = [c.name for c in t.columns
                        if c.kind == NUMBER and c.name not in exclude]
            if not numerics:
                raise IngestError(
                    "no numeric column to plot — columns are: %s"
                    % ", ".join("%s (%s)" % (c.name, c.kind) for c in t.columns))
            if self.kind in ("line", "area", "bar") and self._by is None:
                ynames = numerics
            else:
                ynames = numerics[:1]
        ycols = [self._col(n) for n in ynames]

        if xcol is None and self.kind == "scatter":
            others = [c for c in t.columns
                      if c.kind == NUMBER and c.name != ycols[0].name]
            if len(ycols) == 1 and others:
                xcol = ycols[0]
                ycols = [others[0]]
        if xcol is None:
            numerics = [c for c in t.columns if c.kind == NUMBER
                        and all(c.name != y.name for y in ycols)]
            categories = [c for c in t.columns if c.kind == CATEGORY]
            if self.kind in ("line", "area") and categories:
                xcol = categories[0]
            elif self.kind == "scatter" and numerics:
                xcol = numerics[0]
            else:
                xcol = Index(len(t))
        return xcol, ycols

    def _series(self, xcol, ycols, theme):
        """Long form (by=) or wide form (several y columns) -> series list."""
        if self._by is not None:
            bycol = self._col(self._by)
            ycol = ycols[0]
            groups = []
            for i, g in enumerate(bycol.values):
                if g is not None and g not in groups:
                    groups.append(g)
            return [{
                "name": str(g),
                "color": theme.series_color(i),
                "points": [(xcol.values[j], ycol.values[j])
                           for j in range(len(ycol))
                           if bycol.values[j] == g],
            } for i, g in enumerate(groups)]
        return [{
            "name": y.name,
            "color": theme.series_color(i),
            "points": list(zip(xcol.values, y.values)),
        } for i, y in enumerate(ycols)]

    # -- build ----------------------------------------------------------------

    def _build(self):
        theme = get_theme(self._theme)
        if self.kind == "heatmap":
            return self._build_heatmap(theme)
        if self.kind == "hist":
            return self._build_common(theme, *self._prep_hist(theme))
        xcol, ycols = self._resolve_xy()
        series = self._series(xcol, ycols, theme)
        series = [s for s in series if any(v is not None for _x, v in s["points"])]
        if not series:
            raise IngestError("nothing to plot — every value is missing")
        if self.kind == "bar":
            return self._build_common(theme, *self._prep_bar(series, xcol,
                                                             ycols, theme))
        return self._build_common(theme, *self._prep_xy(series, xcol, ycols,
                                                        theme))

    # each _prep_* returns (spec, series) where spec drives the shared layout

    def _prep_xy(self, series, xcol, ycols, theme):
        stacked = self._opts.get("stack", self.kind == "area")
        ylog = self._opts.get("ylog", False)

        values = [v for s in series for _x, v in s["points"] if v is not None]
        if self.kind == "area" and stacked and len(series) > 1:
            if any(v < 0 for v in values):
                self.notes.append("stacked area needs non-negative values — "
                                  "drew overlapping areas instead")
                stacked = False
            else:
                _xs, layers = stack_series(series)
                values = [v for l in layers for v in l["upper"]]

        missing = sum(1 for s in series for x, v in s["points"]
                      if v is None and x is not None)
        if missing and self.kind == "line":
            self.notes.append("%d missing value%s shown as gap%s in the line"
                              % (missing, "s" if missing != 1 else "",
                                 "s" if missing != 1 else ""))

        if ylog:
            positive = [v for v in values if v > 0]
            dropped = len(values) - len(positive)
            if not positive:
                raise IngestError("log axis: no positive values to plot")
            if dropped:
                self.notes.append("log axis: dropped %d non-positive value%s"
                                  % (dropped, "s" if dropped != 1 else ""))
                for s in series:
                    s["points"] = [(x, v if v is not None and v > 0 else None)
                                   for x, v in s["points"]]
                values = positive
            sy = Log(min(values), max(values), self._ytarget())
        else:
            include_zero = self.kind == "area"
            pad = 0.05 if self.kind in ("line", "scatter") else 0.0
            sy = Linear(min(values), max(values), self._ytarget(),
                        include_zero=include_zero, pad_frac=pad)

        sx = self._x_scale(xcol, series)
        ycol = ycols[0]
        spec = dict(sx=sx, sy=sy, stacked=stacked, horizontal=False,
                    percent=getattr(ycol, "percent", False),
                    currency=getattr(ycol, "currency", None),
                    band_axis=None)
        return spec, series

    def _prep_bar(self, series, xcol, ycols, theme):
        stacked = self._opts.get("stack", False)
        horizontal = self._opts.get("horizontal", False)
        sort = self._opts.get("sort")
        labels = self._opts.get("labels", False)

        # bars live on a band: categories are the x values, stringified
        for s in series:
            s["points"] = [(None if x is None else _cat(x), v)
                           for x, v in s["points"]]
        order = []
        for s in series:
            for c, _v in s["points"]:
                if c is not None and c not in order:
                    order.append(c)
        if sort in ("y", "-y"):
            first = dict(series[0]["points"])
            order.sort(key=lambda c: (first.get(c) is None,
                                      first.get(c, 0.0)),
                       reverse=(sort == "-y"))
        elif sort == "x":
            order.sort()
        band = Band(order)

        if stacked and len(series) > 1:
            pos = {c: 0.0 for c in order}
            neg = {c: 0.0 for c in order}
            for s in series:
                for c, v in s["points"]:
                    if v is None or c is None:
                        continue
                    (pos if v >= 0 else neg)[c] = \
                        (pos if v >= 0 else neg)[c] + v
            values = list(pos.values()) + list(neg.values())
        else:
            values = [v for s in series for _c, v in s["points"]
                      if v is not None]
        sy = Linear(min(values), max(values),
                    self._ytarget(horizontal), include_zero=True)
        ycol = ycols[0]
        spec = dict(sx=band, sy=sy, stacked=stacked, horizontal=horizontal,
                    percent=getattr(ycol, "percent", False),
                    currency=getattr(ycol, "currency", None),
                    band_axis="y" if horizontal else "x",
                    bar_labels=labels)
        return spec, series

    def _prep_hist(self, theme):
        col = None
        for key in (self._y, self._x):
            if key is not None:
                col = self._col(key)
                break
        if col is None:
            col = self.table.first_of_kind(NUMBER)
        if col is None or col.kind != NUMBER:
            raise IngestError("hist needs a numeric column"
                              + ("" if col is None else
                                 " — %r is %s" % (col.name, col.kind)))
        values = sorted(v for v in col.values if v is not None)
        if not values:
            raise IngestError("hist: every value in %r is missing" % col.name)
        edges = _bin_edges(values, self._opts.get("bins", "auto"))
        counts = [0] * (len(edges) - 1)
        j = 0
        for v in values:
            while j < len(counts) - 1 and v >= edges[j + 1]:
                j += 1
            counts[j] += 1
        sx = Linear(edges[0], edges[-1], self._xtarget())
        sy = Linear(0, max(counts), self._ytarget(), include_zero=True)
        series = [{"name": col.name, "color": theme.series_color(0),
                   "points": []}]
        spec = dict(sx=sx, sy=sy, stacked=False, horizontal=False,
                    percent=col.percent, currency=col.currency,
                    band_axis=None, hist=(edges, counts))
        return spec, series

    def _x_scale(self, xcol, series):
        xs = [x for s in series for x, _v in s["points"] if x is not None]
        if not xs:
            raise IngestError("nothing to plot on the x axis — "
                              "column %r is all missing" % xcol.name)
        if xcol.kind == TEMPORAL:
            return Time(min(xs), max(xs), self._xtarget())
        if xcol.kind == CATEGORY:
            return Band([x for x in xcol.values if x is not None])
        pad = 0.02 if self.kind == "scatter" else 0.0
        return Linear(min(xs), max(xs), self._xtarget(), pad_frac=pad)

    def _ytarget(self, horizontal=False):
        extent = self._w if horizontal else self._h
        return max(3, min(8, int(extent / 70)))

    def _xtarget(self):
        return max(3, min(9, int(self._w / 110)))

    # -- the shared layout ------------------------------------------------------

    def _build_common(self, theme, spec, series):
        w, h = self._w, self._h
        sx, sy = spec["sx"], spec["sy"]
        # sy is always the value scale; horizontal only changes where it renders
        vfmt = axis_formatter(sy.tick_values(), percent=spec["percent"],
                              currency=spec["currency"])
        label_fmt = lambda v: fmt_value(v, spec["percent"], spec["currency"])

        # ---- measure text, derive margins
        if spec["horizontal"]:
            left_labels = [truncate_to(_cat(c), theme.size_axis, w * 0.3)
                           for c in spec["sx"].categories]
            bottom_labels = [vfmt(t) for t in sy.tick_values()]
        else:
            left_ticks = sy.tick_values()
            left_labels = [vfmt(t) for t in left_ticks]
            if isinstance(sx, Band):
                bottom_labels = [_cat(c) for c in sx.categories]
            elif isinstance(sx, Time):
                bottom_labels = sx.tick_labels()
            else:
                xfmt = axis_formatter(sx.tick_values())
                bottom_labels = [xfmt(t) for t in sx.tick_values()]

        left_w = max([text_width(l, theme.size_axis) for l in left_labels]
                     or [0.0])
        left = left_w + 14
        if self._ylabel:
            left = max(left, text_width(self._ylabel, theme.size_axis) -
                       (0 if left_labels else 0))

        top = 12.0
        if self._title:
            top += theme.size_title + 8
        if self._subtitle:
            top += theme.size_subtitle + 6
        if self._ylabel:
            top += theme.size_axis + 8

        legend_items = [(s["name"], s["color"]) for s in series] \
            if len(series) >= 2 and self._legend != "none" else []
        legend_rows = _wrap_legend(legend_items, theme, w - 28) \
            if legend_items else []
        top += len(legend_rows) * 19 + (4 if legend_rows else 6)

        bottom = 8 + theme.size_axis + 10
        if self._xlabel:
            bottom += theme.size_axis + 6
        if self._caption:
            bottom += theme.size_caption + 10

        direct = []
        right = 16.0
        if self.kind in ("line", "area") and len(series) >= 2 \
                and len(series) <= 4 and self._legend == "auto":
            widths = [text_width(s["name"], theme.size_label) for s in series]
            right = min(max(widths) + 26, 120)
        if bottom_labels:
            right = max(right, text_width(bottom_labels[-1],
                                          theme.size_axis) / 2 + 6)
        if spec.get("bar_labels") and spec["horizontal"]:
            right = max(right, 8 + max(
                text_width(label_fmt(v), theme.size_label)
                for s in series for _c, v in s["points"] if v is not None))
        if spec.get("bar_labels") and not spec["horizontal"]:
            top += theme.size_label + 4

        px0, px1 = left, w - right
        py0, py1 = top, h - bottom
        if px1 - px0 < MIN_PLOT or py1 - py0 < MIN_PLOT:
            raise ValueError("figure %gx%g is too small for its labels — "
                             "make it bigger with .size()" % (w, h))

        # ---- pixel mapping
        if spec["horizontal"]:
            band = sx
            band._bw = band.bandwidth(py0, py1)
            centers = lambda c: band.center(c, py0, py1)
            to_v = lambda v: sy.to_px(v, px0, px1)
        elif isinstance(sx, Band):
            band = sx
            band._bw = band.bandwidth(px0, px1)
            centers = lambda c: band.center(c, px0, px1)
            to_v = lambda v: sy.to_px(v, py1, py0)
        else:
            band = None
            centers = None
            to_v = lambda v: sy.to_px(v, py1, py0)
        to_x = (lambda v: sx.to_px(v, px0, px1)) if band is None else centers
        to_y = lambda v: sy.to_px(v, py1, py0)

        # ---- draw
        root = document(w, h, theme.surface)
        root.attrs["font-family"] = theme.font
        if self._title:
            root.add(El("title", [self._title]))
        g = root

        self._draw_grid(g, theme, spec, px0, px1, py0, py1)
        marks = g.add(El("g"))
        self._draw_marks(marks, theme, spec, series, band, centers, to_v,
                         to_x, to_y, label_fmt, px0, px1, py0, py1)
        self._draw_axes(g, theme, spec, vfmt, px0, px1, py0, py1)
        y_cursor = self._draw_header(g, theme, legend_rows)
        if self._ylabel:
            g.add(El("text", [self._ylabel], x=px0 - left_w - 0,
                     y=py0 - 10, font_size=theme.size_axis,
                     fill=theme.muted))
        if self.kind in ("line", "area") and 2 <= len(series) <= 4 \
                and self._legend == "auto":
            self._draw_direct_labels(g, theme, series, to_x, to_y,
                                     px1, py0, py1, spec)
        if self._xlabel:
            g.add(El("text", [self._xlabel], x=(px0 + px1) / 2,
                     y=py1 + theme.size_axis + 10 + theme.size_axis + 2,
                     text_anchor="middle", font_size=theme.size_axis,
                     fill=theme.muted))
        if self._caption:
            g.add(El("text", [self._caption], x=14, y=h - 10,
                     font_size=theme.size_caption, fill=theme.muted))
        return root

    # -- pieces --------------------------------------------------------------

    def _draw_grid(self, g, theme, spec, px0, px1, py0, py1):
        sy, sx = spec["sy"], spec["sx"]
        if spec["horizontal"]:
            for t in sy.tick_values():
                x = crisp(sy.to_px(t, px0, px1))
                color = theme.baseline if t == 0 else theme.grid
                g.add(El("line", x1=x, x2=x, y1=py0, y2=py1,
                         stroke=color, stroke_width=1))
            g.add(El("line", x1=crisp(px0), x2=crisp(px0), y1=py0, y2=py1,
                     stroke=theme.baseline, stroke_width=1))
            return
        for t in sy.tick_values():
            y = crisp(sy.to_px(t, py1, py0))
            color = theme.baseline if t == 0 else theme.grid
            g.add(El("line", x1=px0, x2=px1, y1=y, y2=y,
                     stroke=color, stroke_width=1))
        base_y = crisp(py1)
        g.add(El("line", x1=px0, x2=px1, y1=base_y, y2=base_y,
                 stroke=theme.baseline, stroke_width=1))

    def _draw_marks(self, g, theme, spec, series, band, centers, to_v,
                    to_x, to_y, label_fmt, px0, px1, py0, py1):
        if "hist" in spec:
            edges, counts = spec["hist"]
            sx, sy = spec["sx"], spec["sy"]
            zero = sy.to_px(0, py1, py0)
            for i, count in enumerate(counts):
                x_left = sx.to_px(edges[i], px0, px1)
                x_right = sx.to_px(edges[i + 1], px0, px1)
                _emit_bar(g, x_left + 1, max(x_right - x_left - 2, 1),
                          zero, sy.to_px(count, py1, py0),
                          series[0]["color"], theme, False, "top", False)
            return
        if self.kind == "bar":
            draw_bars(g, series, band, to_v, centers, theme,
                      spec["stacked"], spec["horizontal"],
                      spec.get("bar_labels", False), label_fmt, theme.ink2)
        elif self.kind == "line":
            draw_lines(g, series, to_x, to_y, theme,
                       markers=self._opts.get("markers", True))
        elif self.kind == "area":
            baseline = to_y(max(0.0, spec["sy"].lo))
            draw_areas(g, series, to_x, to_y, theme, spec["stacked"],
                       baseline)
        elif self.kind == "scatter":
            sized = self._sized_series(series)
            radius = size_scale([e for s in sized for _x, _y, e in s["points"]])
            n = sum(len(s["points"]) for s in sized)
            draw_scatter(g, sized, to_x, to_y, theme, radius, n)

    def _sized_series(self, series):
        if self._size is None:
            return [dict(s, points=[(x, y, None) for x, y in s["points"]])
                    for s in series]
        sizes = self._col(self._size).values
        # points were built row-aligned only for wide form; recompute per row
        xcol, ycols = self._resolve_xy()
        if self._by is not None:
            bycol = self._col(self._by)
            out = []
            for s in series:
                idx = [j for j in range(len(bycol))
                       if bycol.values[j] is not None
                       and str(bycol.values[j]) == s["name"]]
                out.append(dict(s, points=[
                    (xcol.values[j], ycols[0].values[j], sizes[j])
                    for j in idx]))
            return out
        return [dict(s, points=[(x, y, sz) for (x, y), sz
                                in zip(s["points"], sizes)])
                for s in series]

    def _draw_axes(self, g, theme, spec, vfmt, px0, px1, py0, py1):
        sx, sy = spec["sx"], spec["sy"]
        axis_style = dict(font_size=theme.size_axis, fill=theme.muted)
        if spec["horizontal"]:
            for c in sx.categories:
                y = sx.center(c, py0, py1)
                label = truncate_to(_cat(c), theme.size_axis, px0 - 10)
                g.add(El("text", [label], x=px0 - 8, y=y, dy="0.35em",
                         text_anchor="end", **axis_style))
            for t in sy.tick_values():
                g.add(El("text", [vfmt(t)], x=sy.to_px(t, px0, px1),
                         y=py1 + theme.size_axis + 6, text_anchor="middle",
                         style="font-variant-numeric: tabular-nums",
                         **axis_style))
            return
        for t in sy.tick_values():
            g.add(El("text", [vfmt(t)], x=px0 - 8,
                     y=sy.to_px(t, py1, py0), dy="0.35em", text_anchor="end",
                     style="font-variant-numeric: tabular-nums",
                     **axis_style))
        if isinstance(sx, Band):
            slot = sx.slot(px0, px1)
            labels = [(sx.center(c, px0, px1),
                       truncate_to(_cat(c), theme.size_axis, slot * 1.4))
                      for c in sx.categories]
        elif isinstance(sx, Time):
            labels = list(zip((sx.to_px(t, px0, px1)
                               for t in sx.tick_values()), sx.tick_labels()))
        else:
            xfmt = axis_formatter(sx.tick_values())
            labels = [(sx.to_px(t, px0, px1), xfmt(t))
                      for t in sx.tick_values()]
        labels = _thin_labels(labels, theme.size_axis)
        for x, label in labels:
            g.add(El("text", [label], x=x, y=py1 + theme.size_axis + 6,
                     text_anchor="middle", **axis_style))

    def _draw_header(self, g, theme, legend_rows):
        y = 12.0
        if self._title:
            y += theme.size_title
            g.add(El("text", [self._title], x=14, y=y, fill=theme.ink,
                     font_size=theme.size_title, font_weight="600"))
            y += 8 - theme.size_title + theme.size_title
        if self._subtitle:
            y += theme.size_subtitle - 2
            g.add(El("text", [self._subtitle], x=14, y=y, fill=theme.ink2,
                     font_size=theme.size_subtitle))
            y += 6
        for row in legend_rows:
            y += 14
            x = 14.0
            for name, color in row:
                g.add(El("rect", x=x, y=y - 9, width=10, height=10, rx=2,
                         fill=color))
                g.add(El("text", [name], x=x + 15, y=y, fill=theme.ink2,
                         font_size=theme.size_label))
                x += 15 + text_width(name, theme.size_label) + 16
            y += 5
        return y

    def _draw_direct_labels(self, g, theme, series, to_x, to_y, px1,
                            py0, py1, spec):
        ends = []
        if self.kind == "area" and spec["stacked"] and len(series) > 1:
            xs, layers = stack_series(series)
            for layer in layers:
                mid = (layer["upper"][-1] + layer["lower"][-1]) / 2
                ends.append([to_y(mid), layer["name"], layer["color"]])
        else:
            for s in series:
                last = next(((x, y) for x, y in reversed(s["points"])
                             if x is not None and y is not None), None)
                if last is None:
                    continue
                ends.append([to_y(last[1]), s["name"], s["color"]])
        if not ends:
            return
        ends.sort(key=lambda e: e[0])
        min_gap = theme.size_label + 3
        for _pass in range(2):
            for i in range(1, len(ends)):
                if ends[i][0] - ends[i - 1][0] < min_gap:
                    ends[i][0] = ends[i - 1][0] + min_gap
            overflow = ends[-1][0] - (py1 - 2)
            if overflow > 0:
                ends[-1][0] -= overflow
                for i in range(len(ends) - 2, -1, -1):
                    if ends[i + 1][0] - ends[i][0] < min_gap:
                        ends[i][0] = ends[i + 1][0] - min_gap
        max_w = 120 - 26
        for y, name, color in ends:
            y = max(py0 + 6, y)
            g.add(El("line", x1=px1 + 4, x2=px1 + 12, y1=y, y2=y,
                     stroke=color, stroke_width=2.5))
            g.add(El("text", [truncate_to(name, theme.size_label, max_w)],
                     x=px1 + 16, y=y, dy="0.35em", fill=theme.ink2,
                     font_size=theme.size_label))

    # -- heatmap (its own layout: two band axes + a ramp legend) --------------

    def _build_heatmap(self, theme):
        matrix, row_labels, col_labels = _matrix_from(self._raw, self)
        w, h = self._w, self._h
        fmt = lambda v: fmt_value(v)

        row_labels = [truncate_to(l, theme.size_axis, w * 0.25)
                      for l in row_labels]
        left = max([text_width(l, theme.size_axis) for l in row_labels]
                   or [0.0]) + 14
        top = 12.0
        if self._title:
            top += theme.size_title + 8
        if self._subtitle:
            top += theme.size_subtitle + 6
        top += 6
        bottom = 8 + theme.size_axis + 10 + (theme.size_caption + 10
                                             if self._caption else 0)
        right = 20.0
        px0, px1, py0, py1 = left, w - right, top, h - bottom
        if px1 - px0 < MIN_PLOT or py1 - py0 < MIN_PLOT:
            raise ValueError("figure %gx%g is too small for its labels — "
                             "make it bigger with .size()" % (w, h))

        root = document(w, h, theme.surface)
        root.attrs["font-family"] = theme.font
        if self._title:
            root.add(El("title", [self._title]))
        lo, hi = draw_heatmap(root, matrix, (px0, py0, px1, py1), theme, fmt)
        rows, cols = len(matrix), len(matrix[0])
        ch, cw = (py1 - py0) / rows, (px1 - px0) / cols
        for i, label in enumerate(row_labels):
            root.add(El("text", [label], x=px0 - 8, y=py0 + (i + 0.5) * ch,
                        dy="0.35em", text_anchor="end",
                        font_size=theme.size_axis, fill=theme.muted))
        col_pairs = _thin_labels(
            [(px0 + (j + 0.5) * cw,
              truncate_to(_cat(c), theme.size_axis, cw * 1.35))
             for j, c in enumerate(col_labels)], theme.size_axis)
        for x, label in col_pairs:
            root.add(El("text", [label], x=x, y=py1 + theme.size_axis + 6,
                        text_anchor="middle", font_size=theme.size_axis,
                        fill=theme.muted))
        self._draw_header(root, theme, [])
        self._draw_ramp_legend(root, theme, lo, hi, fmt, w, top)
        if self._caption:
            root.add(El("text", [self._caption], x=14, y=h - 10,
                        font_size=theme.size_caption, fill=theme.muted))
        return root

    def _draw_ramp_legend(self, root, theme, lo, hi, fmt, w, top):
        bar_w, bar_h = 96.0, 8.0
        hi_w = text_width(fmt(hi), theme.size_caption)
        x1 = w - 16 - hi_w - 5 - bar_w
        y = max(top - 22, 10)
        grad_id = "limnramp"
        defs = root.add(El("defs"))
        grad = defs.add(El("linearGradient", id=grad_id, x1=0, y1=0,
                           x2=1, y2=0))
        for i, color in enumerate(theme.ramp):
            grad.add(El("stop",
                        offset="%.3f" % (i / (len(theme.ramp) - 1)),
                        stop_color=color))
        root.add(El("rect", x=x1, y=y, width=bar_w, height=bar_h, rx=2,
                    fill="url(#%s)" % grad_id))
        root.add(El("text", [fmt(lo)], x=x1 - 5, y=y + bar_h - 1,
                    text_anchor="end", font_size=theme.size_caption,
                    fill=theme.muted))
        root.add(El("text", [fmt(hi)], x=x1 + bar_w + 5, y=y + bar_h - 1,
                    font_size=theme.size_caption, fill=theme.muted))


# -- helpers ---------------------------------------------------------------------


class Index:
    """A synthetic 0..n-1 x column for y-only data."""
    name = "index"
    kind = NUMBER
    percent = False
    currency = None

    def __init__(self, n):
        self.values = list(range(n))

    def __len__(self):
        return len(self.values)


def _cat(v):
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return str(v)


def _wrap_legend(items, theme, max_width):
    rows, row, x = [], [], 0.0
    for name, color in items:
        item_w = 15 + text_width(name, theme.size_label) + 16
        if row and x + item_w > max_width:
            rows.append(row)
            row, x = [], 0.0
        row.append((name, color))
        x += item_w
    if row:
        rows.append(row)
    return rows


def _thin_labels(labels, size):
    """Drop every other label until neighbors stop colliding."""
    stride = 1
    while stride < len(labels):
        kept = labels[::stride]
        ok = True
        for (x1, l1), (x2, l2) in zip(kept, kept[1:]):
            if (text_width(l1, size) + text_width(l2, size)) / 2 + 8 \
                    > (x2 - x1):
                ok = False
                break
        if ok:
            return kept
        stride *= 2
    return [labels[0], labels[-1]] if len(labels) > 1 else labels


def _bin_edges(sorted_values, bins):
    lo, hi = sorted_values[0], sorted_values[-1]
    if lo == hi:
        return [lo - 0.5, hi + 0.5]
    if isinstance(bins, int):
        k = max(1, min(bins, 200))
    else:
        n = len(sorted_values)
        q1 = _quantile(sorted_values, 0.25)
        q3 = _quantile(sorted_values, 0.75)
        width = 2 * (q3 - q1) / n ** (1 / 3)     # Freedman–Diaconis
        if width <= 0:
            k = max(1, math.ceil(math.log2(n)) + 1)   # Sturges fallback
        else:
            k = max(1, min(math.ceil((hi - lo) / width), 120))
    step = (hi - lo) / k
    return [lo + i * step for i in range(k)] + [hi]


def _quantile(sorted_values, q):
    pos = (len(sorted_values) - 1) * q
    i = int(pos)
    frac = pos - i
    if i + 1 >= len(sorted_values):
        return sorted_values[-1]
    return sorted_values[i] * (1 - frac) + sorted_values[i + 1] * frac


def _matrix_from(data, fig):
    """Heatmap input: a numeric matrix, or a table with a label column."""
    if isinstance(data, (list, tuple)) and data \
            and all(isinstance(r, (list, tuple)) for r in data) \
            and all(isinstance(v, (int, float)) or v is None
                    for r in data for v in r):
        matrix = [[None if v is None else float(v) for v in row]
                  for row in data]
        width = max(len(r) for r in matrix)
        matrix = [r + [None] * (width - len(r)) for r in matrix]
        rows = [str(i + 1) for i in range(len(matrix))]
        cols = [str(j + 1) for j in range(width)]
        return matrix, rows, cols
    table = ingest(data)
    fig.notes.extend(table.notes)
    label_col = table.first_of_kind(CATEGORY)
    numeric = [c for c in table.columns if c.kind == NUMBER]
    if not numeric:
        raise IngestError("heatmap needs numeric columns — got: %s"
                          % ", ".join("%s (%s)" % (c.name, c.kind)
                                      for c in table.columns))
    matrix = [[c.values[i] for c in numeric] for i in range(len(table))]
    rows = [_cat(v) if v is not None else "?" for v in label_col.values] \
        if label_col else [str(i + 1) for i in range(len(table))]
    return matrix, rows, [c.name for c in numeric]
