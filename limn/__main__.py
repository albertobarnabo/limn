"""``limn data.csv -o chart.svg`` — the one-liner for the shell.

Chart kind defaults to ``auto``: limn looks at the columns and picks.
Options that a given kind cannot use are refused rather than ignored, so
``--facet`` on a heatmap tells you instead of silently doing nothing.
"""

import argparse
import sys

from . import (line, area, bar, scatter, hist, box, heatmap, plot,
               __version__)
from .ingest import IngestError

# name -> (constructor, parameters it actually accepts)
_KINDS = {
    "auto": (plot, {"x", "y", "by"}),
    "line": (line, {"x", "y", "by", "facet"}),
    "area": (area, {"x", "y", "by", "facet"}),
    "bar": (bar, {"x", "y", "by", "facet"}),
    "scatter": (scatter, {"x", "y", "by", "facet"}),
    "hist": (hist, {"x", "facet"}),
    "box": (box, {"x", "y", "facet"}),
    "heatmap": (heatmap, set()),
}


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="limn",
        description="Chart a data file without writing a script.")
    p.add_argument("data", help="CSV/TSV/JSON file (or '-' for stdin)")
    p.add_argument("-o", "--output", default="chart.svg",
                   help="output file: .svg, .svgz or .png (default %(default)s)")
    p.add_argument("-k", "--kind", choices=sorted(_KINDS), default="auto")
    p.add_argument("-x", default=None, help="x column")
    p.add_argument("-y", default=None, action="append",
                   help="y column (repeatable)")
    p.add_argument("--by", default=None, help="series column")
    p.add_argument("--facet", default=None, help="small-multiples column")
    p.add_argument("--title", default=None)
    p.add_argument("--theme", default="paper", choices=("paper", "dusk"))
    p.add_argument("--size", default=None, metavar="WxH",
                   help="figure size, e.g. 900x520")
    p.add_argument("--version", action="version",
                   version="limn %s" % __version__)
    ns = p.parse_args(argv)

    build, accepted = _KINDS[ns.kind]
    kwargs = {"title": ns.title}
    for name, value in (("x", ns.x), ("y", ns.y), ("by", ns.by),
                        ("facet", ns.facet)):
        if value is None:
            continue
        if name not in accepted:
            print("limn: --%s does not apply to -k %s (it accepts: %s)"
                  % (name, ns.kind,
                     ", ".join("--" + a for a in sorted(accepted)) or "none"),
                  file=sys.stderr)
            return 2
        kwargs[name] = value[0] if name == "y" and len(value) == 1 else value

    try:
        data = sys.stdin.read() if ns.data == "-" else ns.data
        fig = build(data, **kwargs).theme(ns.theme)
        if ns.size:
            try:
                w, h = (float(v) for v in ns.size.lower().split("x"))
            except ValueError:
                print("limn: --size wants WxH, e.g. 900x520", file=sys.stderr)
                return 2
            fig.size(w, h)
        fig.save(ns.output)
    except (IngestError, ValueError, TypeError, OSError, RuntimeError) as exc:
        print("limn: %s" % exc, file=sys.stderr)
        return 1
    print("limn · wrote %s" % ns.output, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
