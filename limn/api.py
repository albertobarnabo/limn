"""The public face: six chart constructors and one that decides for you.

Every function takes *data* in any ingestible shape (CSV path or text,
list of dicts, dict of lists, DataFrame, plain sequence — see ingest.py)
plus column selectors, and returns a :class:`~limn.figure.Figure` you can
chain style calls on and save::

    limn.line("sales.csv", x="month", y="revenue", by="region",
              title="Revenue by region").save("revenue.svg")
"""

from .figure import Figure
from .ingest import ingest, NUMBER, TEMPORAL, CATEGORY


def line(data, x=None, y=None, by=None, title=None, markers=True,
         ylog=False):
    """A line chart.  Missing values become visible gaps, never lies."""
    return Figure("line", data, x=x, y=y, by=by, title=title,
                  markers=markers, ylog=ylog)


def area(data, x=None, y=None, by=None, title=None, stack=True):
    """An area chart; multiple series stack by default (set stack=False
    for overlapping washes)."""
    return Figure("area", data, x=x, y=y, by=by, title=title, stack=stack)


def bar(data, x=None, y=None, by=None, title=None, stack=False,
        horizontal=False, sort=None, labels=False):
    """A bar chart.  *by* groups (or stacks, with stack=True); *sort* is
    None (data order), 'x', 'y', or '-y'; *labels* puts values at the
    bar ends."""
    return Figure("bar", data, x=x, y=y, by=by, title=title, stack=stack,
                  horizontal=horizontal, sort=sort, labels=labels)


def scatter(data, x=None, y=None, by=None, size=None, title=None,
            ylog=False):
    """A scatter plot; *by* colors by category, *size* scales dot area
    by a numeric column."""
    return Figure("scatter", data, x=x, y=y, by=by, size=size, title=title,
                  ylog=ylog)


def hist(data, x=None, bins="auto", title=None):
    """A histogram with Freedman–Diaconis binning (or give *bins* an int)."""
    return Figure("hist", data, x=x, title=title, bins=bins)


def heatmap(data, title=None):
    """A heatmap from a numeric matrix, or a table whose category column
    labels the rows."""
    return Figure("heatmap", data, title=title)


def plot(data, x=None, y=None, by=None, title=None):
    """Look at the data, pick the form.

    time on x -> line · two numerics -> scatter · category + numeric ->
    bar · one numeric column -> histogram for spreads, line for sequences.
    An explicit chart function is always available when you disagree.
    """
    table = ingest(data)
    kinds = [c.kind for c in table.columns]
    if x is None and y is None:
        if any(k == TEMPORAL for k in kinds):
            return line(data, x=x, y=y, by=by, title=title)
        numerics = kinds.count(NUMBER)
        has_cat = any(k == CATEGORY for k in kinds)
        if has_cat and numerics >= 1:
            return bar(data, x=x, y=y, by=by, title=title)
        if numerics >= 2:
            return scatter(data, x=x, y=y, by=by, title=title)
        if numerics == 1:
            col = table.first_of_kind(NUMBER)
            values = [v for v in col.values if v is not None]
            monotonicish = sum(
                1 for a, b in zip(values, values[1:]) if b >= a)
            if len(values) > 12 and monotonicish < len(values) * 0.75:
                return hist(data, title=title)
            return line(data, x=x, y=y, by=by, title=title)
        raise ValueError("plot() found nothing plottable — columns are: %s"
                         % ", ".join("%s (%s)" % (c.name, c.kind)
                                     for c in table.columns))
    xk = table.col(x).kind if x is not None else None
    if xk == CATEGORY:
        return bar(data, x=x, y=y, by=by, title=title)
    if xk == TEMPORAL:
        return line(data, x=x, y=y, by=by, title=title)
    if xk == NUMBER and y is not None:
        return scatter(data, x=x, y=y, by=by, title=title)
    return line(data, x=x, y=y, by=by, title=title)
