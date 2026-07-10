"""Build the limn gallery: every chart kind, on real-shaped data.

    python3 examples/gallery.py

Writes gallery/*.svg and gallery/index.html.  The first chart is the
thesis statement: raw CSV the way finance actually exports it — currency,
thousands separators, percent columns, N/A holes, European decimals —
straight into limn with no cleaning step.
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import limn

OUT = os.path.join(os.path.dirname(__file__), "..", "gallery")

MESSY_CSV = """\
month,revenue,costs,margin
Jan 2026,"$1,204,500","$980,100",18.6%
Feb 2026,"$1,310,900","$1,010,400",22.9%
Mar 2026,"$1,502,300","$1,090,800",27.4%
Apr 2026,"$1,488,000","$1,120,500",N/A
May 2026,"$1,610,750","$1,180,300",26.7%
Jun 2026,"$1,745,200","$1,240,900",28.9%
"""


def figures():
    random.seed(20260710)

    yield "messy_csv", limn.line(
        MESSY_CSV, x="month", y=["revenue", "costs"],
        title="Straight from the export",
    ).subtitle('input: "$1,204,500" · "N/A" · "18.6%" — zero cleaning') \
     .caption("source: finance CSV, ingested as-is")

    # -- line: multi-series with a gap ------------------------------------
    days, north, south, east = [], [], [], []
    for i in range(48):
        days.append("2025-%02d-%02d" % (1 + (i * 7 // 31) % 12,
                                        1 + (i * 7) % 28))
    days = sorted(set(days))
    n = len(days)
    for i in range(n):
        north.append(240 + i * 6 + 28 * math.sin(i / 4) + random.uniform(-9, 9))
        south.append(180 + i * 8 + random.uniform(-12, 12))
        east.append(300 + i * 2.5 + 18 * math.cos(i / 5) + random.uniform(-7, 7))
    north[n // 2] = None  # an honest hole in the data
    yield "line_series", limn.line(
        {"date": days, "North": north, "South": south, "East": east},
        x="date", title="Weekly active readers by region",
    ).subtitle("missing week shown as a gap, not interpolated away") \
     .caption("simulated data")

    # -- bar: sorted, labeled ---------------------------------------------
    yield "bar_sorted", limn.bar(
        {"language": ["Python", "TypeScript", "Rust", "Go", "Kotlin",
                      "Swift", "Ruby"],
         "share": ["31%", "22%", "9.4%", "12%", "6.1%", "5.2%", "3.8%"]},
        sort="-y", horizontal=True, labels=True,
        title="Language share of new services, 2026",
    ).subtitle("percent strings parsed; unit kept on the axis") \
     .caption("simulated data")

    # -- stacked bars --------------------------------------------------------
    yield "bar_stacked", limn.bar(
        {"quarter": ["Q1 24", "Q2 24", "Q3 24", "Q4 24",
                     "Q1 25", "Q2 25", "Q3 25", "Q4 25"],
         "Subscriptions": [4.1, 4.6, 5.0, 5.8, 6.2, 6.9, 7.4, 8.1],
         "Services": [2.2, 2.1, 2.5, 2.9, 2.8, 3.0, 3.2, 3.1],
         "Hardware": [1.4, 1.2, 1.5, 2.1, 1.3, 1.1, 1.6, 2.3]},
        stack=True, title="Revenue mix, $M",
    ).subtitle("stacked with surface gaps — no outlines") \
     .caption("simulated data")

    # -- area ------------------------------------------------------------------
    months = ["2024-%02d" % m for m in range(1, 13)] \
        + ["2025-%02d" % m for m in range(1, 13)]
    base = [42 + i * 3.1 + 8 * math.sin(i / 2.5) for i in range(24)]
    yield "area_stack", limn.area(
        {"month": months,
         "Organic": [round(b * 0.55, 1) for b in base],
         "Referral": [round(b * 0.28, 1) for b in base],
         "Paid": [round(b * 0.17, 1) for b in base]},
        x="month", title="Traffic by channel, thousands of sessions",
    ).caption("simulated data")

    # -- scatter -----------------------------------------------------------------
    rows = []
    for cont, (gdp0, life0, k) in {"Asia": (8, 68, 26),
                                   "Europe": (34, 76, 14),
                                   "Africa": (3, 58, 30)}.items():
        for _ in range(k):
            gdp = max(0.6, random.lognormvariate(math.log(gdp0), 0.55))
            rows.append({"gdp": round(gdp, 1),
                         "life": round(life0 + 6.5 * math.log(gdp / gdp0)
                                       + random.uniform(-2.5, 2.5), 1),
                         "pop": round(random.lognormvariate(2.4, 1.1), 1),
                         "continent": cont})
    yield "scatter_sized", limn.scatter(
        rows, x="gdp", y="life", by="continent", size="pop",
        title="Wealth and longevity",
    ).subtitle("dot area scales with population; GDP per capita in $k") \
     .caption("simulated data") \
     .xlabel("GDP per capita ($k)")

    # -- histogram ------------------------------------------------------------------
    latencies = [random.lognormvariate(3.4, 0.35) for _ in range(2500)]
    yield "hist_latency", limn.hist(
        latencies, title="API latency distribution, ms",
    ).subtitle("2,500 requests · Freedman–Diaconis binning") \
     .caption("simulated data")

    # -- heatmap ---------------------------------------------------------------------
    yield "heatmap_commits", limn.heatmap(
        {"team": ["Platform", "Mobile", "Data", "Infra", "Web"],
         "Mon": [34, 18, 22, 9, 27], "Tue": [41, 22, 31, 14, 33],
         "Wed": [46, 25, 29, 11, 38], "Thu": [39, 30, 24, 16, 30],
         "Fri": [28, 21, 18, 8, 22]},
        title="Merged pull requests by team and weekday",
    ).caption("simulated data")

    # -- the European CSV -----------------------------------------------------------
    yield "euro_csv", limn.line(
        "datum;temperatur\n01.03.2026;7,4\n08.03.2026;9,1\n15.03.2026;8,2\n"
        "22.03.2026;11,6\n29.03.2026;13,0\n05.04.2026;12,3\n12.04.2026;15,8\n"
        "19.04.2026;17,2\n26.04.2026;16,9\n03.05.2026;19,4\n",
        title="A German CSV, unedited",
    ).subtitle("semicolons · decimal commas · dotted day-first dates — detected") \
     .caption("source: weather export, ingested as-is")


HTML = """<!doctype html>
<meta charset="utf-8">
<title>limn gallery</title>
<style>
  body {{ margin: 0; padding: 28px; background: {bg}; color: {ink};
         font-family: system-ui, sans-serif; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  p  {{ color: {muted}; margin: 0 0 24px; font-size: 13px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill,
           minmax(560px, 1fr)); gap: 20px; }}
  .grid img {{ width: 100%; height: auto; display: block;
               border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.18); }}
</style>
<h1>limn — {theme} theme</h1>
<p>every chart on this page came out of the library exactly as rendered —
no post-processing. <a href="{other}.html" style="color:inherit">switch to
the {other} theme</a></p>
<div class="grid">
{imgs}
</div>
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    names = []
    for name, fig in figures():
        for theme in ("paper", "dusk"):
            fig.theme(theme).size(680, 400).save(
                os.path.join(OUT, "%s_%s.svg" % (name, theme)))
        names.append(name)
        print("built", name)
    pages = {"paper": ("#f9f9f7", "#0b0b0b", "#898781", "dusk"),
             "dusk": ("#0d0d0d", "#ffffff", "#898781", "paper")}
    for theme, (bg, ink, muted, other) in pages.items():
        imgs = "\n".join('<img src="%s_%s.svg" alt="%s">'
                         % (n, theme, n) for n in names)
        page = "index.html" if theme == "paper" else "dusk.html"
        with open(os.path.join(OUT, page), "w") as f:
            f.write(HTML.format(theme=theme, bg=bg, ink=ink, muted=muted,
                                imgs=imgs,
                                other="dusk" if theme == "paper" else "index"))
    print("gallery: open gallery/index.html")


if __name__ == "__main__":
    main()
