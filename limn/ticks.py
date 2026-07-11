"""Tick placement and label formatting — the part readers never notice
unless it's wrong.

Linear axes use the **Extended Wilkinson** algorithm (Talbot, Lin &
Hanrahan, *An Extension of Wilkinson's Algorithm for Positioning Tick
Labels on Axes*, InfoVis 2010): an optimization over simplicity, coverage,
and density that consistently beats the pick-a-step heuristics in older
libraries.  Time axes step in *calendar* units — months land on the 1st,
quarters on Jan/Apr/Jul/Oct, weeks on Monday — never in fake 30-day
months.  Labels carry their context exactly once: the year appears on the
first tick and wherever it changes, not on all twelve.

Formatting is unit-aware: a column that arrived as ``45%`` or ``$1,234``
keeps its unit on the axis (see coerce.NumberHint).
"""

import math
from datetime import datetime, timedelta

_Q = (1.0, 5.0, 2.0, 2.5, 4.0, 3.0)
_W = (0.25, 0.2, 0.5, 0.05)   # simplicity, coverage, density, legibility
_EPS = 1e-10


def _simplicity(qi, j, lmin, lmax, lstep):
    v = 1 if (lmin % lstep < _EPS or lstep - (lmin % lstep) < _EPS) \
        and lmin <= 0 <= lmax else 0
    return 1 - qi / (len(_Q) - 1) - j + v


def _simplicity_max(qi, j):
    return 1 - qi / (len(_Q) - 1) - j + 1


def _coverage(dmin, dmax, lmin, lmax):
    return 1 - 0.5 * ((dmax - lmax) ** 2 + (dmin - lmin) ** 2) \
        / ((0.1 * (dmax - dmin)) ** 2)


def _coverage_max(dmin, dmax, span):
    drange = dmax - dmin
    if span > drange:
        half = (span - drange) / 2
        return 1 - half ** 2 / ((0.1 * drange) ** 2)
    return 1.0


def _density(k, m, dmin, dmax, lmin, lmax):
    r = (k - 1) / (lmax - lmin)
    rt = (m - 1) / (max(lmax, dmax) - min(lmin, dmin))
    return 2 - max(r / rt, rt / r)


def _density_max(k, m):
    return 2 - (k - 1) / (m - 1) if k >= m else 1.0


def linear_ticks(dmin, dmax, target=5):
    """Extended Wilkinson: optimal loose labeling of [dmin, dmax].

    Returns a list of tick values whose span *contains* the data (loose
    labels — the axis is extended to the ticks, so data never floats in
    unlabeled space).  Always returns at least two ticks.
    """
    if math.isnan(dmin) or math.isnan(dmax):
        return [0.0, 1.0]
    if dmin > dmax:
        dmin, dmax = dmax, dmin
    if dmax - dmin < _EPS * max(abs(dmin), abs(dmax), 1.0):
        pad = 1.0 if dmin == 0 else abs(dmin) / 2
        dmin, dmax = dmin - pad, dmax + pad

    best = None       # (score, lmin, lstep, k)
    for j in range(1, 3):
        if best and _W[0] * _simplicity_max(0, j) + _W[1] + _W[2] + _W[3] \
                < best[0]:
            break
        for qi, q in enumerate(_Q):
            sm = _simplicity_max(qi, j)
            if best and _W[0] * sm + _W[1] + _W[2] + _W[3] < best[0]:
                break
            for k in range(2, 13):
                dm = _density_max(k, target)
                if best and _W[0] * sm + _W[1] + _W[2] * dm + _W[3] < best[0]:
                    break
                delta = (dmax - dmin) / (k + 1) / j / q
                z = math.ceil(math.log10(delta)) if delta > 0 else 0
                for z in range(z, z + 4):
                    step = j * q * 10.0 ** z
                    cm = _coverage_max(dmin, dmax, step * (k - 1))
                    if best and _W[0] * sm + _W[1] * cm + _W[2] * dm + _W[3] \
                            < best[0]:
                        break
                    min_start = int(math.floor(dmax / step) * j - (k - 1) * j)
                    max_start = int(math.ceil(dmin / step) * j)
                    if min_start > max_start:
                        continue
                    for start in range(min_start, max_start + 1):
                        lmin = start * step / j
                        lmax = lmin + step * (k - 1)
                        if lmin > dmin or lmax < dmax:
                            continue  # loose labels only
                        score = (_W[0] * _simplicity(qi, j, lmin, lmax, step)
                                 + _W[1] * _coverage(dmin, dmax, lmin, lmax)
                                 + _W[2] * _density(k, target, dmin, dmax,
                                                    lmin, lmax)
                                 + _W[3])
                        if best is None or score > best[0]:
                            best = (score, lmin, step, k)
    if best is None:  # pathological ranges: fall back to naive thirds
        step = (dmax - dmin) / 2
        return [dmin, dmin + step, dmax]
    _score, lmin, lstep, k = best
    ticks = [lmin + i * lstep for i in range(k)]
    return [0.0 if abs(t) < lstep * _EPS else t for t in ticks]


# -- time ---------------------------------------------------------------------

_SUBDAY_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800,
                 3600, 7200, 10800, 21600, 43200]   # seconds
_DAY_STEPS = [1, 2, 7, 14]
_MONTH_STEPS = [1, 2, 3, 6]


def time_ticks(tmin, tmax, target=6):
    """Calendar-aware ticks: [(datetime, label), ...] spanning the data.

    Chooses the finest calendar unit that stays at or under *target*
    ticks; alignment is to real boundaries (Mondays, month starts,
    quarter starts, round years) and each label carries the year/day
    context exactly where it changes.
    """
    if tmin > tmax:
        tmin, tmax = tmax, tmin
    if tmin == tmax:
        tmin, tmax = tmin - timedelta(days=1), tmax + timedelta(days=1)
    span = (tmax - tmin).total_seconds()

    for step in _SUBDAY_STEPS:
        if span / step <= target:
            return _label_times(_subday_ticks(tmin, tmax, step), step)
    for days in _DAY_STEPS:
        if span / (days * 86400) <= target:
            return _label_times(_day_ticks(tmin, tmax, days), 86400)
    for months in _MONTH_STEPS:
        if span / (months * 30.44 * 86400) <= target + 0.5:
            return _label_times(_month_ticks(tmin, tmax, months), "month")
    years = linear_ticks(tmin.year, tmax.year + 1, target)
    ticks = [datetime(max(1, int(round(y))), 1, 1) for y in years
             if 1 <= int(round(y)) <= 9999]
    return [(t, str(t.year)) for t in ticks]


def _subday_ticks(tmin, tmax, step):
    day = datetime(tmin.year, tmin.month, tmin.day)
    offset = math.ceil((tmin - day).total_seconds() / step) * step
    t = day + timedelta(seconds=offset)
    out = []
    while t <= tmax:
        out.append(t)
        t += timedelta(seconds=step)
    return out or [tmin, tmax]


def _day_ticks(tmin, tmax, days):
    t = datetime(tmin.year, tmin.month, tmin.day)
    if t < tmin:
        t += timedelta(days=1)
    if days in (7, 14):  # weeks align to Monday
        t += timedelta(days=(7 - t.weekday()) % 7)
    out = []
    while t <= tmax:
        out.append(t)
        t += timedelta(days=days)
    return out or [tmin, tmax]


def _month_ticks(tmin, tmax, months):
    idx = tmin.year * 12 + (tmin.month - 1)
    if not (tmin.day == 1 and tmin.hour == tmin.minute == 0):
        idx += 1
    idx = math.ceil(idx / months) * months   # quarters at Jan/Apr/Jul/Oct
    out = []
    while True:
        t = datetime(idx // 12, idx % 12 + 1, 1)
        if t > tmax:
            break
        out.append(t)
        idx += months
    return out or [tmin, tmax]


def _label_times(ticks, unit):
    out, prev = [], None
    for t in ticks:
        if unit == "month":
            label = t.strftime("%b")
            if prev is None or t.year != prev.year:
                label = t.strftime("%b %Y")
        elif unit >= 86400:
            label = "%d %s" % (t.day, t.strftime("%b"))
            if prev is None or t.year != prev.year:
                label += t.strftime(" %Y")
        else:
            label = t.strftime("%H:%M" if unit >= 60 else "%H:%M:%S")
            if prev is None or t.date() != prev.date():
                label = "%d %s %s" % (t.day, t.strftime("%b"), label)
        out.append((t, label))
        prev = t
    return out


# -- log ----------------------------------------------------------------------


def log_ticks(dmin, dmax, target=6):
    """Decade ticks for a log axis; steps decades when there are too many."""
    lo, hi = math.floor(math.log10(dmin)), math.ceil(math.log10(dmax))
    if hi == lo:
        hi += 1
    exps = list(range(lo, hi + 1))
    if len(exps) > target:
        stride = math.ceil(len(exps) / target)
        exps = exps[::stride]
        if exps[-1] < hi:
            exps.append(exps[-1] + stride)
    return [10.0 ** e for e in exps]


# -- number formatting ----------------------------------------------------------

_SUFFIXES = ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e4, "k"))


def axis_formatter(ticks, percent=False, currency=None):
    """One formatter for a whole axis: consistent scale and precision.

    The compaction suffix (k/M/B/T) and decimal count are chosen once from
    the tick set, so an axis reads ``0 · 0.5M · 1M · 1.5M`` — never a
    ragged mix of styles.
    """
    finite = [t for t in ticks if not math.isnan(t)]
    top = max((abs(t) for t in finite), default=1.0)
    scale, suffix = 1.0, ""
    for cut, suf in _SUFFIXES:
        if top >= cut:
            scale, suffix = (1e3 if suf == "k" else cut), suf
            break
    step = min((abs(a - b) for a, b in zip(finite, finite[1:]) if a != b),
               default=top or 1.0)
    scaled_step = step / scale
    decimals = max(0, -int(math.floor(math.log10(scaled_step) + 1e-9))) \
        if scaled_step > 0 else 0
    decimals = min(decimals, 6)

    def fmt(v):
        if math.isnan(v):
            return ""
        body = "{:,.{d}f}".format(v / scale, d=decimals)
        if body in ("-0", "-0.0", "-0.00"):
            body = body[1:]
        out = body + suffix
        if currency:
            out = (currency + out) if v >= 0 else ("-" + currency + out.lstrip("-"))
        if percent:
            out += "%"
        return out

    return fmt


def fmt_log(v, percent=False, currency=None):
    """Labels for decade ticks: compact from 1k up, uniform all the way.

    A log axis reading ``1 · 10 · 100 · 1k · 10k · 1M`` is one visual
    system; fmt_value's 10k compaction threshold would mix styles at the
    thousands boundary.
    """
    if v is None:
        return ""
    a = abs(v)
    body = None
    for cut, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
        if a >= cut:
            body = "{:,.2f}".format(v / cut).rstrip("0").rstrip(".") + suf
            break
    if body is None:
        if 0 < a < 1e-4:
            body = "%g" % v
        elif a < 1:
            body = "{:.6f}".format(v).rstrip("0").rstrip(".")
        else:
            body = "{:,.0f}".format(v)
    if currency:
        body = (currency + body) if v >= 0 else ("-" + currency + body.lstrip("-"))
    if percent:
        body += "%"
    return body


def fmt_value(v, percent=False, currency=None):
    """Compact single-value format for direct labels and notes."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–"
    a = abs(v)
    for cut, suf in _SUFFIXES:
        if a >= cut:
            scaled = v / (1e3 if suf == "k" else cut)
            body = "{:,.1f}".format(scaled).rstrip("0").rstrip(".") + suf
            break
    else:
        if a >= 100 or v == int(v):
            body = "{:,.0f}".format(v)
        elif a >= 1:
            body = "{:,.1f}".format(v).rstrip("0").rstrip(".")
        else:
            body = "{:.3g}".format(v)
    if currency:
        body = (currency + body) if v >= 0 else ("-" + currency + body.lstrip("-"))
    if percent:
        body += "%"
    return body
