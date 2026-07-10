"""A small honest SVG writer.

No DOM, no templating — an element tree of tuples flattened to a string.
Numbers are emitted compactly (``12`` not ``12.000000``), text is always
escaped, and the two helpers that matter for print-quality output live
here: :func:`crisp`, which aligns hairlines to the pixel grid so a 1px
gridline is one gray pixel instead of two anti-aliased ones, and
:func:`rounded_bar`, which rounds only the data end of a bar (the
baseline end stays square, per the mark spec).
"""

from xml.sax.saxutils import escape, quoteattr


def _fmt(v):
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return ("%.2f" % v).rstrip("0").rstrip(".")
    return str(v)


def crisp(v):
    """Snap a coordinate to the half-pixel so 1px strokes render crisp."""
    return int(v) + 0.5


class El:
    """One SVG element; children are Els or raw strings (text nodes)."""

    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag, children=(), **attrs):
        self.tag = tag
        self.attrs = attrs
        self.children = list(children)

    def add(self, child):
        self.children.append(child)
        return child

    def render(self, out):
        out.append("<" + self.tag)
        for key, value in self.attrs.items():
            if value is None:
                continue
            out.append(" %s=%s" % (key.replace("_", "-"), quoteattr(_fmt(value))))
        if not self.children:
            out.append("/>")
            return
        out.append(">")
        for child in self.children:
            if isinstance(child, El):
                child.render(out)
            else:
                out.append(escape(str(child)))
        out.append("</%s>" % self.tag)


def document(width, height, background):
    root = El("svg", xmlns="http://www.w3.org/2000/svg",
              viewBox="0 0 %s %s" % (_fmt(float(width)), _fmt(float(height))),
              width=width, height=height, role="img")
    root.add(El("rect", x=0, y=0, width=width, height=height,
                fill=background))
    return root


def to_string(root):
    out = ['<?xml version="1.0" encoding="UTF-8"?>\n']
    root.render(out)
    return "".join(out)


def polyline_path(points):
    """An SVG path through *points*, with None entries breaking the line."""
    parts, pen_up = [], True
    for pt in points:
        if pt is None:
            pen_up = True
            continue
        x, y = pt
        parts.append("%s%s %s" % ("M" if pen_up else "L", _fmt(x), _fmt(y)))
        pen_up = False
    return " ".join(parts)


def area_path(top_points, bottom_points):
    """A closed region: along the top, back along the bottom (reversed)."""
    parts = []
    for i, (x, y) in enumerate(top_points):
        parts.append("%s%s %s" % ("M" if i == 0 else "L", _fmt(x), _fmt(y)))
    for x, y in reversed(bottom_points):
        parts.append("L%s %s" % (_fmt(x), _fmt(y)))
    return " ".join(parts) + " Z"


def rounded_bar(x, y, w, h, r, side):
    """A bar rounded at its data end only; square at the baseline.

    *side* is which end carries the data: 'top', 'bottom', 'right', 'left'.
    The radius is clamped so tiny bars never invert.
    """
    r = max(0.0, min(r, w / 2.0, h / 2.0))

    def path(*segments):
        return " ".join("%s%s" % (op, " ".join(_fmt(v) for v in vals))
                        for op, vals in segments) + " Z"

    if r < 0.25:
        return path(("M", (x, y)), ("h", (w,)), ("v", (h,)), ("h", (-w,)))
    if side == "top":
        return path(("M", (x, y + h)), ("v", (-(h - r),)),
                    ("q", (0, -r, r, -r)), ("h", (w - 2 * r,)),
                    ("q", (r, 0, r, r)), ("v", (h - r,)))
    if side == "bottom":
        return path(("M", (x, y)), ("v", (h - r,)),
                    ("q", (0, r, r, r)), ("h", (w - 2 * r,)),
                    ("q", (r, 0, r, -r)), ("v", (-(h - r),)))
    if side == "right":
        return path(("M", (x, y)), ("h", (w - r,)),
                    ("q", (r, 0, r, r)), ("v", (h - 2 * r,)),
                    ("q", (0, r, -r, r)), ("h", (-(w - r),)))
    # left: data end at x, baseline at x + w
    return path(("M", (x + w, y)), ("h", (-(w - r),)),
                ("q", (-r, 0, -r, r)), ("v", (h - 2 * r,)),
                ("q", (0, r, r, r)), ("h", (w - r,)))
