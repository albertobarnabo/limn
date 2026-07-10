"""Themes: a small set of named tokens, chosen once, validated as a set.

The default palettes are the reference instance of a colorblind-validated
design system: the categorical slot *ordering* is part of the safety
mechanism (it maximizes worst-case adjacent color-vision-deficiency
distance — light-mode worst pair ΔE 24.2, well clear of the ≥12 target),
so series colors are assigned in fixed order and never cycled or
generated.  The dark theme is not an automatic inversion: its steps were
selected against the dark surface and validated separately.

Two themes ship: **paper** (light) and **dusk** (dark).  Everything a
renderer touches is a named token, so a custom theme is just a dict.
"""


class Theme:
    def __init__(self, **tokens):
        self.__dict__.update(tokens)

    def series_color(self, i):
        """Fixed-order assignment; past 8 series the palette repeats and a
        legend becomes mandatory (limn already always draws one there)."""
        return self.series[i % len(self.series)]


_COMMON = dict(
    font='system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif',
    size_title=15.0,
    size_subtitle=12.0,
    size_axis=11.0,
    size_label=11.0,
    size_caption=10.5,
    line_width=2.0,
    marker_radius=4.0,
    bar_max=24.0,
    bar_round=4.0,
    area_opacity=0.12,
    pad=8.0,
)

PAPER = Theme(
    name="paper",
    surface="#fcfcfb",
    ink="#0b0b0b",
    ink2="#52514e",
    muted="#898781",
    grid="#e1e0d9",
    baseline="#c3c2b7",
    series=["#2a78d6", "#1baf7a", "#eda100", "#008300",
            "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"],
    ramp=["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
          "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281",
          "#0d366b"],
    **_COMMON,
)

DUSK = Theme(
    name="dusk",
    surface="#1a1a19",
    ink="#ffffff",
    ink2="#c3c2b7",
    muted="#898781",
    grid="#2c2c2a",
    baseline="#383835",
    series=["#3987e5", "#199e70", "#c98500", "#008300",
            "#9085e9", "#e66767", "#d55181", "#d95926"],
    ramp=["#0d366b", "#104281", "#184f95", "#1c5cab", "#256abf", "#2a78d6",
          "#3987e5", "#5598e7", "#6da7ec", "#86b6ef", "#9ec5f4", "#b7d3f6",
          "#cde2fb"],
    **_COMMON,
)

THEMES = {"paper": PAPER, "dusk": DUSK}


def get_theme(name):
    if isinstance(name, Theme):
        return name
    try:
        return THEMES[name]
    except KeyError:
        raise ValueError("no theme %r — available: %s"
                         % (name, ", ".join(sorted(THEMES))))


def ramp_color(theme, t):
    """Interpolate the sequential ramp at t ∈ [0, 1] (piecewise linear)."""
    ramp = theme.ramp
    t = min(1.0, max(0.0, t))
    pos = t * (len(ramp) - 1)
    i = min(int(pos), len(ramp) - 2)
    frac = pos - i
    a, b = _hex_rgb(ramp[i]), _hex_rgb(ramp[i + 1])
    mixed = tuple(round(av + (bv - av) * frac) for av, bv in zip(a, b))
    return "#%02x%02x%02x" % mixed


def _hex_rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
