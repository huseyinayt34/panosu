"""M0: V1 churn modeli (MusteriAnalizi.py'den taşındı).

    aralik_i ~ Normal(mu, sigma)            (mu, sigma: müşterinin kendi aralıkları)
    r        = son ziyaretten bu yana geçen gün
    risk     = P(aralik <= r) = Phi((r - mu) / sigma_etkin),   sigma_etkin = max(sigma, 0.25 * mu)

Backtest karşılaştırması için "hayatta olma olasılığı" = 1 - risk. En az MIN_ZIYARET_SAYISI ziyareti
olmayan müşterilerde, eğitim verisindeki (yeterli ziyareti olan) müşterilerin ortanca mu ve sigma'sı
kullanılır (tasarım belgesi, M0).
"""

from collections.abc import Sequence
from datetime import date
from math import erf, sqrt

import numpy as np
from scipy.special import ndtr

MIN_ZIYARET_SAYISI = 3               # En az 2 aralık olmadan std. sapma hesaplanamaz
SIGMA_TABAN_ORANI = 0.25             # sigma_etkin >= 0.25 * mu

# (üst_sinir, etiket) - risk değeri üst sınırın altındaysa etiket geçerlidir
SEGMENT_ESIKLERI = [
    (0.35, "GÜVENLİ"),
    (0.75, "İZLENMELİ"),
    (0.95, "YÜKSEK RİSK"),
    (1.01, "KRİTİK"),
]


def normal_cdf(x: float) -> float:
    """Standart normal dağılımın birikimli dağılım fonksiyonu Phi(x)."""
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def ziyaret_araliklari(tarihler: list[date]) -> list[int]:
    """Ardışık ziyaretler arasındaki gün farklarını döndürür."""
    sirali = sorted(tarihler)
    return [(b - a).days for a, b in zip(sirali, sirali[1:])]


def churn_riski(gecen_gun: float, mu: float, sigma: float) -> float:
    """Müşterinin, kendi ritmine göre şimdiye kadar dönmüş olması gerekme olasılığı."""
    sigma_etkin = max(sigma, SIGMA_TABAN_ORANI * mu)
    z = (gecen_gun - mu) / sigma_etkin
    return normal_cdf(z)


def segment_belirle(risk: float) -> str:
    for ust_sinir, etiket in SEGMENT_ESIKLERI:
        if risk < ust_sinir:
            return etiket
    return SEGMENT_ESIKLERI[-1][1]


def p_hayatta_toplu(ziyaretler: Sequence[np.ndarray], gozlem_sonu: float) -> np.ndarray:
    """Her müşteri için P(hayatta) = 1 - risk. ziyaretler: gün cinsinden ziyaret zamanları (gözlem sonuna kadar).

    Yetersiz ziyaretli müşterilere, yeterli ziyaretli müşterilerin ortanca mu ve sigma'sı uygulanır.
    """
    mu = np.full(len(ziyaretler), np.nan)
    sigma = np.full(len(ziyaretler), np.nan)
    gecen = np.empty(len(ziyaretler))
    for i, z in enumerate(ziyaretler):
        z = np.sort(np.asarray(z, dtype=float))
        gecen[i] = gozlem_sonu - z[-1]
        if len(z) >= MIN_ZIYARET_SAYISI:
            araliklar = np.diff(z)
            mu[i] = araliklar.mean()
            sigma[i] = araliklar.std(ddof=1)          # statistics.stdev ile aynı (örneklem)

    yeterli = ~np.isnan(mu)
    if not yeterli.any():
        raise ValueError(f"Hiçbir müşteride en az {MIN_ZIYARET_SAYISI} ziyaret yok; ortanca hesaplanamaz")
    mu[~yeterli] = np.median(mu[yeterli])
    sigma[~yeterli] = np.median(sigma[yeterli])

    sigma_etkin = np.maximum(sigma, SIGMA_TABAN_ORANI * mu)
    return 1.0 - ndtr((gecen - mu) / sigma_etkin)
