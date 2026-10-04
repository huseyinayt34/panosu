# Score command: today's risk list without a database, K76-K80

Status: done (2026-10-04). Design decided by Claude under the owner's delegation. Item (3) of the gap review; the
core of the future Docker license package (Docker itself is a separate later step).

## Problem
The integration guide (`docs/entegrasyon.md`) promises a nightly "files in, risk list out" run on the firm's own
machine. Before this step the only way was the pilot command, which also runs the retrospective validation
(rolling cut-offs, 2,000 bootstrap resamples) and writes an HTML report on every run; and its `skorlar.csv` had no
model version.

## K76 A thin command over the pilot core
- New command `python -m servisler.skor` (`servisler/skor.py`). No new model path: input preparation is
  `pilot_dogrula._hazirla` (K30-K38 reading, mapping, whitelist, sensitive columns, 10% invalid-row stop), the
  computation is `pilot.guncel` (K68), the output is `pilot_dogrula.skorlar_csv`.
- Same arguments as the pilot command minus `--ad`; `--cikti` is a file path (default `skorlar.csv`).
- No validation, no report, no `esleme.json`; the mapping is printed on every run as in the pilot command.
- Does not import `database`/`config` (test); runs without `.env` and PostgreSQL.

## K77 Same list as the pilot
For the same files, `servisler.skor` and `servisler.pilot_dogrula` write byte-identical `skorlar.csv` (test). A firm
that validated the model in the pilot gets exactly that list in production.

## K78 Data day and model version on every row
`skorlar.csv` gets two trailing columns, in both commands: `Veri Günü` (L, the local date of the latest completed
check-in, K65) and `Model Sürümü` (`analitik.yenileme.MODEL_VERSIYONU`, now `mbgnbd-map-v3`). Per row rather than a
header line, so the file stays a plain table that imports into the firm's system without special handling. Columns
were appended at the end so readers that use the first ten columns by position keep working.

## K79 Atomic output, old list kept on error
The file is written to `<name>.yaziliyor` next to the target and renamed over it (`os.replace`). A reader never sees
a half-written list. On any error (mapping error exit 2, more than 10% invalid rows exit 1, no check-ins, fit not
converging) nothing is written and yesterday's list stays in place (test).

## K80 Stale export warning
If the data day is more than 2 days before the real today, the command prints a warning ("dışa aktarma güncel mi?")
but still writes the list: a firm that shifted all dates (K69) gets a valid list. `Veri Günü` lets the firm's system
detect a stale list on its side.

## Side fix
On Windows the pilot command wrote CSV lines as `\r\r\n` (the csv writer's `\r\n` plus text-mode newline
translation); Excel showed an empty row after every row. Both commands now write with `newline=""`.

## Files
`servisler/skor.py` (new), `servisler/pilot_dogrula.py` (two columns, newline fix), `tests/test_pilot.py` (3 new
tests; the header assertion of the pilot test now includes the two new columns). No new package, no migration.
