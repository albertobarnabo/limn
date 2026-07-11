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

import itertools
import sys
import math

from .coerce import parse_number, parse_temporal
from .ingest import ingest, IngestError, NUMBER, TEMPORAL, CATEGORY
from .marks import (draw_lines, draw_areas, draw_bars, draw_scatter,
                    draw_heatmap, draw_boxes, box_stats, stack_series,
                    size_scale, decimate, _emit_bar)
from .metrics import text_width, truncate_to
from .scales import Linear, Time, Log, Band
from .svg import El, document, to_string, crisp
from .theme import get_theme
from .ticks import axis_formatter, fmt_value, fmt_log

MIN_PLOT = 60  # px; below this the figure is too small to be honest

# SVG ids are document-global; faceted figures nest many sub-documents,
# so every id-bearing element takes a fresh one.
_uid = itertools.count(1)


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
        self._facet = opts.pop("facet", None)
        self._hlines = []
        self._vlines = []
        self._flags = []
        self._ylim_v = None
        self._xlim_v = None
        self._force = {}      # facet machinery: shared domains & orders
        self._panel = False   # True when this figure is one facet panel

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

    # -- annotations ---------------------------------------------------------

    def hline(self, y, label=None, color=None):
        """A horizontal reference line at value *y* (a target, a limit)."""
        self._hlines.append((y, label, color))
        return self

    def vline(self, x, label=None, color=None):
        """A vertical reference line at *x* — a date, number, or category
        (an event, a deadline, the moment everything changed)."""
        self._vlines.append((x, label, color))
        return self

    def flag(self, x, y, text):
        """Call out one point: a ringed dot at (x, y) with a short label."""
        self._flags.append((x, y, text))
        return self

    def ylim(self, lo, hi):
        """Fix the value-axis range (overrides the computed domain)."""
        self._ylim_v = (float(lo), float(hi))
        return self

    def xlim(self, lo, hi):
        """Fix a numeric x-axis range (overrides the computed domain)."""
        self._xlim_v = (float(lo), float(hi))
        return self

    # -- output ------------------------------------------------------------

    def to_svg(self):
        return to_string(self._build())

    def save(self, path):
        path = str(path)
        if path.endswith(".png"):
            self._save_png(path)
        else:
            if not path.endswith(".svg"):
                path += ".svg"
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.to_svg())
        if self.notes and not self._notes_shown:
            for n in self.notes:
                print("limn · %s" % n, file=sys.stderr)
            self._notes_shown = True
        return self

    def _save_png(self, path):
        """PNG is an escape hatch, not a dependency: uses cairosvg if
        (and only if) the user installed it."""
        try:
            import cairosvg
        except ImportError:
            raise RuntimeError(
                "PNG export needs the optional rasterizer: pip install "
                "cairosvg — or save as .svg, which needs nothing")
        cairosvg.svg2png(bytestring=self.to_svg().encode("utf-8"),
                         write_to=path, output_width=int(self._w * 2))

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
            groups = self._force.get("groups")
            if groups is None:
                groups = []
                for g in bycol.values:
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

    def _apply_style(self, series):
        """User overrides: color= (str, list, or {name: hex}), dash=."""
        color = self._opts.get("color")
        if isinstance(color, str):
            for s in series:
                s["color"] = color
        elif isinstance(color, dict):
            for s in series:
                if s["name"] in color:
                    s["color"] = color[s["name"]]
        elif isinstance(color, (list, tuple)):
            for s, c in zip(series, color):
                s["color"] = c
        dash = self._opts.get("dash")
        if dash:
            names = set(dash) if not isinstance(dash, str) else {dash}
            for s in series:
                if s["name"] in names:
                    s["dash"] = True

    # -- build ----------------------------------------------------------------

    def _build(self):
        theme = get_theme(self._theme)
        if self._facet:
            return self._build_facets(theme)
        if self.kind == "heatmap":
            return self._build_heatmap(theme)
        return self._build_common(theme, *self._prepare(theme))

    def _prepare(self, theme):
        """Resolve data into (spec, series) — everything but pixels."""
        if self.kind == "hist":
            return self._prep_hist(theme)
        if self.kind == "box":
            return self._prep_box(theme)
        xcol, ycols = self._resolve_xy()
        series = self._series(xcol, ycols, theme)
        self._apply_style(series)
        series = [s for s in series if any(v is not None for _x, v in s["points"])]
        if not series:
            raise IngestError("nothing to plot — every value is missing")
        if self.kind == "bar":
            return self._prep_bar(series, xcol, ycols, theme)
        return self._prep_xy(series, xcol, ycols, theme)

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
            vlo, vhi = self._y_domain(min(values), max(values))
            sy = Log(vlo, vhi, self._ytarget())
        else:
            include_zero = self.kind == "area"
            pad = 0.05 if self.kind in ("line", "scatter") else 0.0
            vlo, vhi = self._y_domain(min(values), max(values))
            if (vlo, vhi) != (min(values), max(values)):
                include_zero, pad = False, 0.0    # an explicit range is law
            sy = Linear(vlo, vhi, self._ytarget(),
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
        order = self._force.get("xcats")
        if order is None:
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
        vlo, vhi = self._y_domain(min(values), max(values))
        sy = Linear(vlo, vhi, self._ytarget(horizontal),
                    include_zero=(vlo, vhi) == (min(values), max(values)))
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
        edges = self._force.get("edges") \
            or _bin_edges(values, self._opts.get("bins", "auto"))
        counts = [0] * (len(edges) - 1)
        j = 0
        for v in values:
            if v < edges[0] or v > edges[-1]:
                continue
            while j < len(counts) - 1 and v >= edges[j + 1]:
                j += 1
            counts[j] += 1
        sx = Linear(edges[0], edges[-1], self._xtarget())
        clo, chi = self._y_domain(0, max(counts))
        sy = Linear(clo, chi, self._ytarget(), include_zero=True)
        series = [{"name": col.name, "color": theme.series_color(0),
                   "points": []}]
        spec = dict(sx=sx, sy=sy, stacked=False, horizontal=False,
                    percent=col.percent, currency=col.currency,
                    band_axis=None, hist=(edges, counts))
        return spec, series

    def _prep_box(self, theme):
        ycol = self._col(self._y) if self._y is not None \
            else self.table.first_of_kind(NUMBER)
        if ycol is None or ycol.kind != NUMBER:
            raise IngestError("box needs a numeric column"
                              + ("" if ycol is None else
                                 " — %r is %s" % (ycol.name, ycol.kind)))
        if self._x is not None:
            xcol = self._col(self._x)
        else:
            xcol = self.table.first_of_kind(CATEGORY)
        if xcol is not None:
            groups = {}
            for cat, v in zip(xcol.values, ycol.values):
                if cat is None or v is None:
                    continue
                groups.setdefault(_cat(cat), []).append(v)
        else:
            groups = {ycol.name: [v for v in ycol.values if v is not None]}
        if not any(groups.values()):
            raise IngestError("box: every value in %r is missing" % ycol.name)
        stats = [(cat, box_stats(vals)) for cat, vals in groups.items()
                 if vals]
        band = Band([c for c, _s in stats])
        all_vals = [v for vals in groups.values() for v in vals]
        vlo, vhi = self._y_domain(min(all_vals), max(all_vals))
        sy = Linear(vlo, vhi, self._ytarget(), pad_frac=0.05)
        series = [{"name": ycol.name, "color": theme.series_color(0),
                   "points": []}]
        spec = dict(sx=band, sy=sy, stacked=False, horizontal=False,
                    percent=ycol.percent, currency=ycol.currency,
                    band_axis="x", box=stats)
        return spec, series

    def _y_domain(self, lo, hi):
        """Data extent, unless the user (or the facet grid) says otherwise."""
        if "ylo" in self._force:
            return self._force["ylo"], self._force["yhi"]
        if self._ylim_v:
            return self._ylim_v
        return lo, hi

    def _x_scale(self, xcol, series):
        if self._opts.get("xlog"):
            if xcol.kind != NUMBER:
                raise IngestError("xlog needs a numeric x column — "
                                  "%r is %s" % (xcol.name, xcol.kind))
            dropped = 0
            for s in series:
                pts = []
                for x, v in s["points"]:
                    if x is not None and x <= 0:
                        dropped += 1
                        x = None
                    pts.append((x, v))
                s["points"] = pts
            if dropped:
                self.notes.append("log x axis: dropped %d non-positive "
                                  "value%s" % (dropped,
                                               "s" if dropped != 1 else ""))
        xs = [x for s in series for x, _v in s["points"] if x is not None]
        if not xs:
            raise IngestError("nothing to plot on the x axis — "
                              "column %r is all missing" % xcol.name)
        if self._opts.get("xlog"):
            lo, hi = self._force.get("xlo", min(xs)), self._force.get("xhi", max(xs))
            return Log(lo, hi, self._xtarget())
        if xcol.kind == TEMPORAL:
            lo, hi = self._force.get("xlo", min(xs)), self._force.get("xhi", max(xs))
            return Time(lo, hi, self._xtarget())
        if xcol.kind == CATEGORY:
            cats = self._force.get("xcats") \
                or [x for x in xcol.values if x is not None]
            return Band(cats)
        if "xlo" in self._force:
            return Linear(self._force["xlo"], self._force["xhi"],
                          self._xtarget())
        if self._xlim_v:
            return Linear(self._xlim_v[0], self._xlim_v[1], self._xtarget())
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
        if isinstance(sy, Log):
            vfmt = lambda v: fmt_log(v, spec["percent"], spec["currency"])
        else:
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
        clip_id = "limnclip%d" % next(_uid)
        # generous on the side where bar value labels live; the clip's job
        # is only to stop ylim'd marks from bleeding across the figure
        pad_top = 26 if spec.get("bar_labels") else 6
        pad_right = 110 if spec.get("bar_labels") and spec["horizontal"] else 1
        defs = g.add(El("defs"))
        defs.add(El("clipPath", [El("rect", x=px0 - 6, y=py0 - pad_top,
                                    width=px1 - px0 + 6 + pad_right,
                                    height=py1 - py0 + 2 * pad_top)],
                    id=clip_id))
        marks = g.add(El("g", clip_path="url(#%s)" % clip_id))
        self._draw_marks(marks, theme, spec, series, band, centers, to_v,
                         to_x, to_y, label_fmt, px0, px1, py0, py1)
        self._draw_annotations(g, theme, spec, to_x, to_y, to_v,
                               px0, px1, py0, py1)
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
        if "box" in spec:
            draw_boxes(g, spec["box"], band, to_v, centers, theme,
                       series[0]["color"])
            return
        if self.kind == "bar":
            draw_bars(g, series, band, to_v, centers, theme,
                      spec["stacked"], spec["horizontal"],
                      spec.get("bar_labels", False), label_fmt, theme.ink2)
        elif self.kind == "line":
            budget = int((px1 - px0) * 4)
            series = [dict(s, points=decimate(s["points"], to_x, budget))
                      if len(s["points"]) > budget else s for s in series]
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
            xfmt = fmt_log if isinstance(sx, Log) \
                else axis_formatter(sx.tick_values())
            labels = [(sx.to_px(t, px0, px1), xfmt(t))
                      for t in sx.tick_values()]
        labels = _thin_labels(labels, theme.size_axis)
        for x, label in labels:
            g.add(El("text", [label], x=x, y=py1 + theme.size_axis + 6,
                     text_anchor="middle", **axis_style))

    # -- annotations: reference lines and callouts ------------------------------

    def _draw_annotations(self, g, theme, spec, to_x, to_y, to_v,
                          px0, px1, py0, py1):
        for value, label, color in self._hlines:
            v = _as_number(value)
            if v is None:
                self.notes.append("hline: %r is not a number — skipped"
                                  % (value,))
                continue
            color = color or theme.ink2
            if spec["horizontal"]:      # the value axis runs horizontally
                x = to_v(v)
                if not px0 <= x <= px1:
                    self.notes.append("hline at %s is outside the value "
                                      "range — skipped" % value)
                    continue
                self._ref_vertical(g, theme, x, label, color, px0, px1,
                                   py0, py1)
            else:
                y = to_y(v)
                if not py0 <= y <= py1:
                    self.notes.append("hline at %s is outside the value "
                                      "range — skipped" % value)
                    continue
                g.add(El("line", x1=px0, x2=px1, y1=y, y2=y, stroke=color,
                         stroke_width=1, stroke_dasharray="5 4"))
                if label:
                    g.add(El("text", [label], x=px1 - 2, y=y - 5,
                             text_anchor="end", font_size=theme.size_caption,
                             fill=color))
        for value, label, color in self._vlines:
            if spec["horizontal"]:
                self.notes.append("vline on a horizontal chart has no axis "
                                  "to live on — use hline for the value")
                continue
            xv = self._annotation_x(spec["sx"], value)
            x = to_x(xv) if xv is not None else None
            if x is None or not px0 <= x <= px1:
                self.notes.append("vline at %r is outside the x range — "
                                  "skipped" % (value,))
                continue
            self._ref_vertical(g, theme, x, label, color or theme.ink2,
                               px0, px1, py0, py1)
        for xval, yval, text in self._flags:
            xv = self._annotation_x(spec["sx"], xval)
            yv = _as_number(yval)
            x = to_x(xv) if xv is not None else None
            y = to_y(yv) if yv is not None else None
            if x is None or y is None:
                self.notes.append("flag %r is outside the data space — "
                                  "skipped" % text)
                continue
            g.add(El("circle", cx=x, cy=y, r=5.5, fill="none",
                     stroke=theme.ink, stroke_width=1.5))
            g.add(El("circle", cx=x, cy=y, r=1.8, fill=theme.ink))
            w = text_width(text, theme.size_label)
            tx, anchor = x + 10, "start"
            if tx + w > px1:
                tx, anchor = x - 10, "end"
            ty = min(max(y + 4, py0 + 12), py1 - 4)
            g.add(El("text", [text], x=tx, y=ty, text_anchor=anchor,
                     font_size=theme.size_label, fill=theme.ink,
                     font_weight="600"))

    def _ref_vertical(self, g, theme, x, label, color, px0, px1, py0, py1):
        g.add(El("line", x1=x, x2=x, y1=py0, y2=py1, stroke=color,
                 stroke_width=1, stroke_dasharray="5 4"))
        if label:
            w = text_width(label, theme.size_caption)
            tx, anchor = x + 5, "start"
            if tx + w > px1:
                tx, anchor = x - 5, "end"
            g.add(El("text", [label], x=tx, y=py0 + 11, text_anchor=anchor,
                     font_size=theme.size_caption, fill=color))

    def _annotation_x(self, sx, value):
        """Coerce an annotation's x to whatever the x scale speaks."""
        if isinstance(sx, Band):
            return _cat(value)
        if isinstance(sx, Time):
            return parse_temporal(value)
        return _as_number(value)

    def _draw_header(self, g, theme, legend_rows):
        y = 12.0
        if self._title:
            size = 12.5 if self._panel else theme.size_title
            y += size
            g.add(El("text", [self._title], x=14, y=y, fill=theme.ink,
                     font_size=size, font_weight="600"))
            y += 8
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
        grad_id = "limnramp%d" % next(_uid)
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


    # -- small multiples --------------------------------------------------------

    def _build_facets(self, theme):
        """One panel per facet value, sharing scales, colors, and bins.

        Sharing is the whole point: a grid of panels with private y axes
        is a lie detector's nightmare.  Domains, category orders, series
        colors, and histogram bin edges are computed once, from all the
        data, and imposed on every panel.
        """
        if self.kind in ("heatmap", "box"):
            raise IngestError("facet isn't supported for %s charts"
                              % self.kind)
        fcol = self._col(self._facet)
        panels, row_index = [], {}
        for i, v in enumerate(fcol.values):
            if v is None:
                continue
            key = _cat(v)
            if key not in row_index:
                row_index[key] = []
                panels.append(key)
            row_index[key].append(i)
        if not panels:
            raise IngestError("facet column %r is all missing" % fcol.name)

        force = {}
        if self._by is not None:
            bycol = self._col(self._by)
            groups = []
            for g in bycol.values:
                if g is not None and g not in groups:
                    groups.append(g)
            force["groups"] = groups
        if self.kind == "hist":
            col = None
            for key in (self._y, self._x):
                if key is not None:
                    col = self._col(key)
                    break
            col = col or self.table.first_of_kind(NUMBER)
            if col is None or col.kind != NUMBER:
                raise IngestError("hist needs a numeric column to facet")
            pooled = sorted(v for v in col.values if v is not None)
            force["edges"] = _bin_edges(pooled, self._opts.get("bins", "auto"))

        children = []
        for key in panels:
            idx = row_index[key]
            data = {c.name: [c.raw[i] for i in idx]
                    for c in self.table.columns if c.name != fcol.name}
            child = Figure(self.kind, data, x=self._x, y=self._y,
                           by=self._by, size=self._size,
                           **{k: v for k, v in self._opts.items()
                              if k != "cols"})
            child.notes = []          # the parent told the story once
            child._theme = self._theme
            child._legend = "none"
            child._panel = True
            child._opts["markers"] = False   # beads read as dashes at panel size
            child._title = key
            child._hlines = self._hlines
            child._vlines = self._vlines
            child._flags = self._flags
            child._ylim_v, child._xlim_v = self._ylim_v, self._xlim_v
            child._force.update(force)
            children.append(child)

        # dry pass: union the domains every panel will be held to
        ylo = yhi = xlo = xhi = None
        xcats, legend_union = [], []
        for child in children:
            spec, series = child._prepare(theme)
            sy, sx = spec["sy"], spec["sx"]
            ylo = sy.lo if ylo is None else min(ylo, sy.lo)
            yhi = sy.hi if yhi is None else max(yhi, sy.hi)
            if isinstance(sx, Band):
                for c in sx.categories:
                    if c not in xcats:
                        xcats.append(c)
            elif not isinstance(sx, Band) and hasattr(sx, "lo"):
                xlo = sx.lo if xlo is None else min(xlo, sx.lo)
                xhi = sx.hi if xhi is None else max(xhi, sx.hi)
            for s in series:
                if all(s["name"] != n for n, _c in legend_union):
                    legend_union.append((s["name"], s["color"]))
        for child in children:
            child._force.update({"ylo": ylo, "yhi": yhi})
            if xcats:
                child._force["xcats"] = xcats
            elif xlo is not None and self.kind != "hist":
                child._force.update({"xlo": xlo, "xhi": xhi})

        # grid arithmetic
        n = len(children)
        cols = self._opts.get("cols") or (1 if n == 1 else 2 if n <= 4 else 3)
        cols = max(1, min(int(cols), n))
        rows = math.ceil(n / cols)
        w, h = self._w, self._h
        top = 12.0
        if self._title:
            top += theme.size_title + 8
        if self._subtitle:
            top += theme.size_subtitle + 6
        items = legend_union if len(legend_union) >= 2 \
            and self._legend != "none" else []
        legend_rows = _wrap_legend(items, theme, w - 28) if items else []
        top += len(legend_rows) * 19 + (4 if legend_rows else 2)
        bottom = (theme.size_caption + 14) if self._caption else 8
        gap = 12.0
        pw = (w - 20 - (cols - 1) * gap) / cols
        ph = (h - top - bottom - (rows - 1) * gap) / rows
        if pw < 160 or ph < 130:
            raise ValueError(
                "a %dx%d facet grid doesn't fit in %gx%g — make the figure "
                "bigger with .size() or reduce cols=" % (rows, cols, w, h))

        root = document(w, h, theme.surface)
        root.attrs["font-family"] = theme.font
        if self._title:
            root.add(El("title", [self._title]))
        self._draw_header(root, theme, legend_rows)
        for i, child in enumerate(children):
            child.size(pw, ph)
            panel = child._build()
            r, c = divmod(i, cols)
            panel.attrs["x"] = 10 + c * (pw + gap)
            panel.attrs["y"] = top + r * (ph + gap)
            root.add(panel)
            for note in child.notes:
                if note not in self.notes:
                    self.notes.append(note)
        if self._caption:
            root.add(El("text", [self._caption], x=14, y=h - 10,
                        font_size=theme.size_caption, fill=theme.muted))
        return root


# -- helpers ---------------------------------------------------------------------


def _as_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        parsed = parse_number(value)
        return parsed[0] if parsed else None
    return None


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
