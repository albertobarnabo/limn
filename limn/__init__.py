"""limn — charts for people who have real data, not clean data.

    limn (v., archaic): to depict in painting or words; to illuminate
    a manuscript.

A zero-dependency plotting library that meets your data where it is:
hand it a CSV export full of ``$1,234.50``, ``45%``, ``N/A`` and mixed
date formats, and get back a publication-grade SVG — types inferred,
units kept, ticks placed by the Extended Wilkinson algorithm, every
label measured so nothing ever clips.

    import limn
    limn.line("sales.csv", by="region", title="Revenue").save("out.svg")

Seven forms: line, area, bar, scatter, hist, box, heatmap — plus
plot(), which looks at the data and picks one.  Annotations, small
multiples, and log axes are one call each.  Figures render inline in
notebooks.
"""

from .api import line, area, bar, scatter, hist, box, heatmap, plot
from .figure import Figure
from .ingest import ingest, IngestError
from .theme import THEMES, Theme

__version__ = "1.1.0"

__all__ = ["line", "area", "bar", "scatter", "hist", "box", "heatmap",
           "plot", "Figure", "ingest", "IngestError", "THEMES", "Theme",
           "__version__"]
