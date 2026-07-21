"""Value-level coercion: turning what people actually have into numbers.

Real exports are dirty.  Finance writes ``$1,234.50`` and ``(2,400)`` for
negatives; Europe writes ``1.234,56``; dashboards write ``45%`` and ``3.2M``;
databases leak ``NULL``, ``N/A``, ``—`` and empty cells.  matplotlib expects
you to have cleaned all of that before it will draw a line.  limn considers
it the chart library's job.

Two parsers live here — :func:`parse_number` and :func:`parse_temporal` —
plus the missing-value vocabulary.  Both return ``None`` for "not one of
mine" and never raise on strings.  Column-level judgement (is this column
numeric? day-first or month-first?) lives in ingest.py; these functions
only ever look at one value.
"""

import re
from datetime import date, datetime

MISSING_TOKENS = frozenset({
    "", "-", "--", "—", "–", "?", ".",
    "na", "n/a", "n.a.", "nan", "null", "none", "nil", "missing",
    "#n/a", "#na", "#value!", "#div/0!", "#ref!",
})

_CURRENCY_SYMBOLS = "$€£¥₹₩₽₺"
_CURRENCY_CODES = {
    "usd": "$", "eur": "€", "gbp": "£", "jpy": "¥",
    "chf": "CHF", "cad": "$", "aud": "$", "inr": "₹",
}
_SUFFIX_MULT = {"k": 1e3, "m": 1e6, "mm": 1e6, "mn": 1e6, "b": 1e9,
                "bn": 1e9, "t": 1e12, "tn": 1e12}


def is_missing(value):
    """The many spellings of nothing — including the un-plottable floats."""
    if value is None:
        return True
    if isinstance(value, float) and (value != value or value in (INF, -INF)):
        return True   # NaN and ±inf have no position on any axis
    if isinstance(value, str):
        return value.strip().casefold() in MISSING_TOKENS
    return False


class NumberHint:
    """What a numeric string wore: units survive parsing to style the axis."""

    __slots__ = ("percent", "currency")

    def __init__(self, percent=False, currency=None):
        self.percent = percent
        self.currency = currency

    def __repr__(self):
        return "NumberHint(percent=%r, currency=%r)" % (self.percent, self.currency)


_GROUPED_COMMA = re.compile(r"^\d{1,3}(,\d{3})+(\.\d+)?$")
# Two or more dot groups can only be thousands (1.234.567); ONE dot group is
# genuinely ambiguous — "1.085" is an FX rate far more often than it is a
# German thousand — so it needs column-level evidence.  See _parse_bare_number.
_GROUPED_DOT_MULTI = re.compile(r"^\d{1,3}(\.\d{3}){2,}(,\d+)?$")
_GROUPED_DOT_ONE = re.compile(r"^\d{1,3}\.\d{3}(,\d+)?$")
_GROUPED_DOT = re.compile(r"^\d{1,3}(\.\d{3})+(,\d+)?$")
_GROUPED_SPACE = re.compile(r"^\d{1,3}( \d{3})+([.,]\d+)?$")
_GROUPED_APOSTROPHE = re.compile(r"^\d{1,3}('\d{3})+([.,]\d+)?$")   # Swiss
_PLAIN = re.compile(r"^\d+$")
INF = float("inf")


def parse_number(value, decimal_comma=None):
    """Parse one messy numeric value.  Returns ``(float, NumberHint)`` or None.

    Handles currency symbols and codes, percent signs, thousands separators
    in US (``1,234.5``), European (``1.234,5``) and SI (``1 234,5``) styles,
    accounting negatives ``(1,234)``, unicode minus, and order-of-magnitude
    suffixes (``3.2M``, ``150k``, ``1.4bn``).

    *decimal_comma* resolves the one genuinely ambiguous case: a single
    comma with exactly three trailing digits (``1,234``).  ``None`` means
    "assume thousands"; ingest.py re-parses a whole column with ``True``
    when any of its values proves European style (e.g. ``3,14``).
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        if value != value:
            return None
        return float(value), NumberHint()
    if not isinstance(value, str):
        return None

    # U+00A0 no-break, U+202F narrow no-break, U+2009 thin — all group digits
    s = (value.strip().replace("−", "-")
         .replace(" ", " ").replace(" ", " ").replace(" ", " "))
    if s.casefold() in MISSING_TOKENS:
        return None
    hint = NumberHint()

    negative = False
    # Excel's accounting export puts the symbol outside the parens: $(2,400)
    s, hint.currency = _strip_currency(s, hint.currency)
    if s.startswith("(") and s.endswith(")"):
        s, negative = s[1:-1].strip(), True
    if s.startswith("-"):
        s, negative = s[1:].strip(), not negative
    elif s.startswith("+"):
        s = s[1:].strip()

    if s.endswith("%"):
        hint.percent = True
        s = s[:-1].strip()

    s, hint.currency = _strip_currency(s, hint.currency)

    if s.endswith("%"):  # a percent that was hiding behind a currency code
        hint.percent = True
        s = s[:-1].strip()

    mult = 1.0
    low = s.casefold()
    for suf in ("bn", "tn", "mm", "mn", "k", "m", "b", "t"):
        if low.endswith(suf) and len(s) > len(suf):
            body = s[: -len(suf)]
            # "3.2M" is a magnitude; "5 m" is five metres — a real suffix is
            # written flush against its number, a unit is spaced off it.
            if body[-1:].isspace():
                break
            if body and (body[-1].isdigit() or body[-1] in ".,"):
                mult = _SUFFIX_MULT[suf]
                s = body
                break

    parsed = _parse_bare_number(s, decimal_comma)
    if parsed is None:
        return None
    result = parsed * mult
    if result in (INF, -INF) or result != result:
        return None     # 1e400 and friends have no place on an axis
    return (-result if negative else result), hint


def _strip_currency(s, found):
    """Peel one currency symbol or ISO code off either end of *s*."""
    for sym in _CURRENCY_SYMBOLS:
        if s.startswith(sym) or s.endswith(sym):
            return s.strip(sym).strip(), (found or sym)
    head = s[:3].casefold()
    if head in _CURRENCY_CODES and (len(s) == 3 or s[3] in " 0123456789(-+"):
        return s[3:].strip(), (found or _CURRENCY_CODES[head])
    if len(s) > 3 and s[-3:].casefold() in _CURRENCY_CODES:
        return s[:-3].strip(), (found or _CURRENCY_CODES[s[-3:].casefold()])
    return s, found


def _parse_bare_number(s, decimal_comma):
    """Digits and separators only; separator style is validated, not guessed.

    The one dangerous ambiguity is a *single* dot group: ``1.085`` is an FX
    rate, a latency, or a batting average far more often than it is a German
    thousand.  It is only read as thousands when the column proved European
    style (*decimal_comma*) — otherwise a plain float, so ``0.125`` stays
    an eighth instead of becoming a hundred and twenty-five.
    """
    if not s:
        return None
    if decimal_comma and s.count(",") == 1 and "." not in s:
        head, _, tail = s.partition(",")   # column-level European evidence
        if _PLAIN.match(head or "0") and _PLAIN.match(tail):
            return float(head + "." + tail)
    if _GROUPED_COMMA.match(s):            # 1,234,567.89
        return float(s.replace(",", ""))
    if _GROUPED_APOSTROPHE.match(s):       # 1'234'567.89 (Swiss)
        return float(s.replace("'", "").replace(",", "."))
    if _GROUPED_DOT_MULTI.match(s):        # 1.234.567,89 — unambiguous
        return float(s.replace(".", "").replace(",", "."))
    if _GROUPED_DOT_ONE.match(s):          # 1.085 — ambiguous, needs evidence
        if decimal_comma or "," in s:
            return float(s.replace(".", "").replace(",", "."))
        return float(s)                    # a plain decimal, left alone
    if _GROUPED_SPACE.match(s):            # 1 234 567,89
        return float(s.replace(" ", "").replace(",", "."))
    if "," in s and "." not in s:
        head, _, tail = s.partition(",")
        if "," not in tail and _PLAIN.match(head or "0") and _PLAIN.match(tail):
            if len(tail) == 3 and not decimal_comma:
                return float(head + tail)   # 1,234 -> thousands by default
            return float(head + "." + tail)  # 3,14 -> decimal comma
        return None
    if s.strip().casefold().lstrip("+-") in ("inf", "infinity"):
        return None                        # not a plottable position
    try:
        return float(s)
    except ValueError:
        return None


def proves_dot_thousands(value):
    """True when a string can only be read dot-as-thousands (``1.234.567``).

    The mirror of :func:`proves_decimal_comma`: it lets a column that
    contains one unambiguous German number reinterpret its ambiguous
    ``1.085`` siblings as thousands.
    """
    if not isinstance(value, str):
        return False
    s, _cur = _strip_currency(value.strip().strip("()+-%").strip(), None)
    return bool(_GROUPED_DOT_MULTI.match(s)
                or (_GROUPED_DOT_ONE.match(s) and "," in s))


def proves_decimal_comma(value):
    """True when a string can only be read comma-as-decimal (e.g. ``3,14``)."""
    if not isinstance(value, str):
        return False
    s = value.strip().strip("()+-%").strip()
    for sym in _CURRENCY_SYMBOLS:
        s = s.strip(sym).strip()
    if _GROUPED_DOT.match(s) or _GROUPED_SPACE.match(s):
        return "," in s
    head, comma, tail = s.partition(",")
    return bool(comma) and "," not in tail and "." not in s \
        and _PLAIN.match(head or "0") is not None \
        and _PLAIN.match(tail) is not None and len(tail) != 3


def _naive(dt):
    """Every datetime limn stores is naive UTC.

    Mixing aware and naive datetimes in one column makes them mutually
    incomparable, and the tick machinery does arithmetic on them — so an
    offset is applied and dropped here, at the door, rather than crashing
    three layers down.
    """
    if dt.tzinfo is None:
        return dt
    return (dt - dt.utcoffset()).replace(tzinfo=None)


_ISO_TZ = re.compile(r"[zZ]$")
_SLASHED = re.compile(r"^(\d{1,4})[/.\-](\d{1,2})[/.\-](\d{1,4})$")

_NAMED_FORMATS = (
    "%Y-%m", "%Y/%m",       # month keys: the lingua franca of exports
    "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y",
    "%b %d %Y", "%B %d %Y", "%b %Y", "%B %Y", "%Y %b", "%Y %B",
)


def parse_temporal(value, dayfirst=False):
    """Parse one date-ish value to ``datetime``.  Returns None if it isn't one.

    ISO 8601 first (the one true format), then named-month forms
    (``Mar 3, 2026``, ``3 March 2026``, ``Mar 2026``), then slashed or
    dotted triples, where *dayfirst* settles ``07/10/2026``.  Bare numbers
    are never dates here — a column of ``2019, 2020, 2021`` plots more
    honestly as numbers than as guessed timestamps.
    """
    if isinstance(value, datetime):
        return _naive(value)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s or s.casefold() in MISSING_TOKENS:
        return None

    iso = _ISO_TZ.sub("+00:00", s)
    try:
        return _naive(datetime.fromisoformat(iso))
    except ValueError:
        pass

    for fmt in _NAMED_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    m = _SLASHED.match(s)
    if m:
        a, b, c = (int(g) for g in m.groups())
        if len(m.group(1)) == 4:                      # 2026/07/10
            y, mo, d = a, b, c
        else:
            y = c if c > 99 else (2000 + c if c < 70 else 1900 + c)
            first, second = a, b
            if first > 12 and second <= 12:
                d, mo = first, second
            elif second > 12 and first <= 12:
                mo, d = first, second
            elif dayfirst:
                d, mo = first, second
            else:
                mo, d = first, second
        try:
            return datetime(y, mo, d)
        except ValueError:
            return None
    return None


def temporal_ambiguous(value):
    """True for slashed dates where day/month cannot be told apart."""
    if not isinstance(value, str):
        return False
    m = _SLASHED.match(value.strip())
    if not m or len(m.group(1)) == 4:
        return False
    a, b = int(m.group(1)), int(m.group(2))
    return a <= 12 and b <= 12 and a != b
