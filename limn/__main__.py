"""``python -m limn data.csv -o chart.svg`` — the one-liner for the shell.

Chart kind defaults to ``auto``: limn looks at the columns and picks.
"""

import argparse
import sys

from . import line, area, bar, scatter, hist, box, heatmap, plot, __version__
from .ingest import IngestError

_KINDS = {"auto": plot, "line": line, "area": area, "bar": bar,
          "scatter": scatter, "hist": hist, "box": box}


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="python -m limn",
        description="Chart a data file without writing a script.")
    p.add_argument("data", help="CSV/TSV file (or '-' for stdin)")
    p.add_argument("-o", "--output", default="chart.svg")
    p.add_argument("-k", "--kind", choices=sorted(_KINDS), default="auto")
    p.add_argument("-x", default=None, help="x column")
    p.add_argument("-y", default=None, action="append",
                   help="y column (repeatable)")
    p.add_argument("--by", default=None, help="series column")
    p.add_argument("--facet", default=None, help="small-multiples column")
    p.add_argument("--title", default=None)
    p.add_argument("--theme", default="paper")
    p.add_argument("--version", action="version",
                   version="limn %s" % __version__)
    ns = p.parse_args(argv)
    data = sys.stdin.read() if ns.data == "-" else ns.data
    y = ns.y if ns.y is None or len(ns.y) > 1 else ns.y[0]
    kwargs = dict(x=ns.x, y=y, title=ns.title)
    if ns.kind != "box":
        kwargs["by"] = ns.by
        if ns.kind != "auto" and ns.facet:
            kwargs["facet"] = ns.facet
    try:
        fig = _KINDS[ns.kind](data, **kwargs)
        fig.theme(ns.theme).save(ns.output)
    except (IngestError, ValueError, OSError) as exc:
        print("limn: %s" % exc, file=sys.stderr)
        return 1
    print("limn · wrote %s" % ns.output, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
