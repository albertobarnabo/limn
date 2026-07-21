"""Search for a categorical palette that survives color-vision deficiency.

Eight hues that stay distinct under protanopia, deuteranopia *and*
tritanopia cannot be chosen by eye — the constraint is a four-way
simultaneous one, and deuteranopia in particular collapses the red/green
axis that most palettes lean on.  So it is solved as a search:

1. sample OKLCH at a lightness/chroma band that reads as "a data color",
2. keep only candidates clearing the contrast floor against the surface,
3. greedily grow the palette by max-min all-pairs distance, taking the
   *worst* of normal/protan/deutan/tritan as the objective,
4. improve with local swaps until nothing moves.

Run: python3 tools/pick_palette.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cvd import all_pairs_min, contrast, distance   # noqa: E402

_KINDS = ("normal", "protan", "deutan", "tritan")


def _srgb(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def oklch_hex(L, C, H_deg):
    import math
    h = math.radians(H_deg)
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    vals = [_srgb(v) for v in (r, g, bb)]
    if any(v < 0 or v > 1 for v in (r, g, bb)):
        return None                      # outside the sRGB gamut
    return "#%02x%02x%02x" % tuple(round(v * 255) for v in vals)


def worst_pair_distance(palette):
    """Objective: the worst confusion across all pairs and all vision types."""
    return min(all_pairs_min(palette, k)[0] for k in _KINDS)


def candidates(surface, min_contrast, l_range, c_range):
    out = []
    for L in l_range:
        for C in c_range:
            for H in range(0, 360, 4):
                hexc = oklch_hex(L, C, H)
                if hexc and contrast(hexc, surface) >= min_contrast:
                    out.append(hexc)
    return sorted(set(out))


def pick(surface, n=8, min_contrast=3.0, seed_hue=250,
         l_range=(0.45, 0.55, 0.65, 0.72), c_range=(0.08, 0.12, 0.16, 0.20)):
    pool = candidates(surface, min_contrast, l_range, c_range)
    if not pool:
        raise SystemExit("no candidates clear %.1f:1 on %s"
                         % (min_contrast, surface))
    # seed with a blue, limn's identity color
    start = min(pool, key=lambda c: abs(_hue(c) - seed_hue))
    chosen = [start]
    while len(chosen) < n:
        best, best_score = None, -1
        for c in pool:
            if c in chosen:
                continue
            score = min(min(distance(c, o, k) for k in _KINDS) for o in chosen)
            if score > best_score:
                best, best_score = c, score
        chosen.append(best)
    # local improvement: try replacing each slot with anything better
    improved = True
    while improved:
        improved = False
        for i in range(len(chosen)):
            base = worst_pair_distance(chosen)
            for c in pool:
                if c in chosen:
                    continue
                trial = list(chosen)
                trial[i] = c
                if worst_pair_distance(trial) > base + 1e-9:
                    chosen, base, improved = trial, worst_pair_distance(trial), True
    return chosen


def _hue(hexc):
    import math
    from cvd import _oklab, hex_rgb
    _L, a, b = _oklab(hex_rgb(hexc))
    return math.degrees(math.atan2(b, a)) % 360


def order_for_adjacency(palette):
    """Order slots so consecutive assignments are maximally separated too."""
    remaining = list(palette)
    out = [remaining.pop(0)]
    while remaining:
        nxt = max(remaining,
                  key=lambda c: min(distance(c, out[-1], k) for k in _KINDS))
        out.append(nxt)
        remaining.remove(nxt)
    return out


if __name__ == "__main__":
    for label, surface, floor in (("paper", "#fcfcfb", 3.0),
                                  ("dusk", "#1a1a19", 3.0)):
        pal = order_for_adjacency(pick(surface, min_contrast=floor))
        print("%s: %s" % (label, pal))
        for k in _KINDS:
            d, pair = all_pairs_min(pal, k)
            print("   %-7s all-pairs min ΔE %5.1f  %s" % (k, d, pair))
        print("   contrast: %s"
              % {c: round(contrast(c, surface), 2) for c in pal})
