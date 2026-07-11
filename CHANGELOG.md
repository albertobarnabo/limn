# Changelog

## 1.1.0 — 2026-07-10

The storytelling release.

- **Annotations**: `.hline()` and `.vline()` reference lines (dashed,
  labeled, unit-aware — a vline takes a date string on a time axis) and
  `.flag(x, y, text)` point callouts. References outside the plotted
  range become notes, not accidents.
- **Small multiples**: `facet="column"` on line, area, bar, scatter, and
  hist — panels share y domain, x domain, category order, series colors,
  and histogram bin edges, all computed from the whole dataset. `cols=`
  sets the grid width.
- **Box plots**: `limn.box()` — quartiles, median, Tukey whiskers,
  outlier dots.
- **Log x axes**: `xlog=True` on line and scatter, joining `ylog`.
  Decade labels are uniformly compact (`1 · 10 · 100 · 1k · 10k`).
- **Axis limits**: `.ylim(lo, hi)` and `.xlim(lo, hi)`; marks beyond the
  limits clip instead of bleeding into the margins.
- **Series styling**: `color=` (hex, list, or `{name: hex}`) and
  `dash=[names]` for forecast-style dashed lines.
- **Big series**: automatic min-max decimation past ~3k points per line
  series — visually identical paths, tiny files.
- **PNG escape hatch**: `save("chart.png")` rasterizes at 2× via the
  optional `[png]` extra (cairosvg); SVG still needs nothing.
- Packaging: published as **limn-charts** (import stays `limn`); user
  documentation under `docs/`.

## 1.0.0 — 2026-07-10

Initial release: smart messy-data ingestion (currency, percents,
European decimals, accounting negatives, magnitude suffixes, missing
vocabulary, evidence-based date disambiguation), Extended Wilkinson
ticks, calendar-aware time axes, measured no-clip layout, direct end
labels, colorblind-validated paper/dusk themes, six chart forms plus
`plot()`, notebook rendering, CLI.
