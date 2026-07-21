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
import json
import os
import re

from .coerce import (is_missing, parse_number, parse_temporal,
                     proves_decimal_comma, proves_dot_thousands,
                     temporal_ambiguous)

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


def ingest(data, dtypes=None):
    """Any accepted shape -> Table.  The one front door.

    *dtypes* overrides the classifier per column —
    ``{"zip": "category", "ts": "temporal", "price": "number"}`` — for the
    cases where the data is right and the guess is wrong.
    """
    raw_columns, notes = _extract_columns(data)
    if not raw_columns:
        raise IngestError("no data — the input was empty")
    width = max(len(vals) for _name, vals in raw_columns)
    if width == 0:
        raise IngestError("no rows — the input has columns but no values")
    dtypes = _check_dtypes(dtypes, [str(n) for n, _v in raw_columns])
    columns = []
    for name, vals in raw_columns:
        vals = list(vals) + [None] * (width - len(vals))
        columns.append(_classify(str(name), vals, notes,
                                 dtype=dtypes.get(str(name))))
    return Table(columns, notes)


def _check_dtypes(dtypes, names):
    if not dtypes:
        return {}
    kinds = (NUMBER, TEMPORAL, CATEGORY)
    out = {}
    for key, kind in dtypes.items():
        if key not in names:
            raise IngestError("dtypes names column %r, which doesn't exist — "
                              "available: %s"
                              % (key, ", ".join(map(repr, names))))
        kind = str(kind).lower()
        if kind not in kinds:
            raise IngestError("dtypes[%r] = %r — use one of: %s"
                              % (key, kind, ", ".join(kinds)))
        out[key] = kind
    return out


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
                text = f.read()
        if _looks_like_json(text):
            return _from_json_text(text, notes)
        if any(sep in text for sep in (",", "\t", ";", "\n")):
            return _from_csv_text(text, notes)
        raise IngestError("string input is neither an existing file "
                          "nor CSV/JSON text: %r" % text[:80])

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
        names = _dedupe_names(
            [str(h).strip() if h is not None else "col%d" % (i + 1)
             for i, h in enumerate(rows[0])], notes)
    else:
        names = ["col%d" % (i + 1) for i in range(width)]
        body = rows
        notes.append("no header row found — columns named col1..col%d; "
                     "the first row is being charted as data" % width)
    return [(names[i], [r[i] for r in body]) for i in range(width)], notes


def _looks_typed(v):
    return parse_number(v) is not None or parse_temporal(v) is not None


def _detect_header(rows):
    """Does the first row *label* the columns below it, or is it data?

    Judged per column rather than per cell.  A header exists when at least
    one column pairs a text first cell with a predominantly typed body —
    so a year in the header (``product,2023,2024``) no longer vetoes the
    whole row, and a table whose text columns outnumber its numeric ones
    keeps its names.  Only a first row that is typed *everywhere* is data.
    """
    if len(rows) < 2:
        return False, rows
    first, rest = rows[0], rows[1:]
    if not all(isinstance(v, str) and v.strip() for v in first):
        return False, rows
    if all(_looks_typed(v) for v in first):
        return False, rows          # a row of pure numbers is data, not names

    for_header = against = 0
    for i, cell in enumerate(first):
        body = [r[i] for r in rest if not is_missing(r[i])]
        if not body:
            continue
        typed = sum(1 for v in body if _looks_typed(v)) / len(body)
        if typed < _CLASSIFY_THRESHOLD:
            continue                     # a text column tells us nothing
        if not _looks_typed(cell):
            for_header += 1              # a label over numbers: a header
        elif _in_family(cell, body):
            against += 1                 # a peer of its own column: data
        # A typed cell that is NOT a peer of its column — the 2023 in
        # `product,2023,2024` over a body of 120/140 — is a label too, and
        # counts as neither: it must not veto the columns that do speak.
    if for_header or not against:
        return True, rest
    return False, rows


def _in_family(cell, body):
    """Could *cell* plausibly be one more value of this column?

    Used to tell a header from data when both parse: a year sitting over
    a column of small counts is a label, a number sitting inside its
    column's own range is data.
    """
    parsed = parse_number(cell)
    values = [parse_number(v) for v in body]
    values = [v[0] for v in values if v is not None]
    if parsed is None or not values:
        return True          # dates and unparseables: assume peer, stay safe
    lo, hi = min(values), max(values)
    span = max(abs(lo), abs(hi)) or 1.0
    return lo - 4 * span <= parsed[0] <= hi + 4 * span


def _dedupe_names(names, notes):
    """Excel and SQL joins ship duplicate headers; make every name reachable."""
    seen, out = {}, []
    for name in names:
        if name in seen:
            seen[name] += 1
            new = "%s.%d" % (name, seen[name])
            notes.append("duplicate column name %r renamed to %r"
                         % (name, new))
            out.append(new)
        else:
            seen[name] = 1
            out.append(name)
    return out


def _looks_like_json(text):
    head = text.lstrip()[:1]
    return head in ("[", "{")


def _from_json_text(text, notes):
    """JSON is the other half of real exports: APIs, logs, ``jq`` output.

    Accepts a list of objects, an object of lists, a list of rows, a
    single object, and NDJSON (one object per line).
    """
    stripped = text.strip()
    try:
        data = json.loads(stripped)
    except ValueError:
        rows = []
        for i, line in enumerate(stripped.splitlines(), 1):
            line = line.strip().rstrip(",")
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                raise IngestError("line %d is not valid JSON: %r"
                                  % (i, line[:60]))
        if not rows:
            raise IngestError("input looked like JSON but did not parse")
        notes.append("read as NDJSON (%d records)" % len(rows))
        data = rows
    if isinstance(data, dict):
        if data and all(_iterable(v) for v in data.values()):
            return [(k, list(v)) for k, v in data.items()], notes
        data = [data]                       # a lone record is one row
    if not isinstance(data, list) or not data:
        raise IngestError("JSON input holds no records")
    if all(isinstance(r, dict) for r in data):
        names = []
        for r in data:
            for k in r:
                if k not in names:
                    names.append(k)
        return [(k, [_flatten(r.get(k)) for r in data]) for k in names], notes
    if all(isinstance(r, (list, tuple)) for r in data):
        return _from_row_major([list(r) for r in data], notes)
    return [("value", [_flatten(v) for v in data])], notes


def _flatten(v):
    """Nested JSON values become their repr — charted as categories, not junk."""
    if isinstance(v, (dict, list, tuple)):
        return json.dumps(v, separators=(",", ":"))[:120]
    return v


_SEP_DIRECTIVE = re.compile(r"^sep=(.)\s*$", re.IGNORECASE)


def _from_csv_text(text, notes):
    text = text.lstrip("\ufeff")
    lines = text.splitlines()

    # Excel writes a literal "sep=;" first line that csv.Sniffer chokes on
    forced = None
    if lines and _SEP_DIRECTIVE.match(lines[0]):
        forced = _SEP_DIRECTIVE.match(lines[0]).group(1)
        lines = lines[1:]
        notes.append("honoured the spreadsheet's sep=%r directive" % forced)
        text = "\n".join(lines)

    if forced:
        rows = [r for r in csv.reader(io.StringIO(text), delimiter=forced) if r]
    else:
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel
        rows = [r for r in csv.reader(io.StringIO(text), dialect) if r]
    if not rows:
        return [], notes

    # Real exports lead with "Report generated: …", account metadata, blank
    # lines.  The table starts at the first row whose *field count* matches
    # the bulk of the rows below it — counted after parsing, so commas
    # inside quoted values ("$1,204,500") never masquerade as columns.
    skipped = _preamble_length(rows)
    if skipped:
        notes.append("skipped %d preamble line%s before the table (e.g. %r)"
                     % (skipped, "s" if skipped != 1 else "",
                        ", ".join(rows[0])[:48]))
        rows = rows[skipped:]
    return _from_row_major(rows, notes)


def _preamble_length(rows):
    """How many junk rows precede the real table."""
    widths = [len(r) for r in rows]
    if len(widths) < 3:
        return 0
    table_width = max(set(widths), key=widths.count)
    if table_width < 2 or widths.count(table_width) < 2:
        return 0
    first = widths.index(table_width)
    if first == 0:
        return 0
    # only believe it if the table really is the bulk of what follows
    rest = widths[first:]
    if rest.count(table_width) >= max(2, 0.6 * len(rest)):
        return first
    return 0


# -- classification -----------------------------------------------------------


def _classify(name, raw, notes, dtype=None):
    present = [(i, v) for i, v in enumerate(raw) if not is_missing(v)]
    n_missing = len(raw) - len(present)
    if not present:
        return Column(name, CATEGORY, [None] * len(raw), raw)

    if dtype == CATEGORY:
        return Column(name, CATEGORY,
                      [None if is_missing(v) else str(v).strip() for v in raw],
                      raw)
    if dtype == NUMBER:
        forced = _try_numbers(name, raw, present, notes, threshold=0.0)
        if forced is None:
            raise IngestError("dtypes said %r is a number, but not one value "
                              "parses as one (e.g. %r)"
                              % (name, present[0][1]))
        column, _rate, note = forced
        if note:
            notes.append(note)
        return column
    if dtype == TEMPORAL:
        forced = _try_temporal(name, raw, present, notes, threshold=0.0)
        if forced is None:
            raise IngestError("dtypes said %r is temporal, but not one value "
                              "parses as a date (e.g. %r)"
                              % (name, present[0][1]))
        column, _rate, note = forced
        if note:
            notes.append(note)
        return column

    if _looks_like_identifier(name, present):
        notes.append("column %r kept as text — its values are identifiers "
                     "(leading zeros would be lost as numbers)" % name)
        return Column(name, CATEGORY,
                      [None if is_missing(v) else str(v).strip() for v in raw],
                      raw)

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


def _looks_like_identifier(name, present):
    """Zip codes, account numbers, zero-padded keys: digits that aren't values.

    The tell is a leading zero — ``'02134'`` is not two thousand one hundred
    and thirty-four, and rendering it as one both changes the value and
    invents an axis.  Only fires when the column is *consistently* padded.
    """
    strings = [v.strip() for _i, v in present if isinstance(v, str)]
    if len(strings) < len(present) or not strings:
        return False
    padded = [s for s in strings if len(s) > 1 and s[0] == "0" and s.isdigit()]
    if not padded:
        return False
    if not all(s.isdigit() for s in strings):
        return False
    widths = {len(s) for s in strings}
    return len(padded) >= max(1, 0.25 * len(strings)) and len(widths) == 1


def _try_numbers(name, raw, present, notes, threshold=None):
    threshold = _CLASSIFY_THRESHOLD if threshold is None else threshold
    decimal_comma = any(proves_decimal_comma(v) for _i, v in present) \
        or any(proves_dot_thousands(v) for _i, v in present)
    parsed = [(i, parse_number(v, decimal_comma=decimal_comma))
              for i, v in present]
    hits = [(i, p) for i, p in parsed if p is not None]
    rate = len(hits) / len(present)
    # A four-value column with one typo would fail an 80% bar; short columns
    # get to lose exactly one value and still be numbers.
    floor = min(threshold, (len(present) - 1) / len(present)) \
        if len(present) < 8 else threshold
    if rate < floor or not hits:
        return None
    values = [None] * len(raw)
    for i, (v, _h) in hits:
        values[i] = v
    percent = sum(1 for _i, (_v, h) in hits if h.percent) > len(hits) / 2
    symbols = []
    for _i, (_v, h) in hits:
        if h.currency and h.currency not in symbols:
            symbols.append(h.currency)
    if len(symbols) > 1:
        currency = None      # dollars and euros are not commensurable
        notes.append("column %r mixes currencies (%s) — axis left unitless; "
                     "convert to one currency before charting"
                     % (name, ", ".join(symbols)))
    else:
        currency = symbols[0] if symbols else None
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


def _try_temporal(name, raw, present, notes, threshold=None):
    threshold = _CLASSIFY_THRESHOLD if threshold is None else threshold
    strings = [v for _i, v in present if isinstance(v, str)]
    dayfirst = False
    if strings:
        forced_day = sum(1 for v in strings
                         if _slash_first_component_over_12(v))
        ambiguous = [v for v in strings if temporal_ambiguous(v)]
        if forced_day:
            dayfirst = True
            if ambiguous:
                notes.append("column %r: read as day/month — a value like %r "
                             "can only be a day" % (name, next(
                                 v for v in strings
                                 if _slash_first_component_over_12(v))))
        elif ambiguous:
            dayfirst = _prefer_chronological(present)
            if dayfirst is None:
                dayfirst = True  # every value ambiguous: dd/mm is the
                #                  worldwide majority convention
                notes.append("column %r: dates like %r are ambiguous — "
                             "read as day/month (chronology gave no hint)"
                             % (name, ambiguous[0]))
            else:
                notes.append("column %r: dates like %r are ambiguous — read "
                             "as %s because only that order runs forward in "
                             "time" % (name, ambiguous[0],
                                       "day/month" if dayfirst
                                       else "month/day"))
    parsed = [(i, parse_temporal(v, dayfirst=dayfirst)) for i, v in present]
    hits = [(i, p) for i, p in parsed if p is not None]
    if not hits:
        return None
    rate = len(hits) / len(present)
    floor = min(threshold, (len(present) - 1) / len(present)) \
        if len(present) < 8 else threshold
    if rate < floor:
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
