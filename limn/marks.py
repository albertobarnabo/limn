"""Mark geometry: data made visible, one shape family per chart kind.

The specs are deliberate and fixed (they come from a validated design
system, see theme.py): 2px lines with round joins, markers with a 2px
surface ring so they survive crossings, area washes at 12% opacity,
bars capped at 24px with the data end rounded and the baseline end
square, and a 2px *surface gap* — never a stroke — separating stacked
segments and grouped neighbors.  Nothing here measures text or decides
layout; figure.py owns that.
"""

import math

from .svg import El, polyline_path, area_path, rounded_bar
from .theme import ramp_color
from .metrics import text_width


def _luminance(hex_color):
    r, g, b = (int(hex_color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
           for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ink(fill, theme):
    """Ink or white for text sitting *inside* a colored fill."""
    return "#ffffff" if _luminance(fill) < 0.45 else theme.ink


# -- lines ---------------------------------------------------------------------


def draw_lines(g, series, to_x, to_y, theme, markers):
    for s in series:
        pts = [None if x is None or y is None else (to_x(x), to_y(y))
               for x, y in s["points"]]
        drawable = [p for p in pts if p is not None]
        if not drawable:
            continue
        if len(drawable) == 1:
            x, y = drawable[0]
            g.add(El("circle", cx=x, cy=y, r=theme.marker_radius,
                     fill=s["color"], stroke=theme.surface, stroke_width=2))
            continue
        g.add(El("path", d=polyline_path(pts), fill="none",
                 stroke=s["color"], stroke_width=theme.line_width,
                 stroke_dasharray=s.get("dash") or None,
                 stroke_linejoin="round", stroke_linecap="round"))
        if markers and len(drawable) <= 30:
            for x, y in drawable:
                g.add(El("circle", cx=x, cy=y, r=theme.marker_radius - 0.5,
                         fill=s["color"], stroke=theme.surface,
                         stroke_width=2))


def decimate(points, to_x, budget):
    """Min-max decimation: shrink a huge series to what pixels can show.

    Points are bucketed by rounded x pixel; each bucket keeps its first,
    lowest, highest, and last point, in x order — the rendered path is
    visually identical to the full one.  Gaps (None) survive untouched.
    """
    if len(points) <= budget:
        return points
    out, bucket, key = [], [], None

    def flush():
        if not bucket:
            return
        keep = {0, len(bucket) - 1,
                min(range(len(bucket)), key=lambda i: bucket[i][1]),
                max(range(len(bucket)), key=lambda i: bucket[i][1])}
        out.extend(bucket[i] for i in sorted(keep))

    for p in points:
        x, y = p
        if x is None or y is None:
            flush()
            bucket, key = [], None
            out.append(p)                      # the gap itself survives
            continue
        k = int(to_x(x))
        if k != key:
            flush()
            bucket, key = [], k
        bucket.append(p)
    flush()
    return out


# -- areas ---------------------------------------------------------------------


def stack_series(series):
    """Shared-x cumulative stacking.  Missing contributes 0 (figure notes it).

    Returns (xs, [series with 'lower'/'upper' lists aligned to xs]).
    """
    xs = []
    for s in series:
        for x, _y in s["points"]:
            if x is not None and x not in xs:
                xs.append(x)
    try:
        xs.sort()
    except TypeError:
        pass  # categories keep appearance order
    base = [0.0] * len(xs)
    stacked = []
    for s in series:
        lookup = {x: (y or 0.0) for x, y in s["points"] if x is not None}
        lower = list(base)
        upper = [lo + lookup.get(x, 0.0) for lo, x in zip(lower, xs)]
        stacked.append(dict(s, lower=lower, upper=upper))
        base = upper
    return xs, stacked


def draw_areas(g, series, to_x, to_y, theme, stacked, baseline_px):
    if stacked and len(series) > 1:
        xs, layers = stack_series(series)
        pxs = [to_x(x) for x in xs]
        for layer in layers:
            top = list(zip(pxs, [to_y(v) for v in layer["upper"]]))
            bottom = list(zip(pxs, [to_y(v) for v in layer["lower"]]))
            g.add(El("path", d=area_path(top, bottom), fill=layer["color"]))
            # the surface gap between stacked fills
            g.add(El("path", d=polyline_path(top), fill="none",
                     stroke=theme.surface, stroke_width=2))
        return
    for s in series:
        pts = [(to_x(x), to_y(y)) for x, y in s["points"]
               if x is not None and y is not None]
        if len(pts) < 2:
            continue
        bottom = [(pts[0][0], baseline_px), (pts[-1][0], baseline_px)]
        g.add(El("path", d=area_path(pts, bottom), fill=s["color"],
                 fill_opacity=theme.area_opacity))
        g.add(El("path", d=polyline_path(pts), fill="none",
                 stroke=s["color"], stroke_width=theme.line_width,
                 stroke_linejoin="round", stroke_linecap="round"))


# -- bars ----------------------------------------------------------------------

_GAP = 2.0  # the surface gap, everywhere


def bar_geometry(n_series, bandwidth, bar_max):
    """Widths and offsets for n bars sharing one category slot."""
    if n_series == 1:
        w = min(bar_max, bandwidth)
        return w, [-w / 2]
    w = min(bar_max, (bandwidth - (n_series - 1) * _GAP) / n_series)
    w = max(w, 1.0)
    total = n_series * w + (n_series - 1) * _GAP
    left = -total / 2
    return w, [left + i * (w + _GAP) for i in range(n_series)]


def draw_bars(g, series, band, to_v, centers, theme, stacked, horizontal,
              labels, fmt, ink):
    """Bars for every category of every series.

    *to_v* maps a value to pixels on the value axis; *centers* maps a
    category to its slot center on the band axis.  Stacked mode shaves the
    surface gap off the inner end of every non-first segment.
    """
    zero_px = to_v(0.0)
    side_pos = "right" if horizontal else "top"
    side_neg = "left" if horizontal else "bottom"

    if stacked and len(series) > 1:
        cats = band.categories
        w = min(theme.bar_max, band._bw)
        pos_base = {c: 0.0 for c in cats}
        neg_base = {c: 0.0 for c in cats}
        tops, bottoms = {}, {}
        for s in series:
            values = {c: v for c, v in s["points"]}
            for c in cats:
                v = values.get(c)
                if v is None:
                    continue
                base = pos_base if v >= 0 else neg_base
                start_px, end_px = to_v(base[c]), to_v(base[c] + v)
                first = base[c] == 0.0
                _emit_bar(g, centers(c) - w / 2, w, start_px, end_px,
                          s["color"], theme, horizontal,
                          side_pos if v >= 0 else side_neg,
                          shave=not first)
                base[c] += v
                tops[c] = to_v(pos_base[c])
                bottoms[c] = to_v(neg_base[c])
        if labels:
            requests = []
            for c in cats:
                # The honest total of +10 and -5 is 5, not 10: label the net
                # and hang it off whichever end the net actually reaches.
                net = pos_base[c] + neg_base[c]
                anchor = tops.get(c, zero_px) if net >= 0 \
                    else bottoms.get(c, zero_px)
                requests.append((centers(c), anchor, w, net))
            return _place_bar_labels(g, requests, fmt, theme, horizontal, ink)
        return 0

    requests = []
    w, offsets = bar_geometry(len(series), band._bw, theme.bar_max)
    for s, off in zip(series, offsets):
        for c, v in s["points"]:
            if v is None or c is None:
                continue
            end_px = to_v(v)
            pos = centers(c) + off
            _emit_bar(g, pos, w, zero_px, end_px, s["color"], theme,
                      horizontal, side_pos if v >= 0 else side_neg,
                      shave=False)
            if labels:
                requests.append((pos + w / 2, end_px, w, v))
    if labels:
        return _place_bar_labels(g, requests, fmt, theme, horizontal, ink)
    return 0


def _place_bar_labels(g, requests, fmt, theme, horizontal, ink):
    """Draw value labels, skipping any that would collide.

    Grouped bars put neighbouring labels a bar-width apart, which is often
    narrower than the numbers themselves; overlapping text reads as one
    run-on number, which is worse than no label.  Returns how many were
    dropped so the figure can say so.
    """
    placed, dropped = [], 0
    for band_center, end_px, w, value in requests:
        text = fmt(value)
        tw = text_width(text, theme.size_label)
        if horizontal:
            x = end_px + 5 if value >= 0 else end_px - 5 - tw
            box = (x, band_center - theme.size_label / 2,
                   x + tw, band_center + theme.size_label / 2)
        else:
            y = end_px - 6 if value >= 0 else end_px + 6 + theme.size_label
            box = (band_center - tw / 2, y - theme.size_label,
                   band_center + tw / 2, y)
        if any(_overlaps(box, other) for other in placed):
            dropped += 1
            continue
        placed.append(box)
        _bar_label(g, band_center, end_px, w, value, fmt, theme, horizontal,
                   positive=value >= 0, ink=ink)
    return dropped


def _overlaps(a, b, pad=2.0):
    return not (a[2] + pad <= b[0] or b[2] + pad <= a[0]
                or a[3] + pad <= b[1] or b[3] + pad <= a[1])


def _emit_bar(g, band_pos, w, start_px, end_px, color, theme, horizontal,
              side, shave):
    lo, hi = min(start_px, end_px), max(start_px, end_px)
    if shave:
        if side in ("top", "right"):
            if side == "top":
                hi -= _GAP     # y grows downward: inner end is the bottom
            else:
                lo += _GAP
        else:
            if side == "bottom":
                lo += _GAP
            else:
                hi -= _GAP
    if hi - lo < 0.1:
        return
    if horizontal:
        d = rounded_bar(lo, band_pos, hi - lo, w, theme.bar_round, side)
    else:
        d = rounded_bar(band_pos, lo, w, hi - lo, theme.bar_round, side)
    g.add(El("path", d=d, fill=color))


def _bar_label(g, band_center, end_px, w, value, fmt, theme, horizontal,
               positive, ink):
    text = fmt(value)
    if horizontal:
        x = end_px + 5 if positive else end_px - 5
        anchor = "start" if positive else "end"
        g.add(El("text", [text], x=x, y=band_center, dy="0.35em",
                 font_size=theme.size_label, fill=ink,
                 text_anchor=anchor))
    else:
        y = end_px - 6 if positive else end_px + 6 + theme.size_label * 0.7
        g.add(El("text", [text], x=band_center, y=y,
                 font_size=theme.size_label, fill=ink,
                 text_anchor="middle"))


# -- scatter ---------------------------------------------------------------------


def size_scale(values, rmin=3.0, rmax=11.0):
    present = [v for v in values if v is not None and v >= 0]
    if not present:
        return lambda v: rmin + 1.5
    lo, hi = min(present), max(present)
    if hi == lo:
        return lambda v: (rmin + rmax) / 2
    return lambda v: rmin + (rmax - rmin) * math.sqrt((v - lo) / (hi - lo)) \
        if v is not None else rmin


def draw_scatter(g, series, to_x, to_y, theme, radius_of, n_total):
    opacity = 0.9 if n_total <= 50 else (0.75 if n_total <= 500 else 0.55)
    for s in series:
        for x, y, extra in s["points"]:
            if x is None or y is None:
                continue
            g.add(El("circle", cx=to_x(x), cy=to_y(y), r=radius_of(extra),
                     fill=s["color"], fill_opacity=opacity,
                     stroke=theme.surface, stroke_width=2))


# -- box plots -------------------------------------------------------------------


def box_stats(values):
    """Five-number summary with Tukey whiskers (1.5·IQR) and outliers."""
    vals = sorted(values)

    def q(p):
        pos = (len(vals) - 1) * p
        i, frac = int(pos), pos - int(pos)
        if i + 1 >= len(vals):
            return vals[-1]
        return vals[i] * (1 - frac) + vals[i + 1] * frac

    q1, med, q3 = q(0.25), q(0.5), q(0.75)
    iqr = q3 - q1
    lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    inside = [v for v in vals if lo_fence <= v <= hi_fence]
    lo_wh = inside[0] if inside else q1
    hi_wh = inside[-1] if inside else q3
    outliers = [v for v in vals if v < lo_fence or v > hi_fence]
    return {"q1": q1, "med": med, "q3": q3,
            "lo": lo_wh, "hi": hi_wh, "outliers": outliers}


def draw_boxes(g, stats, band, to_v, centers, theme, color):
    """One box per category: quartile box, median, whiskers, outlier dots."""
    w = min(38.0, band._bw)
    for cat, s in stats:
        cx = centers(cat)
        x = cx - w / 2
        top, bottom = to_v(s["q3"]), to_v(s["q1"])
        g.add(El("rect", x=x, y=min(top, bottom), width=w,
                 height=max(abs(bottom - top), 1), rx=2,
                 fill=color, fill_opacity=0.18,
                 stroke=color, stroke_width=1.5))
        med_y = to_v(s["med"])
        g.add(El("line", x1=x, x2=x + w, y1=med_y, y2=med_y,
                 stroke=color, stroke_width=2.5))
        for value, box_edge in ((s["hi"], min(top, bottom)),
                                (s["lo"], max(top, bottom))):
            wy = to_v(value)
            g.add(El("line", x1=cx, x2=cx, y1=box_edge, y2=wy,
                     stroke=color, stroke_width=1.5))
            g.add(El("line", x1=cx - 5, x2=cx + 5, y1=wy, y2=wy,
                     stroke=color, stroke_width=1.5))
        for v in s["outliers"]:
            g.add(El("circle", cx=cx, cy=to_v(v), r=2.5, fill=color,
                     fill_opacity=0.6))


# -- heatmap ---------------------------------------------------------------------


def draw_heatmap(g, matrix, rect, theme, fmt):
    """Cells with surface gaps; values annotated when they fit."""
    px0, py0, px1, py1 = rect
    rows, cols = len(matrix), len(matrix[0])
    cw, ch = (px1 - px0) / cols, (py1 - py0) / rows
    flat = [v for row in matrix for v in row if v is not None]
    lo, hi = (min(flat), max(flat)) if flat else (0.0, 1.0)
    span = (hi - lo) or 1.0
    annotate = cw >= 36 and ch >= 16
    for i, row in enumerate(matrix):
        for j, v in enumerate(row):
            x, y = px0 + j * cw, py0 + i * ch
            if v is None:
                continue
            fill = ramp_color(theme, (v - lo) / span)
            g.add(El("rect", x=x + 1, y=y + 1, width=max(cw - _GAP, 1),
                     height=max(ch - _GAP, 1), rx=2, fill=fill))
            if annotate:
                label = fmt(v)
                if text_width(label, theme.size_label) <= cw - 8:
                    g.add(El("text", [label], x=x + cw / 2, y=y + ch / 2,
                             dy="0.35em", text_anchor="middle",
                             font_size=theme.size_label,
                             fill=contrast_ink(fill, theme)))
    return lo, hi
