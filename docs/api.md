# API reference

Everything public, in one place. Anything not documented here is
private and may change.

## Chart constructors

All return a `Figure`. `data` accepts any ingestible shape (see
[data.md](data.md)); column selectors take names (or integer positions
for headerless data).

### `limn.line(data, x=None, y=None, by=None, title=None, markers=True, ylog=False, xlog=False, color=None, dash=None, facet=None, cols=None)`

| param | meaning |
|---|---|
| `x` | x column; default: first temporal column, else index |
| `y` | value column, or a list for several series; default: all numerics |
| `by` | category column that splits rows into series (long form) |
| `markers` | point dots up to 30 points (`False` to disable) |
| `ylog` / `xlog` | log scales; non-positive values dropped with a note |
| `color` | one hex, a list, or `{series: hex}` |
| `dash` | series name(s) to render dashed |
| `facet` / `cols` | small multiples by a category column, grid width |

### `limn.area(data, x=None, y=None, by=None, title=None, stack=True, color=None, facet=None, cols=None)`

`stack=False` → overlapping washes. Stacked negatives fall back to
washes, with a note.

### `limn.bar(data, x=None, y=None, by=None, title=None, stack=False, horizontal=False, sort=None, labels=False, color=None, facet=None, cols=None)`

`sort`: `None` · `"x"` · `"y"` · `"-y"`. `labels=True` → values at bar
ends. The value axis always includes zero.

### `limn.scatter(data, x=None, y=None, by=None, size=None, title=None, ylog=False, xlog=False, color=None, facet=None, cols=None)`

`size`: numeric column mapped to dot area (√ radius scale).

### `limn.hist(data, x=None, bins="auto", title=None, color=None, facet=None, cols=None)`

`bins`: `"auto"` (Freedman–Diaconis, Sturges fallback) or an int.
Faceted histograms share bin edges.

### `limn.box(data, x=None, y=None, title=None, color=None)`

Quartiles, median, Tukey whiskers (1.5·IQR), outlier dots. One box per
`x` category, or one overall.

### `limn.heatmap(data, title=None)`

A numeric matrix, or a table (category column → row labels, numeric
columns → columns). Cells annotate themselves when they fit.

### `limn.plot(data, x=None, y=None, by=None, title=None)`

Picks a form from the inferred column kinds. See
[charts.md](charts.md#plot--the-decider).

## Figure

All methods return `self` (chainable) except the output methods.

| method | effect |
|---|---|
| `.title(s)` `.subtitle(s)` `.caption(s)` | text around the plot |
| `.xlabel(s)` `.ylabel(s)` | axis names |
| `.size(w, h)` | figure size in px (default 720×432) |
| `.theme(name_or_Theme)` | `"paper"`, `"dusk"`, or a custom `Theme` |
| `.legend(mode)` | `"auto"` · `"none"` · `"legend"` (no direct labels) |
| `.hline(y, label=None, color=None)` | dashed reference on the value axis |
| `.vline(x, label=None, color=None)` | dashed reference at an x position |
| `.flag(x, y, text)` | ringed-dot callout with a bold label |
| `.ylim(lo, hi)` `.xlim(lo, hi)` | fix an axis range; marks beyond it clip |
| `.note(s)` | append to the figure's notes |
| `.to_svg()` | the SVG document as a string |
| `.save(path)` | write `.svg` (or `.png` with the `[png]` extra); prints notes to stderr once |
| `.notes` | list of everything limn decided or skipped |
| `._repr_svg_()` | Jupyter inline rendering (automatic) |

## Data utilities

| name | what |
|---|---|
| `limn.ingest(data)` | the parser on its own → `Table` with typed `.columns` and `.notes` |
| `limn.IngestError` | raised for structural problems (subclass of `ValueError`) |
| `limn.THEMES` | `{"paper": Theme, "dusk": Theme}` |
| `limn.Theme` | plain token bag; copy one from `THEMES` and override |
| `limn.__version__` | the version string |

## Errors you can rely on

| condition | error |
|---|---|
| empty input / unknown column / nothing numeric | `IngestError` with the available columns listed |
| log axis, no positive values | `IngestError` |
| figure too small for its labels | `ValueError` naming `.size()` |
| facet grid that doesn't fit | `ValueError` naming `.size()` and `cols=` |
| unknown theme | `ValueError` listing the themes |
| `.png` without cairosvg | `RuntimeError` naming the extra |

Everything about *values* — unparseable cells, missing data, references
outside range — is a note, never an exception.

## Command line

```
python -m limn DATA [-o OUT.svg] [-k auto|line|area|bar|scatter|hist|box]
                    [-x COL] [-y COL]... [--by COL] [--facet COL]
                    [--title T] [--theme paper|dusk]
```

`DATA` is a file or `-` for stdin. Exit code 1 with a `limn:` message on
structural errors.
