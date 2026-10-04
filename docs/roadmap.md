Moved from CLAUDE.md on 2026-10-03. CLAUDE.md links here.

# Panosu: roadmap detail

The single source of the roadmap is the table in CLAUDE.md; README gives only a short summary. The Status column
below is a snapshot as of 2026-10-03; the current status lives in CLAUDE.md.

## Roadmap (full rows)
| # | Step | Status |
|---|---|---|
| 1 | Security lock (RLS, guard tests) | Done |
| 2 | Alembic baseline | Done |
| 3 | Customer API | Done |
| 4a | Services + visits API, synthetic data engine (writes only to _demo databases) | Done |
| 5a | Model library: V1, BG/NBD, MBG/NBD, Gamma-Gamma, Riskteki Para (no database; design: `docs/adim-5-6-tasarim.md`) | Done |
| 6 | Backtest: comparison of V1, BG/NBD and MBG/NBD on synthetic data (S0–S5) (ROC AUC, calibration); result: `docs/backtest-sonuclari.md` | Done |
| 5b | Contract membership (packages), renewal risk (M3 + simulation), S6 backtest, panel endpoint (`docs/adim-5b-tasarim.md`) | Done |
| 5c | Calibration of the renewal model with real renewal data (when Faz 0 data arrives). Hypotheses to test (owner's observation): (1) the renewal rate ρ of active members is above 90%; (2) the number of previous renewals is a strong predictor of renewal; (3) there is a group that comes rarely yet still renews, and the model may be giving them false alarms. Riskteki Para coming out 13% low in S6 is caused by the ρ = 1 assumption. | Waiting |
| 7 | Panel: silent members, revenue and profit summary (expenses, break-even), weekly report (`docs/adim-7-tasarim.md`). For a past month the break-even gap uses the month average (K2, `docs/adim-9-tasarim.md`) | Done |
| 4b | CSV/Excel import (`docs/adim-4b-tasarim.md`; does not depend on 8). Note: on import, check-in visits must have amount 0; otherwise package revenue is counted twice. | 4b-1 Done (CSV/Excel import core, command, export, round-trip test); 4b-2 real-data validation and 4b-3 web screen pending |
| 8 | Real authentication + business sign-up: Argon2id + JWT, single-use refresh token, invite codes (`docs/adim-8-tasarim.md`). The live `panosu` migration awaits separate approval. | Done |
| 8a | Cold-start mode (before 9; plan only): in a business with little history, MBG/NBD parameters start from a prior learned from other businesses or from synthetic data and are updated in a Bayesian way as the business's data arrives. During this period the panel shows predictions with the label 'ön tahmin' (preliminary estimate). | Planned |
| 8b | Automatic calculation (before 9; plan only): the finance panel is recalculated instantly on every data entry, renewal risks automatically every night. (Nightly refresh for the demo was done in 9c; real businesses pending) | Planned |
| 9 | Web panel (Jinja + HTMX, inside FastAPI; `docs/adim-9-tasarim.md`), live demo with panosu_demo | Done |
| 10 | Consent, messaging, win-back measurement | Planned |
| 11 | Deployment: Docker, CI, server, strong and distinct passwords, payments (`docs/adim-11-tasarim.md`) | Done (minimum release 2026-10-02: https://panosu.onrender.com; payments later) |
| — | Model fix (μ, κ): MAP, weak prior, central difference, two starts (`docs/adim-mu-kappa-tasarim.md`) | Done |
| — | Math report: model, MAP and weak identifiability, simulation, validation, limitations (`docs/matematik-raporu.md`) | Done |
| — | Ritmeva brand + public landing page (`docs/adim-ritmeva-tasarim.md`) | Done |

## Development ideas (not decisions; designed in the relevant step)
- Step 4b: AI-suggested CSV column mapping; extracting a table from a photo of the attendance book.
- Step 10: messaging with control groups and uplift measurement; not disturbing the "sleeping dogs" (members who pay
  but rarely come); causal evidence of win-back.
- Step 8a: hierarchical Bayesian priors across businesses.
- After step 11: Score API for software companies.
- Integration guide for software firms (Turkish, firm-facing): `docs/entegrasyon.md`. The score command and the
  Docker license package it describes as planned are not built yet.

## Research shelf (if time allows)
- RFM/cohort, survival analysis (Kaplan-Meier, Cox), XGBoost + SHAP, campaign simulator / A-B power analysis.
  - Cafe/restaurant module (extracting products from a menu photo, menu engineering, inflation/margin alarm). Start
    condition: the studio product runs in at least one real studio and a cafe can provide product-level sales data.
  - Veterinary clinics: vaccination/check-up cycle (to be evaluated later).

## Other notes
- Faz 0: demand and data-format interviews with businesses. Not code; the owner runs it.
- Math decisions (model choice, assumptions) belong to the owner. Approved design of 5a/6: `docs/adim-5-6-tasarim.md`;
  approved design of 5b: `docs/adim-5b-tasarim.md` (M3 went into the product).
- Reports are saved in the raporlar/ folder; this folder is not tracked by git.

## Closed issues
- Closed (2026-10-03): the root cause of the intermittent failure of
  test_demo_tazele.py::test_denetim_kayitlari_degismez was the a,b ridge; fixed by the (μ, κ) reparametrization +
  weak prior (MAP), passes 20/20, backtest regenerated (`docs/adim-mu-kappa-tasarim.md`).
- Closed (2026-10-04): Monte Carlo noise in P(yenileme) (about ±0.5 points per package; 0 for very silent members)
  replaced by the exact formula, model version mbgnbd-map-v3 (K61, `docs/adim-rao-blackwell-tasarim.md`).
