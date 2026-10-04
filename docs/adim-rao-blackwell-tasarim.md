# Exact renewal probability (Rao-Blackwell step), K61-K63

Status: done (2026-10-04). Design approved by delegation (owner chose "do Rao-Blackwell as its own step").

## Problem
`analitik/yenileme.py` estimated P(renewal) with 2,000 Monte Carlo draws per package. Two coin flips per draw
("alive now?", "survived every visit?") plus random λ, p, K made each package's value noisy:
per-package sd ≈ 0.005 (Denge 0.0055, Butik 0.0048, 20 seeds, cloud demo build 2026-10-04). A member with
p_alive ≈ 1e-4 could get p_renewal exactly 0 (the K60 bug's trigger). Results depended on a seed tied to the
calculation date, so nightly date shifts moved p_renewal by noise.

## K61 Exact formula instead of simulation (full Rao-Blackwellization)
Rao-Blackwell: replacing a random draw by its conditional expectation never increases variance. Applying it to
"alive now" gives p_alive × mean((1−p)^K) (the first proposal, sd ≈ 0.001). Going all the way, λ, p and K can be
integrated out in closed form because the priors are conjugate, so the variance is exactly zero:

With s = r + x, β = α + T, M(k) = E[(1−p)^k] = B(a, b+x+1+k) / B(a, b+x+1):
- Duration-based, window D: E[e^(−λpD)] = E_p[(1 + pD/β)^(−s)] = ₂F₁(s, a; a+b+x+1; −D/β).
  Step 1 Gamma moment generating function, step 2 Euler's integral for ₂F₁. Evaluated after the Pfaff transform
  ₂F₁(s, a; c; z) = (1−z)^(−a) ₂F₁(c−s, a; c; z/(z−1)) so the argument lies in [0, 1).
- Entry-based, no expiry: M(R).
- Entry-based with expiry E: integrating λ out of Poisson(λE) gives K ~ NBD(s, θ = β/(β+E));
  E[(1−p)^min(K,R)] = Σ_{k<R} P(K=k)·M(k) + P(K≥R)·M(R).
- Window ≤ 0 or remaining entries ≤ 0: p_alive (unchanged rule).
P(renewal) = p_alive × the factor above, clipped to [0, p_alive].

Checks (cloud prototype, Python 3.13, numpy 2.5.2, scipy 1.18.1):
- 300 random parameter sets over wide ranges vs Monte Carlo n = 200,000: max |z| = 3.7 (expected max of 300
  normals ≈ 3); duration formula vs 1-D quadrature: max abs diff 4.6e-11.
- The two existing closed-form tests in tests/test_yenileme.py (dblquad, Beta ratio) are special cases.
- The math report said "no closed form exists" (section 5); that was wrong, and is corrected.

## K62 Version and code shape
- MODEL_VERSIYONU "mbgnbd-map-v3". Views take the newest row per package (hesaplama_tarihi, hesaplanma_zamani), so
  v2 and v3 rows can coexist; the panel shows v3 from the first v3 calculation.
- New `kesin_yenileme(p_hayatta_simdi, prm, x, T, *, pencere_gun, kalan_hak=None)`; `yenileme_olasiligi` loses the
  `tohum` and `n` parameters and calls it. `simule_et`, `tohum_turet`, `SIMULASYON_SAYISI` stay as the reference
  Monte Carlo used by tests. Callers (servisler/yenileme_servisi.py, backtest/calistir.py) drop the seed.
- No new package (scipy.special.hyp2f1, betaln; scipy.stats.nbinom). No migration.

## K63 "Why risky" split threshold stays
q = p_renewal / p_alive is now exact, so the Monte Carlo reason for AYRISTIRMA_MIN_P_AKTIF = 0.05 is gone, but q is
still computed from values stored with 4 decimals (numeric(5,4)); far below 5% that ratio is meaningless
(0.0002 → q from 0.0000/0.0002). Threshold and panel behaviour unchanged; only the comment's rationale changes.
SESSIZ_ESIK (K60) is a product rule and stays.

## Results (owner's Windows machine, 2026-10-04; identical to the cloud prototype)
- Backtest S6, M3-sim, 20 seeds, v2 (Monte Carlo) → v3 (exact), means at full precision:

| Segment | AUC | Brier | Riskteki Para error % |
|---|---|---|---|
| All | 0.8271 → 0.8272 | 0.1534 → 0.1534 | −13.186 → −13.194 |
| 1 month | 0.7098 → 0.7108 | 0.1874 → 0.1874 | −30.73 → −30.76 |
| 3 months | 0.8841 → 0.8848 | 0.1248 → 0.1246 | −9.99 → −9.98 |
| 6 months | 0.9510 → 0.9503 | 0.0850 → 0.0850 | −7.12 → −7.13 |
| 12 entries | 0.8144 → 0.8129 | 0.1612 → 0.1614 | −18.36 → −18.31 |

  Rule baseline and data rows unchanged. README / math report claims (AUC 0.83, about −13%) hold. S6 runtime
  22.7 s → 5.6 s.
- Demo, 2026-10-04, 45-day Riskteki Para: Butik Reformer 22,359.40 → 22,051.95 TL (−1.38%); Denge Pilates
  80,128.00 → 79,798.70 TL (−0.41%); package counts 55 and 156 unchanged. Both changes are inside the old noise
  (20-seed sd of the v2 total: Butik ±200 TL, Denge ±283 TL). Top 10: Denge identical; Butik two adjacent swaps
  (ranks 5↔6, 9↔10).
- Per package |v3 − v2|: max 0.023 / mean 0.004 (Butik), max 0.021 / mean 0.0045 (Denge), consistent with the
  Monte Carlo standard error at n = 2,000 (≤ 0.011). p_hayatta_simdi identical in all 300 packages.
- Packages with p_renewal = 0.0000 while p_alive > 0: v2 had 1 (Butik), v3 has 0. The two remaining 0.0000 rows
  also have p_alive = 0.0000 (rounded to 4 decimals).
- Math report example (section 3.3 parameters, 20 days left): Ayşe 0.98 / 0.96 unchanged; Burak P(renewal)
  0.13 → 0.14 (exact 0.1395; the old 0.13 was 1.2 Monte Carlo standard errors low).
- p_renewal is now bit-for-bit invariant to the nightly date shift (tests/test_demo_tazele.py tightened to ==).
- Tests: 581 passed (567 + 14 new), no RuntimeWarning.

## Out of scope
Full Bayes (parameter uncertainty; math report 10.6), minimum-data guard, prior re-tuning on real data (4b-2).
