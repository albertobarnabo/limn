"""Scales: data space -> pixel space, each with its own idea of ticks.

Four scales cover every axis limn draws:

- :class:`Linear` — Extended Wilkinson ticks; the axis domain snaps
  outward to the tick span, so data never floats in unlabeled space.
- :class:`Time` — over datetimes, delegating to the calendar-aware ticks.
- :class:`Log` — decades, for data that spans orders of magnitude.
- :class:`Band` — categories to slots, for bar charts; owns the
  bandwidth arithmetic.

A scale is fitted from data once, then behaves as a pure function.
"""

import math
from datetime import datetime, timedelta

from .ticks import linear_ticks, time_ticks, log_ticks


class Linear:
    kind = "linear"

    def __init__(self, dmin, dmax, target=5, include_zero=False,
                 pad_frac=0.0):
        if include_zero:
            dmin, dmax = min(dmin, 0.0), max(dmax, 0.0)
        if pad_frac and dmax > dmin:
            span = dmax - dmin
            raw_min, raw_max = dmin, dmax
            dmin -= span * pad_frac
            dmax += span * pad_frac
            if raw_min >= 0 > dmin:
                dmin = 0.0   # padding never invents negative territory
            if raw_max <= 0 < dmax:
                dmax = 0.0
        self.ticks = linear_ticks(dmin, dmax, target)
        self.lo = min(self.ticks[0], dmin)
        self.hi = max(self.ticks[-1], dmax)

    def to_px(self, v, px0, px1):
        if v is None:
            return None
        frac = (v - self.lo) / (self.hi - self.lo)
        return px0 + frac * (px1 - px0)

    def tick_values(self):
        return self.ticks


class Time:
    kind = "time"

    def __init__(self, tmin, tmax, target=6):
        self.labeled = time_ticks(tmin, tmax, target)
        firsts = [t for t, _l in self.labeled]
        self.lo = min(tmin, firsts[0])
        self.hi = max(tmax, firsts[-1])
        if self.lo == self.hi:
            self.lo -= timedelta(days=1)
            self.hi += timedelta(days=1)

    def to_px(self, v, px0, px1):
        if v is None:
            return None
        frac = (v - self.lo).total_seconds() \
            / (self.hi - self.lo).total_seconds()
        return px0 + frac * (px1 - px0)

    def tick_values(self):
        return [t for t, _l in self.labeled]

    def tick_labels(self):
        return [l for _t, l in self.labeled]


class Log:
    kind = "log"

    def __init__(self, dmin, dmax, target=6):
        if dmin <= 0:
            raise ValueError("log scale needs positive values "
                             "(got a minimum of %g)" % dmin)
        self.ticks = log_ticks(dmin, dmax, target)
        self.lo = min(self.ticks[0], dmin)
        self.hi = max(self.ticks[-1], dmax)

    def to_px(self, v, px0, px1):
        if v is None or v <= 0:
            return None
        frac = (math.log10(v) - math.log10(self.lo)) \
            / (math.log10(self.hi) - math.log10(self.lo))
        return px0 + frac * (px1 - px0)

    def tick_values(self):
        return self.ticks


class Band:
    kind = "band"

    def __init__(self, categories, padding=0.25):
        seen = {}
        for c in categories:
            if c is not None and c not in seen:
                seen[c] = len(seen)
        self.categories = list(seen)
        self.index = seen
        self.padding = padding

    def slot(self, px0, px1):
        n = max(len(self.categories), 1)
        return (px1 - px0) / n

    def bandwidth(self, px0, px1):
        return self.slot(px0, px1) * (1 - self.padding)

    def center(self, category, px0, px1):
        i = self.index.get(category)
        if i is None:
            return None
        return px0 + (i + 0.5) * self.slot(px0, px1)

    def to_px(self, v, px0, px1):   # scatter/line over categories
        return self.center(v, px0, px1)

    def tick_values(self):
        return list(self.categories)
