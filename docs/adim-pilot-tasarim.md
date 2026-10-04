# Pilot step: validation report and score list without a database, K64-K71

Status: done (2026-10-04). Design decided by Claude under the owner's delegation ("sen karar ver"). This is the
code half of the pilot kit; the firm-facing data guide and the run plan live outside the repo (project files,
`panosu/pilot-kiti/`). It implements 4b-2 (K40, real-data validation) and is the core of the "score command" of the
license package (Docker wrapper later).

## Problem
The pilot promise to a studio software firm is: "send one studio's anonymous data, get a report showing how
accurate the model is on your data". Before this step: `servisler.ice_aktar`, `yenileme_calistir` and
`rapor_uret` only run on `_demo`/`_test` databases, there was no validation code for real data (K40 open), and the
outputs (panel, weekly report) are keyed by name and phone, which the pilot never receives.

## K64 Pilot runs in memory, without a database
- New pure core `servisler/pilot.py` and command `python -m servisler.pilot_dogrula`.
- Input: package file + check-in file(s) only. No member file: names, phones, e-mails are never needed. Files are
  read with the import core (`servisler.ice_aktarma`: K30 formats, K31 mapping and `--esleme`, K34 whitelist and
  sensitive columns, K37 parsing, K38 10% invalid-row stop) in anonymous mode.
- Nothing is written to any database; the input files are not copied. No database lock is relaxed.
- The command does not import `database`/`config`, so it runs without `.env` and PostgreSQL (test). A firm can run
  it on its own machine and send back only the report.

## K65 Data day and rolling cut-offs
- Data day L = local date of the latest completed check-in (not the real today). The package status rule of the
  import ("aktif if end ≥ today") uses L, so data whose dates were all shifted back still gets correct statuses.
- Cut-offs: C₀ = L − 90 (H = 90 confirms K40), then every 90 days back, at most 4, each earlier one only if at
  least 180 days of history precede it. At each cut-off the model is fitted again with check-ins up to the end of
  that local day only. Rolling cut-offs multiply the evaluated packages (one 90-day window of a 160-member studio
  gave 58 packages and 8 non-renewals, AUC interval 0.38-0.82; four windows gave 241 and 27).

## K66 Evaluation set and outcome
- At cut-off C: each member's latest non-cancelled package started on or before C, with an end date in
  (C, C + 60] (backtest S6 horizon). Entry packages without an end date have no observable end and are only
  counted (`dislanan_bitissiz`). File status is ignored at C except "iptal" (status is as of L).
- Renewed = the member has another non-cancelled package starting in (C, end + 30]. 60 + 30 = 90, so every outcome
  is observable by L and windows of different cut-offs do not overlap.
- Scoring is the production computation (`yenileme_hesapla`): same features, MAP fit, exact P(renewal) (v3),
  4-decimal rounding, Riskteki Para, "why risky" sentence; remaining entries count check-ins up to C only. A
  database test checks equality with `yenileme_hesapla` on the same imported data.

## K67 Metrics
- AUC of P(renewal) vs renewed; 95% percentile bootstrap interval, 2,000 resamples, fixed seed, members resampled
  with all their packages (a member can appear at several cut-offs).
- Baseline rule from backtest S6: at most 1 check-in in the last 21 days → will not renew (0/1 score), its AUC.
- Calibration: 5 equal-count groups, mean predicted vs observed renewal. Brier score kept in the result.
- Top 10 riskiest: how many did not renew, vs the expected count of a random 10 ((1 − renewal rate) × 10).
- Riskteki Para: Σ (1 − P) × price vs realized loss Σ price of non-renewed packages.
- Warnings: fewer than 30 evaluated packages; less than 365 days of history before C₀.

## K68 Today's list
On day L: each member's latest package that is not "iptal"/"bitti"/"donduruldu" and has no end date or an end date
≥ L, scored as above, sorted by Riskteki Para. Output keyed by the firm's own member code, so the firm maps it back
to names on its side. Frozen packages are counted, not scored.

## K69 Time-shift invariance
The model uses only time differences (x, t_x, T, windows, ages), and L comes from the data, so shifting every date
in both files by the same number of days changes nothing (test). The data guide offers this to firms as an extra
anonymization step.

## K70 Report wording
`pilot-raporu.html` (Turkish, A4 printable, same style as the weekly report). One reading sentence by band of the
displayed (2-decimal) AUC: interval lower bound ≤ 0.50 → "uncertain, not enough non-renewals"; ≥ 0.80 strong;
≥ 0.70 good; ≥ 0.60 moderate (use as an order, not a verdict); below → "could not tell apart; we do not hide it".
Plus the comparison with the baseline rule and a note when the interval is wider than 0.20. Limitations are always
printed (behavior only, not calibrated on real renewals yet, one studio).

## K71 Outputs and limits
`raporlar/pilot/<kaynak>/` (gitignored): `pilot-raporu.html`, `dogrulama.csv` (every evaluated package with its
cut-off, P, reason and outcome; lets the firm check the report against its own records), `skorlar.csv` (today's
list), `esleme.json` (mapping used). CSVs: ";" and utf-8-sig for Turkish Excel. Several check-in files may be given
(one file is limited to 50,000 rows and 5 MB, K39); identical derived ids across files count once. Exit codes: 2
mapping error, 1 more than 10% invalid rows; no output is written in either case.

## Results on synthetic data (cloud, Python 3.13, 2026-10-04)
| Data | Packages (not renewed) | AUC [95%] | Rule AUC | Top 10 not renewed |
|---|---|---|---|---|
| S6 generator, 250 members, seeds 0-3 | 126-170 | 0.79-0.86, lower bounds 0.70-0.78 | 0.71-0.74 | 10/10 |
| [DEMO] Denge Pilates export (400 members) | 536 (72) | 0.74 [0.66, 0.81] | 0.67 | 10/10 |
| [DEMO] Butik Reformer export (163 members) | 241 (27) | 0.69 [0.56, 0.81] | 0.64 | 10/10 |

Butik is weaker because its generator drops members almost only at random (p ~ Beta(1, 290), 5% random
non-renewal): non-renewals there are mostly not visible in behavior, which is exactly what a real pilot must
measure.

## Files
`servisler/pilot.py`, `servisler/pilot_dogrula.py`, `sablonlar/pilot_raporu.html`, `tests/test_pilot.py`
(12 tests; one uses panosu_test). No new package, no migration.
