"""Cold start (step 8a, K81-K85; docs/adim-8a-tasarim.md): minimum-data guard and the learned prior.

A business with enough data is fitted exactly as before (weak prior, `analitik.yenileme.MODEL_VERSIYONU`). Below the
data threshold the weak prior is replaced by a prior learned from other businesses (empirical Bayes): each business
is fitted on its own with the usual MAP, and the mean and spread of the fitted θ = (ln m, ln r, logit μ, ln κ)
across businesses become an independent normal prior. As the business's own data grows, its likelihood outweighs
the fixed prior, so the estimate moves toward its own data. Results of this path carry ON_TAHMIN_VERSIYONU and are
shown as "ön tahmin" (preliminary estimate).

Threshold (owner, 2026-10-10): at least 30 members with a repeat visit (x ≥ 1) AND at least 60 days of history
(the oldest member's T).
"""

from dataclasses import dataclass

import numpy as np

from analitik import mbgnbd
from analitik.bgnbd import BGNBDParametreleri, Onsel
from analitik.yenileme import MODEL_VERSIYONU

ASGARI_TEKRARLI_UYE = 30
ASGARI_GECMIS_GUN = 60
ON_TAHMIN_VERSIYONU = "mbgnbd-onsel-v1"
# The learned spread is clipped to [taban, tavan] per direction: with few businesses a sample spread can be near 0
# (an overconfident prior), and above the weak prior's 2.0 the learned prior would be weaker than the default one.
SAPMA_TABANI = 0.5
SAPMA_TAVANI = 2.0

# Learned from the 5 [DEMO] businesses (synthetic, 2026-10-10): `python -m backtest.soguk_baslangic ogren`.
# A test recomputes it; when real businesses exist the same command learns it from their data (K84).
OGRENILMIS_ONSEL = Onsel(
    merkez=(-2.4789, 1.1062, -3.5994, 3.7180),
    sapma=(1.1823, 0.5000, 0.9612, 1.1338),
)


@dataclass(frozen=True)
class Uyum:
    prm: BGNBDParametreleri
    model_versiyonu: str
    on_tahmin: bool                  # True: too little data, the learned prior was used


def veri_yeterli(x, T) -> bool:
    """At least ASGARI_TEKRARLI_UYE members with a repeat visit and at least ASGARI_GECMIS_GUN days of history."""
    x, T = np.asarray(x, dtype=float), np.asarray(T, dtype=float)
    return bool(len(x)) and int(np.sum(x >= 1)) >= ASGARI_TEKRARLI_UYE and float(T.max()) >= ASGARI_GECMIS_GUN


def onsel_ogren(tetalar) -> Onsel:
    """Empirical Bayes prior from per-business MAP estimates (rows: businesses, columns: θ directions).

    Center = mean; spread = sample standard deviation (ddof = 1) clipped to [SAPMA_TABANI, SAPMA_TAVANI].
    """
    tetalar = np.asarray(tetalar, dtype=float)
    if tetalar.ndim != 2 or tetalar.shape[1] != 4 or tetalar.shape[0] < 2:
        raise ValueError("Önsel öğrenmek için en az iki işletmenin θ tahmini gerekli")
    merkez = tetalar.mean(axis=0)
    sapma = np.clip(tetalar.std(axis=0, ddof=1), SAPMA_TABANI, SAPMA_TAVANI)
    return Onsel(merkez=tuple(float(d) for d in merkez), sapma=tuple(float(d) for d in sapma))


def uyum(x, t_x, T, onsel: Onsel = OGRENILMIS_ONSEL) -> Uyum:
    """MBG/NBD fit used by production (renewal service, pilot, score command): guard first, then the right prior."""
    if veri_yeterli(x, T):
        return Uyum(mbgnbd.fit(x, t_x, T), MODEL_VERSIYONU, False)
    return Uyum(mbgnbd.fit(x, t_x, T, onsel=onsel), ON_TAHMIN_VERSIYONU, True)
