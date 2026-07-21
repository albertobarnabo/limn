"""Color-vision validation: the palette metric, made executable.

The claim a chart library makes when it says "colorblind-safe" has to be
checkable, or it is marketing.  This module computes, for a palette:

- **all-pairs** minimum perceptual distance (not merely adjacent pairs —
  a reader compares any two series, not just neighbours in the legend),
- under normal vision and simulated protanopia, deuteranopia and
  tritanopia (Brettel/Viénot-style linear reduction),
- plus WCAG contrast of every slot against the surface it sits on.

Used by tools/palette_report.py and asserted by tests/test_palette.py, so
a regression fails the suite instead of shipping.
"""

import math

# Brettel-derived linear CVD simulation matrices (Viénot, Brettel & Mollon
# 1999), applied in linear-light RGB.
_CVD = {
    "protan": ((0.0, 2.02344, -2.52581), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "deutan": ((1.0, 0.0, 0.0), (0.494207, 0.0, 1.24827), (0.0, 0.0, 1.0)),
    "tritan": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (-0.395913, 0.801109, 0.0)),
}


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def simulate(hex_color, kind):
    """Return *hex_color* as that flavour of color vision receives it.

    Viénot, Brettel & Mollon (1999).  The projection is defined in **LMS
    cone space**, so the pipeline is linear-RGB → LMS → drop the missing
    cone → LMS → linear-RGB.  (Applying those coefficients straight to RGB
    is a tempting shortcut and gives nonsense — it can report two colors as
    *further* apart under color blindness than under normal vision.)
    """
    if kind == "normal":
        return hex_rgb(hex_color)
    r, g, b = (_to_linear(c) for c in hex_rgb(hex_color))

    L = 17.8824 * r + 43.5161 * g + 4.11935 * b
    M = 3.45565 * r + 27.1554 * g + 3.86714 * b
    S = 0.0299566 * r + 0.184309 * g + 1.46709 * b

    if kind == "protan":
        L = 2.02344 * M - 2.52581 * S
    elif kind == "deutan":
        M = 0.494207 * L + 1.24827 * S
    elif kind == "tritan":
        S = -0.395913 * L + 0.801109 * M
    else:
        raise ValueError("unknown vision type %r" % kind)

    r2 = 0.080944447900 * L - 0.130504409000 * M + 0.116721066000 * S
    g2 = -0.010248533500 * L + 0.054019326600 * M - 0.113614708000 * S
    b2 = -0.000365296938 * L - 0.004121614690 * M + 0.693511405000 * S
    return tuple(_to_srgb(v) for v in (r2, g2, b2))


def _oklab(rgb):
    r, g, b = (_to_linear(c) for c in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (max(v, 0.0) ** (1 / 3) for v in (l, m, s))
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def distance(a, b, kind="normal"):
    """Perceptual distance between two hex colors, on a 0-100 scale."""
    la, lb = _oklab(simulate(a, kind)), _oklab(simulate(b, kind))
    return 100 * math.sqrt(sum((x - y) ** 2 for x, y in zip(la, lb)))


def all_pairs_min(palette, kind="normal"):
    """The worst confusion in the whole palette — every pair, not just
    the ones that happen to sit next to each other in the legend."""
    worst, pair = float("inf"), None
    for i in range(len(palette)):
        for j in range(i + 1, len(palette)):
            d = distance(palette[i], palette[j], kind)
            if d < worst:
                worst, pair = d, (palette[i], palette[j])
    return worst, pair


def relative_luminance(hex_color):
    r, g, b = (_to_linear(c) for c in hex_rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = relative_luminance(a), relative_luminance(b)
    lo, hi = sorted((la, lb))
    return (hi + 0.05) / (lo + 0.05)


def report(palette, surface, label=""):
    """A table of every check, for humans and for tests."""
    rows = {}
    for kind in ("normal", "protan", "deutan", "tritan"):
        worst, pair = all_pairs_min(palette, kind)
        rows[kind] = {"min_delta": round(worst, 1), "pair": pair}
    rows["contrast"] = {c: round(contrast(c, surface), 2) for c in palette}
    rows["label"] = label
    return rows
