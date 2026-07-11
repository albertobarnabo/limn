# The chart forms

Seven explicit forms, one decider. All of them return a `Figure` (see
[styling](styling.md)); all accept the common selectors `x=`, `y=`,
`by=` (split into colored series), and — except box and heatmap —
`facet=` (split into [small multiples](styling.md#small-multiples)).

## line

```python
limn.line(data, x=None, y=None, by=None, title=None, markers=True,
          ylog=False, xlog=False, color=None, dash=None,
          facet=None, cols=None)
```

Time on the x axis if the data has any; multiple `y` columns (or a `by`
column) become series. Point markers appear up to 30 points, then the
line stands alone. **Missing values are gaps** — limn never interpolates
over a hole. Past ~3,000 points per series, min-max decimation kicks in:
the drawn path is visually identical and the file stays small.

`dash=["forecast"]` renders named series dashed — the conventional look
for projections and baselines.

## area

```python
limn.area(data, ..., stack=True)
```

Multiple series **stack** by default, separated by 2px surface gaps
(never outlines). `stack=False` gives overlapping 12%-opacity washes with
a solid top line each. Stacking requires non-negative values; if
negatives show up, limn falls back to overlapping washes and tells you.

## bar

```python
limn.bar(data, ..., stack=False, horizontal=False, sort=None, labels=False)
```

Categories on one axis, values on the other. Several `y` columns (or
`by`) group side by side, or stack with `stack=True`. `sort` is `None`
(data order), `"x"` (alphabetical), `"y"`/`"-y"` (by value).
`labels=True` puts the value at each bar's end — measured first, so it
never clips. `horizontal=True` flips the chart; long category names
usually want this. The value axis always includes zero, because bars
that don't start at zero are propaganda.

## scatter

```python
limn.scatter(data, x=None, y=None, by=None, size=None,
             ylog=False, xlog=False)
```

`by` colors by category (legend appears), `size` maps a numeric column
to dot **area** (square-root radius scale, so a dot twice the value
looks twice as big, not four times). Dots carry a 2px surface ring so
they survive overlaps; opacity adapts to point count.

## hist

```python
limn.hist(values, bins="auto")
```

Freedman–Diaconis binning by default (robust to outliers), Sturges as
the degenerate-IQR fallback, or give `bins` an integer. Faceted
histograms share their bin edges so the panels are actually comparable.

## box

```python
limn.box(data, x=None, y=None)
```

One box per category in `x` (or a single box): quartile box, median
line, Tukey whiskers at the last points within 1.5·IQR, outliers as
dots. The right form when the *spread* is the story.

## heatmap

```python
limn.heatmap(matrix_or_table)
```

Give it a numeric matrix (list of lists), or a table — the category
column becomes row labels, numeric columns become columns. Cells are
annotated with their values when they fit, in white or ink depending on
each cell's luminance. A gradient legend shows the scale.

## plot — the decider

```python
limn.plot(data)
```

Looks at the inferred column types and picks: temporal column → line;
category + numeric → bar; two numerics → scatter; one noisy numeric →
histogram; one trending numeric → line. It's a convenience, not an
oracle — when you disagree, call the form you meant.
