"""Ingestion: hand limn whatever you have, get typed columns back.

Accepted shapes, all auto-detected::

    list of dicts        [{"month": "Jan", "sales": "1,204"}, ...]
    dict of lists        {"month": [...], "sales": [...]}
    list of scalars      [3, 1, 4, 1, 5]
    list of rows         [("Jan", 120), ("Feb", 140)]  (header row detected)
    CSV                  a path, a csv/tsv string, or an open file
    DataFrame / ndarray  duck-typed via .to_dict("list") / .tolist()

Every column is then classified as **number**, **temporal**, or
**category** by trying to parse *all* of its values — not by peeking at
the first one.  A column is numeric if at least 80% of its non-missing
values parse; stragglers become missing values and a note.  Slashed dates
get column-level judgement: if any value forces day-first (``13/02/…``)
the whole column is day-first; if every value is ambiguous, the reading
that makes the column chronological wins.

Nothing here raises on dirty values.  The only errors are structural —
no data at all, or a column name that doesn't exist.
"""

import csv
import io
import os

from .coerce import (is_missing, parse_number, parse_temporal,
                     proves_decimal_comma, temporal_ambiguous)

NUMBER, TEMPORAL, CATEGORY = "number", "temporal", "category"

_CLASSIFY_THRESHOLD = 0.8


class IngestError(ValueError):
    """The data's *shape* is unusable (values are never the problem)."""


class Column:
    """One typed column: parsed values (None = missing) plus provenance."""

    __slots__ = ("name", "kind", "values", "raw", "percent", "currency")

    def __init__(self, name, kind, values, raw, percent=False, currency=None):
        self.name = name
        self.kind = kind
        self.values = values
        self.raw = raw
        self.percent = percent
        self.currency = currency

    def __len__(self):
        return len(self.values)

    def present(self):
        """(index, value) pairs for the values that exist."""
        return [(i, v) for i, v in enumerate(self.values) if v is not None]


class Table:
    """The ingested dataset: ordered typed columns + human-readable notes."""

    def __init__(self, columns, notes):
        self.columns = columns          # list[Column], order preserved
        self.notes = notes              # list[str]
        self._by_name = {c.name: c for c in columns}

    def __len__(self):
        return len(self.columns[0]) if self.columns else 0

    @property
    def names(self):
        return [c.name for c in self.columns]

    def col(self, key):
        """A column by name, or by position for headerless data."""
        if isinstance(key, int):
            try:
                return self.columns[key]
            except IndexError:
                raise IngestError("no column %d — the data has %d column%s"
                                  % (key, len(self.columns),
                                     "s" if len(self.columns) != 1 else ""))
        if key in self._by_name:
            return self._by_name[key]
        raise IngestError("no column named %r — available: %s"
                          % (key, ", ".join(map(repr, self.names))))

    def first_of_kind(self, kind, exclude=()):
        for c in self.columns:
            if c.kind == kind and c.name not in exclude:
                return c
        return None


def ingest(data):
    """Any accepted shape -> Table.  The one front door."""
    raw_columns, notes = _extract_columns(data)
    if not raw_columns:
        raise IngestError("no data — the input was empty")
    width = max(len(vals) for _name, vals in raw_columns)
    if width == 0:
        raise IngestError("no rows — the input has columns but no values")
    columns = []
    for name, vals in raw_columns:
        vals = list(vals) + [None] * (width - len(vals))
        columns.append(_classify(str(name), vals, notes))
    return Table(columns, notes)


# -- shape detection ----------------------------------------------------------


def _extract_columns(data):
    """Whatever it is -> ([(name, raw_values)], notes)."""
    notes = []
    if data is None:
        raise IngestError("no data — got None")

    if hasattr(data, "to_dict") and hasattr(data, "columns"):  # pandas duck
        data = data.to_dict("list")
    elif hasattr(data, "tolist") and not isinstance(data, (str, bytes)):
        data = data.tolist()                                   # numpy duck

    if isinstance(data, io.IOBase) or (hasattr(data, "read")
                                       and not isinstance(data, (str, bytes))):
        return _from_csv_text(data.read(), notes)

    if isinstance(data, (str, bytes)):
        text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
        if "\n" not in text and os.path.exists(text):
            with open(text, "r", encoding="utf-8-sig", newline="") as f:
                return _from_csv_text(f.read(), notes)
        if any(sep in text for sep in (",", "\t", ";", "\n")):
            return _from_csv_text(text, notes)
        raise IngestError("string input is neither an existing file "
                          "nor CSV text: %r" % text[:80])

    if isinstance(data, dict):
        if not data:
            return [], notes
        return [(k, list(v) if _iterable(v) else [v]) for k, v in data.items()], notes

    if _iterable(data):
        rows = list(data)
        if not rows:
            return [], notes
        if all(isinstance(r, dict) for r in rows):
            names = []
            for r in rows:
                for k in r:
                    if k not in names:
                        names.append(k)
            return [(k, [r.get(k) for r in rows]) for k in names], notes
        if all(_iterable(r) and not isinstance(r, str) for r in rows):
            return _from_row_major([list(r) for r in rows], notes)
        return [("value", rows)], notes

    raise IngestError("don't know how to read a %s" % type(data).__name__)


def _iterable(x):
    return hasattr(x, "__iter__") and not isinstance(x, (str, bytes, dict))


def _from_row_major(rows, notes):
    width = max(len(r) for r in rows)
    rows = [r + [None] * (width - len(r)) for r in rows]
    header, body = _detect_header(rows)
    if header:
        names = [str(h) if h is not None else "col%d" % (i + 1)
                 for i, h in enumerate(rows[0])]
    else:
        names = ["col%d" % (i + 1) for i in range(width)]
        body = rows
    return [(names[i], [r[i] for r in body]) for i in range(width)], notes


def _detect_header(rows):
    """First row is a header iff it's all strings and the body isn't."""
    if len(rows) < 2:
        return False, rows
    first, rest = rows[0], rows[1:]
    if not all(isinstance(v, str) and v.strip() for v in first):
        return False, rows
    def looks_typed(v):
        return parse_number(v) is not None or parse_temporal(v) is not None
    if any(looks_typed(v) for v in first):
        return False, rows
    body_typed = sum(1 for r in rest for v in r if looks_typed(v))
    body_total = sum(1 for r in rest for v in r if not is_missing(v))
    if body_total and body_typed / body_total >= 0.5:
        return True, rest
    return False, rows


def _from_csv_text(text, notes):
    text = text.lstrip("﻿")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if r]
    if not rows:
        return [], notes
    return _from_row_major(rows, notes)


# -- classification -----------------------------------------------------------


def _classify(name, raw, notes):
    present = [(i, v) for i, v in enumerate(raw) if not is_missing(v)]
    n_missing = len(raw) - len(present)
    if not present:
        return Column(name, CATEGORY, [None] * len(raw), raw)

    as_number = _try_numbers(name, raw, present, notes)
    as_time = _try_temporal(name, raw, present, notes)
    if as_number and as_time:
        # both parse (rare): prefer the stricter temporal reading only if
        # it parsed *everything*; "2,019" style numbers are more common
        chosen = as_time if as_time[1] >= as_number[1] else as_number
    else:
        chosen = as_number or as_time
    if chosen:
        column, _rate, note = chosen
        if note:
            notes.append(note)
        if n_missing:
            pass  # missing values are normal; not worth a note
        return column

    values = [None if is_missing(v) else str(v).strip() for v in raw]
    return Column(name, CATEGORY, values, raw)


def _try_numbers(name, raw, present, notes):
    decimal_comma = any(proves_decimal_comma(v) for _i, v in present)
    parsed = [(i, parse_number(v, decimal_comma=decimal_comma))
              for i, v in present]
    hits = [(i, p) for i, p in parsed if p is not None]
    rate = len(hits) / len(present)
    if rate < _CLASSIFY_THRESHOLD or not hits:
        return None
    values = [None] * len(raw)
    for i, (v, _h) in hits:
        values[i] = v
    percent = sum(1 for _i, (_v, h) in hits if h.percent) > len(hits) / 2
    currencies = [h.currency for _i, (_v, h) in hits if h.currency]
    currency = currencies[0] if currencies else None
    note = None
    if rate < 1.0:
        bad = next(v for (i, v) in present
                   if parse_number(v, decimal_comma=decimal_comma) is None)
        note = ("column %r: %d of %d values aren't numbers — treated as "
                "missing (e.g. %r)" % (name, len(present) - len(hits),
                                       len(present), bad))
    if decimal_comma:
        notes.append("column %r: read with decimal commas (European style)"
                     % name)
    return Column(name, NUMBER, values, raw, percent, currency), rate, note


def _try_temporal(name, raw, present, notes):
    strings = [v for _i, v in present if isinstance(v, str)]
    dayfirst = False
    if strings:
        forced_day = sum(1 for v in strings
                         if _slash_first_component_over_12(v))
        if forced_day:
            dayfirst = True
        elif any(temporal_ambiguous(v) for v in strings):
            dayfirst = _prefer_chronological(present)
            if dayfirst is None:
                dayfirst = True  # every value ambiguous: dd/mm is the
                #                  worldwide majority convention
                notes.append("column %r: dates like %r are ambiguous — "
                             "read as day/month (chronology gave no hint)"
                             % (name, strings[0]))
    parsed = [(i, parse_temporal(v, dayfirst=dayfirst)) for i, v in present]
    hits = [(i, p) for i, p in parsed if p is not None]
    if not hits:
        return None
    rate = len(hits) / len(present)
    if rate < _CLASSIFY_THRESHOLD:
        return None
    values = [None] * len(raw)
    for i, v in hits:
        values[i] = v
    note = None
    if rate < 1.0:
        bad = next(v for (i, v) in present
                   if parse_temporal(v, dayfirst=dayfirst) is None)
        note = ("column %r: %d of %d values aren't dates — treated as "
                "missing (e.g. %r)" % (name, len(present) - len(hits),
                                       len(present), bad))
    return Column(name, TEMPORAL, values, raw), rate, note


def _slash_first_component_over_12(v):
    from .coerce import _SLASHED
    m = _SLASHED.match(v.strip()) if isinstance(v, str) else None
    if not m or len(m.group(1)) == 4:
        return False
    return int(m.group(1)) > 12 and int(m.group(2)) <= 12


def _prefer_chronological(present):
    """For all-ambiguous date columns, the monotonic reading wins."""
    for dayfirst in (True, False):
        parsed = [parse_temporal(v, dayfirst=dayfirst) for _i, v in present]
        if None in parsed:
            continue
        if all(a <= b for a, b in zip(parsed, parsed[1:])) or \
           all(a >= b for a, b in zip(parsed, parsed[1:])):
            other = [parse_temporal(v, dayfirst=not dayfirst)
                     for _i, v in present]
            other_mono = None not in other and (
                all(a <= b for a, b in zip(other, other[1:]))
                or all(a >= b for a, b in zip(other, other[1:])))
            if not other_mono:
                return dayfirst
    return None
