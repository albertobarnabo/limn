# Styling, annotations, and small multiples

Everything on this page is a chainable `Figure` method or constructor
argument. Sensible defaults mean most charts need none of it.

## Text around the plot

```python
fig.title("Revenue by region")     # 15px semibold, top-left
fig.subtitle("monthly, EUR")       # 12px, under the title
fig.caption("source: ERP export")  # 10.5px muted, bottom-left
fig.xlabel("month")                # centered under the x axis
fig.ylabel("sessions (k)")         # above the y axis, left-aligned
```

## Size and themes

```python
fig.size(760, 440)                 # px; the default is 720×432
fig.theme("dusk")                  # or "paper" (default)
```

`paper` is a warm light theme; `dusk` is a true dark theme — its palette
steps were selected against the dark surface and validated separately,
not color-flipped. Both use a colorblind-validated 8-slot categorical
palette whose *order* is part of the safety mechanism, which is why
series colors are assigned in fixed order and never cycled.

A custom theme is a plain object of named tokens:

```python
from limn import Theme, THEMES
mine = Theme(**{**vars(THEMES["paper"]), "series": ["#0a9", "#c33", ...]})
fig.theme(mine)
```

## Series overrides

```python
limn.line(data, color="#0a9")                    # single series
limn.line(data, color={"forecast": "#898781"})   # by name
limn.line(data, color=["#0a9", "#c33"])          # by position
limn.line(data, dash=["forecast"])               # dashed series
```

## Annotations

The difference between a chart and an argument:

```python
(limn.line(data, x="week", y="uptime")
     .hline(99, "SLA target")            # reference on the value axis
     .vline("2026-03-15", "failover")    # event on the x axis
     .flag("2026-03-22", 96.7, "the bad Tuesday"))   # one-point callout
```

- `hline(y, label=None, color=None)` — dashed line across the plot at a
  value. On horizontal bar charts it targets the value axis (and renders
  vertically), because "the target" is about the value, not the screen.
- `vline(x, label=None, color=None)` — dashed line at an x position:
  a number, a date string, or a category name, coerced with the same
  parsers as the data.
- `flag(x, y, text)` — a ringed dot and a bold label beside it, flipped
  to whichever side has room.

References outside the plotted range are skipped with a note, never
drawn into the void.

## Axis control

```python
fig.ylim(0, 100)          # exact; marks beyond it clip AND limn says so
fig.xlim(0, 50)           # numeric x axis
fig.xlim("2026-01-01", "2026-03-31")     # or dates, on a time axis
limn.line(data, ylog=True)            # log value axis
limn.scatter(data, xlog=True)         # log x axis
```

Log axes label decades compactly (`1 · 10 · 100 · 1k · 10k`); zero and
negative values can't live on one, so they're dropped with a note.

Limits are promises, not hints: the axis is exactly the range you gave,
not widened outward to round numbers. Anything outside it is clipped and
counted in `fig.notes`. On a bar chart, a range that excludes zero also
removes the baseline — a bar whose length no longer encodes its value
must not *look* like one that does.

## Legends and direct labels

Past a theme's measured safe series count (`theme.safe_n` — 8 for both
shipped themes), color alone stops being reliable for colorblind readers,
so limn dashes the extra line series automatically and notes it.

With two or more series a legend always appears (identity is never
color-alone); line and area charts with ≤ 4 series *additionally* get
direct labels at the line ends, with collision resolution.
`fig.legend("none")` hides the legend, `fig.legend("legend")` suppresses
the direct labels.

## Small multiples

```python
limn.line(rows, x="month", y="signups", facet="city", cols=2)
```

`facet=` splits the chart into a grid of panels — **sharing y domain,
x domain, category order, series colors, and histogram bin edges**,
all computed from the whole dataset. That sharing is the point: panels
with private axes read as comparable when they aren't. The grid is
`cols` wide (default 2, or 3 for more than four panels); give the figure
enough `.size()` to breathe, and limn will tell you if you didn't.

## PNG export

```python
fig.save("chart.png")     # needs: pip install limn-charts[png]
```

SVG needs nothing and is the native output; PNG is rasterized at 2×
via `cairosvg` if you installed it.
