# Quickstart

## Install

```bash
pip install limn-charts
```

The distribution is `limn-charts` (the name `limn` was taken on PyPI);
the import is plain `limn`. There are **zero dependencies** — no numpy,
no pandas, no C extensions. Python 3.9+.

For optional PNG export (SVG needs nothing):

```bash
pip install limn-charts[png]
```

## Your first chart

```python
import limn

limn.line("sales.csv").save("sales.svg")
```

That's a complete program. limn read the CSV, inferred which column is
time and which are values, parsed `"$1,204,500"` and `"N/A"` without
complaint, placed the ticks, measured the labels, and wrote a
publication-grade SVG.

Naming things helps when the file has more than one story in it:

```python
limn.line("sales.csv", x="month", y="revenue", by="region",
          title="Revenue by region").save("by_region.svg")
```

## The shapes limn eats

Every chart function accepts any of these as `data`:

```python
limn.bar("data.csv")                          # a path
limn.bar("a,b\n1,2\n3,4")                     # CSV/TSV text (delimiter sniffed)
limn.bar(open("data.csv"))                    # an open file
limn.bar([{"team": "a", "pts": 3}, ...])      # list of dicts
limn.bar({"team": [...], "pts": [...]})       # dict of lists
limn.hist([3, 1, 4, 1, 5])                    # a plain sequence
limn.hist(v * v for v in values)              # a generator
limn.line(df)                                 # any DataFrame-like (duck-typed)
```

## Styling is a chain

```python
(limn.bar(rows, x="team", y="points", sort="-y", labels=True)
     .title("Standings")
     .subtitle("after matchday 12")
     .caption("source: league API")
     .theme("dusk")            # "paper" (light) is the default
     .size(760, 440)
     .save("standings.svg"))
```

## Notebooks

A `Figure` renders inline in Jupyter automatically — just leave it as
the last expression in a cell.

## The command line

```bash
python -m limn data.csv -o chart.svg --title "Whatever the file says"
python -m limn data.csv -k bar -x team -y points --theme dusk
cat data.csv | python -m limn - -o chart.svg
```

`-k auto` (the default) looks at the columns and picks the form.

## When something is off, limn says so

Values never raise. Whatever limn had to decide or skip, it reports once
on stderr when you save:

```
limn · column 'price': 3 of 120 values aren't numbers — treated as missing (e.g. 'oops')
limn · column 'datum': read with decimal commas (European style)
limn · 1 missing value shown as gap in the line
```

The same messages are available programmatically as `fig.notes`.

Next: [the chart forms](charts.md) · [how ingestion thinks](data.md) ·
[styling & annotations](styling.md) · [API reference](api.md)
