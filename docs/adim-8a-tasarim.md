# Step 8a: cold start, minimum-data guard and the firm-side image, K81-K88

Status: done (2026-10-10). Owner decisions (2026-10-10): data threshold 30 repeat members and 60 days; method
empirical Bayes; build the Docker image. Everything else below was decided by Claude and is listed so the owner can
change it.

## Problem
1. Minimum-data guard (open issue since the (μ, κ) fix, math report 10.4): when almost every member has one visit
   or the history is a few days long, the MAP fit returns confident but meaningless parameters.
2. Cold start (roadmap 8a): a new studio has little history, so its own data cannot pin down the four parameters.
3. The landing page and the integration guide promised a Docker package so a firm can run the tools without
   installing Python.

## K81 Data threshold (owner)
A business has enough data when at least **30 members have a repeat visit** (x ≥ 1) **and** the history is at least
**60 days** (the oldest member's T). `analitik.soguk_baslangic.veri_yeterli`. Above the threshold nothing changes:
same weak prior, same fit, bit-identical results, version `mbgnbd-map-v3` (test).

## K82 Learned prior replaces the weak prior below the threshold
Below the threshold the MAP objective uses an independent normal prior on all four directions of
θ = (ln m, ln r, logit μ, ln κ) instead of the weak prior on (ln r, ln κ). The optimizer starts at the prior center
(plus the usual second start). Because the prior is fixed and the likelihood grows with every member, the estimate
moves from the prior toward the business's own data as data arrives (Bayesian update; test: the gap to the
weak-prior fit shrinks by more than 3x from 20 to 1 500 members).

## K83 "Ön tahmin" label
Rows computed below the threshold carry model version `mbgnbd-onsel-v1`. No schema change: `model_versiyonu` is
already stored per row and the panel views pick the latest row per package regardless of version.
- Panel (riskli and sessiz tables) and the weekly report show "Ön tahmin: işletmenizin verisi henüz az ..." when the
  business's latest computation used this version (`yenileme_servisi.on_tahmin_mi`).
- Pilot: every `skorlar.csv` row has its own version (was one constant), the report adds a warning when a cut-off
  was below the threshold and a note under today's list; the score command prints a note.

## K84 Empirical Bayes prior and where it comes from
Each business is fitted on its own with the usual MAP (weak prior, all history). Prior center = mean of the fitted
θ across businesses; spread = sample standard deviation (ddof = 1) clipped to [0.5, 2.0] per direction (with few
businesses a sample spread can be near 0, which would make the prior overconfident; above 2.0 it would be weaker
than the weak prior). `analitik.soguk_baslangic.onsel_ogren`.

Today there are no real businesses, so the prior is learned from the 5 [DEMO] businesses (synthetic, generated in
memory with the demo settings): `python -m backtest.soguk_baslangic ogren`. The result is stored as constants
(`OGRENILMIS_ONSEL`); a test regenerates it.

| Business | ln m | ln r | logit μ | ln κ |
|---|---|---|---|---|
| [DEMO] Usta Berber | -3.0029 | 1.2794 | -3.0971 | 3.2262 |
| [DEMO] Nazlı Kuaför | -3.6022 | 1.0753 | -2.7753 | 2.4923 |
| [DEMO] Işıltı Güzellik Merkezi | -3.3177 | 0.6593 | -2.9461 | 3.6321 |
| [DEMO] Denge Pilates Stüdyosu | -1.5969 | 1.4853 | -4.1542 | 3.6803 |
| [DEMO] Butik Reformer | -0.8746 | 1.0319 | -5.0242 | 5.5591 |
| **Prior center** | -2.4789 | 1.1062 | -3.5994 | 3.7180 |
| **Prior spread** | 1.1823 | 0.5000 (clipped) | 0.9612 | 1.1338 |

When real businesses exist, the same function learns the prior from their fitted parameters (four numbers per
business, no member data). Using another firm's parameters needs that firm's written consent (data processing
agreement); until then the synthetic prior stays.

## K85 Young-studio backtest
`python -m backtest.soguk_baslangic degerlendir` (40 seeds). Backtest S6 generator; a studio that opened h days
before the cut-off C (only members acquired in (C - h, C] exist); packages ending in (C, C + 60] scored with both
priors on the same data, pooled over seeds. The S6 generator is not one of the 5 businesses the prior was learned
from.

| Studio | Age (days) | Packages | Below threshold | Repeat members | AUC weak / learned | Brier weak / learned | Riskteki Para error % weak / learned |
|---|---|---|---|---|---|---|---|
| S6 rate (~2 new members/day) | 20 | 987 | 100% | 30 | 0.580 / 0.663 | 0.342 / 0.294 | -84 / -68 |
| | 40 | 2119 | 100% | 71 | 0.687 / 0.701 | 0.265 / 0.259 | -51 / -48 |
| | 60 | 3128 | 100% | 109 | 0.777 / 0.777 | 0.208 / 0.207 | -31 / -30 |
| | 90 | 4362 | 0% | 168 | 0.823 / 0.824 | 0.170 / 0.170 | -19 / -18 |
| Small studio (300 members / 2 years) | 30 | 298 | 100% | 10 | 0.598 / 0.735 | 0.308 / 0.261 | -59 / -56 |
| | 60 | 600 | 100% | 22 | 0.751 / 0.759 | 0.211 / 0.209 | -34 / -34 |
| | 90 | 901 | 25% | 35 | 0.813 / 0.814 | 0.172 / 0.172 | -20 / -19 |
| | 180 | 1372 | 0% | 69 | 0.807 / 0.805 | 0.168 / 0.168 | -13 / -13 |

Reading: in the first month the learned prior clearly helps (AUC +0.08 to +0.14, Brier lower); from about two
months on both priors agree, so switching to the weak prior at the threshold costs nothing. In young studios the
model underestimates the loss (Riskteki Para error strongly negative): with a short history P(alive) is high for
almost everyone. The "ön tahmin" label is there for exactly this.

Limitations: synthetic data only; the prior comes from 5 synthetic businesses (3 of them non-studio); the threshold
is a hard switch (small jump in estimates when crossed, negligible per the table above).

## K86 Firm-side image `Dockerfile.pilot`
- Runs `servisler.skor` and `servisler.pilot_dogrula` with no Python install, no database, no `.env`.
- Installs only what the two commands import (numpy, scipy, Jinja2, MarkupSafe, tzdata, openpyxl, et_xmlfile).
- Build straight from GitHub (no clone):
  `docker build -t ritmeva-pilot -f Dockerfile.pilot https://github.com/huseyinayt34/panosu.git`
- Run in the folder with the export files: `docker run --rm --network none -v "${PWD}:/veri" ritmeva-pilot
  servisler.skor --kaynak studyo --paketler paketler.csv --girisler girisler.csv`. Working directory is the mounted
  folder, so outputs land next to the inputs. `--network none` removes the network: the data cannot leave (KVKK).
- Non-root user (uid 10001). On Linux add `--user "$(id -u):$(id -g)"` so the container can write to the folder.

## K87 Pinned versions
The image pins the same versions as `requirements*.txt` (test `test_pilot_imaji_surumleri_requirements_ile_ayni`).

## K88 CI builds and runs the image
New job `pilot-imaji` in `.github/workflows/testler.yml`: builds the image, generates a synthetic S6 studio inside it,
runs both commands with `--network none`, and checks that the score list equals the pilot's list (K77). No Docker on
the owner's machine is needed. Free on a public repository.

## Files
New: `analitik/soguk_baslangic.py`, `backtest/soguk_baslangic.py`, `Dockerfile.pilot`, `tests/test_soguk_baslangic.py`,
this document. Changed: `analitik/bgnbd.py` (Onsel), `analitik/mbgnbd.py` (fit takes an optional prior),
`servisler/yenileme_servisi.py`, `servisler/pilot.py`, `servisler/pilot_dogrula.py`, `servisler/skor.py`,
`servisler/risk_listeleri.py`, panel/report/pilot templates, tests (`test_pilot.py`, `test_yenileme_servisi.py`,
`test_web.py`), `.github/workflows/testler.yml`, docs. No new package, no migration.
