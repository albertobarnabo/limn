# How ingestion thinks

limn's founding grievance: every chart library assumes clean, typed
columns, and real exports are never clean. So the front door does what
you would have done by hand — and tells you what it did.

## The pipeline

1. **Shape detection.** Path / CSV text / file object / list of dicts /
   dict of lists / rows / plain sequence / DataFrame-duck / generator.
   CSV delimiters (`,` `;` `\t` `|`) are sniffed; header rows are
   detected by comparing first-row types against the body.
2. **Column classification.** Every value in a column is tried — not
   just the first. A column is *numeric* or *temporal* when ≥ 80% of its
   non-missing values parse; the stragglers become missing values plus a
   note naming an example. Otherwise it's a *category*.
3. **Unit hints survive.** A column that arrived as `45%` keeps percent
   formatting on its axis; `$1,234` keeps its currency symbol. Units are
   part of the data's meaning, not dirt to scrub off.

## What the value parsers accept

| Input | Reading |
|---|---|
| `1234`, `-3.5`, `1e3`, `+7` | plain numbers |
| `1,234,567.89` | US grouping |
| `1.234.567,89` | European grouping |
| `1 234 567,89` | SI/French grouping |
| `3,14` | decimal comma — *when the column proves it* |
| `$1,204` · `€99` · `1234 EUR` · `USD 5.5` | currency, symbol kept |
| `45%` · `3.2 %` | percent, unit kept |
| `(1,234)` · `($500)` | accounting negatives |
| `−12` | unicode minus |
| `150k` · `3.2M` · `1.4bn` · `7T` | magnitude suffixes |
| `2026-07-10` · `2026-07-10T14:30:00Z` | ISO 8601 |
| `2024-01` · `2024/07` | month keys |
| `Mar 3, 2026` · `3 March 2026` · `Mar 2026` | named months |
| `10/07/2026` · `10.07.2026` · `1/2/26` | slashed/dotted dates (see below) |
| `""` · `N/A` · `null` · `—` · `NaN` · `#N/A` … | missing |

Grouping is *validated*, not guessed: `1,23,4` and `12.34.56` are not
numbers and won't silently become them.

## The two judgement calls (and how they're made)

**Decimal commas.** `1,234` alone is ambiguous. limn reads it as
thousands — unless any value in the same column proves European style
(like `3,14` or `1.234,56`), in which case the whole column is re-read
comma-as-decimal, with a note.

**Day-first dates.** `07/10/2026` has no true reading. Per column: if
any value forces day-first (`13/02/…`), the column is day-first; if
every value is ambiguous, the reading that makes the column
chronological wins; failing that, day-first (the worldwide majority
convention) with a note.

## Missing values

`None`, `NaN`, and the empty spellings become gaps: a **visible break**
in a line (never interpolated), a skipped point in a scatter, a zero
contribution in a stack, an absent bar. Each gets one collective note.

## The contract

**Values never raise.** Only structure does — and loudly, with the
available alternatives listed:

- empty input, or a column name that doesn't exist,
- no numeric column to plot,
- a log axis with no positive values,
- a figure too small to fit its own labels.

Everything else is coped with and reported: `fig.notes` in code, stderr
on `save()`, once.
