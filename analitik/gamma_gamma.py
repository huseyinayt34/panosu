"""M2: Gamma-Gamma harcama modeli (Fader, Hardie & Lee, 2005).

    Ziyaret başına harcama z ~ Gamma(p, ν)   (ν: oran),   ν ~ Gamma(q, γ)   (γ: oran)

Müşteri başına veri: x (tekrar ziyaret sayısı, x ≥ 1) ve m̄ (bu x ziyaretin ortalama tutarı).
m̄'nin marjinal yoğunluğu (ν integrallenmiş):
    f(m̄ | x) = Γ(px+q) / (Γ(px)·Γ(q)) · γ^q · m̄^(px−1) · x^(px) / (γ + m̄·x)^(px+q)
Parametreler log-uzayda L-BFGS-B ile MLE.

Bilinen varsayım: harcama ile ziyaret sıklığı bağımsızdır (bkz. bagimsizlik_tanisi).
"""

from dataclasses import dataclass

import numpy as np
from scipy.special import gammaln

from analitik.bgnbd import log_mle


@dataclass(frozen=True)
class GammaGammaParametreleri:
    p: float
    q: float
    gamma: float

    def dizi(self) -> np.ndarray:
        return np.array([self.p, self.q, self.gamma])

    @property
    def populasyon_ortalamasi(self) -> float:
        """E[z] = p·γ / (q−1); q > 1 gerektirir."""
        if self.q <= 1:
            raise ValueError(f"q = {self.q:.4f} ≤ 1: popülasyon ortalaması tanımsız")
        return self.p * self.gamma / (self.q - 1)


def _tekrarlilar(x, m):
    x, m = np.asarray(x, dtype=float), np.asarray(m, dtype=float)
    secim = x > 0
    return x[secim], m[secim]


def log_olabilirlik_bireysel(prm: GammaGammaParametreleri, x, m) -> np.ndarray:
    """x ≥ 1 müşterilerin log-olabilirlik katkısı (x, m aynı uzunlukta, yalnız x ≥ 1)."""
    x, m = np.asarray(x, dtype=float), np.asarray(m, dtype=float)
    p, q, g = prm.p, prm.q, prm.gamma
    px = p * x
    return (gammaln(px + q) - gammaln(px) - gammaln(q) + q * np.log(g)
            + (px - 1) * np.log(m) + px * np.log(x) - (px + q) * np.log(g + m * x))


def log_olabilirlik(prm: GammaGammaParametreleri, x, m) -> float:
    """Toplam log-olabilirlik; x = 0 müşteriler yok sayılır."""
    x, m = _tekrarlilar(x, m)
    return float(log_olabilirlik_bireysel(prm, x, m).sum())


def fit(x, m, baslangic: GammaGammaParametreleri | None = None) -> GammaGammaParametreleri:
    """(p, q, γ) MLE; yalnızca x ≥ 1 ve m̄ > 0 müşteriler kullanılır."""
    x, m = _tekrarlilar(x, m)
    if np.any(~(m > 0)):
        raise ValueError("Gamma-Gamma için tekrar ziyaretli müşterilerin ortalama tutarı pozitif olmalı")
    if baslangic is None:
        baslangic = GammaGammaParametreleri(p=1.0, q=2.0, gamma=float(np.mean(m)))
    n = len(x)

    def amac(log_prm):
        deger = -log_olabilirlik_bireysel(GammaGammaParametreleri(*np.exp(log_prm)), x, m).sum() / n
        return deger if np.isfinite(deger) else 1e300

    return GammaGammaParametreleri(*np.exp(log_mle(amac, np.log(baslangic.dizi()), [(-10.0, 15.0)] * 3, n, "Gamma-Gamma")))


def beklenen_sepet(prm: GammaGammaParametreleri, x, m) -> np.ndarray:
    """Sonsal beklenen sepet: (γ + m̄·x)·p / (p·x + q − 1).

    x = 0 müşteride (m̄ tanımsız) popülasyon ortalaması p·γ/(q−1) döner.
    """
    x, m = np.asarray(x, dtype=float), np.asarray(m, dtype=float)
    m_guvenli = np.where(x > 0, m, 0.0)
    return (prm.gamma + m_guvenli * x) * prm.p / (prm.p * x + prm.q - 1)


def bagimsizlik_tanisi(x, m) -> float:
    """Tekrar ziyaretli müşterilerde sıklık (x) ile ortalama sepet (m̄) arasındaki Pearson korelasyonu.

    Gamma-Gamma'nın bağımsızlık varsayımı için tanı; 0'dan belirgin uzaklık varsayımın bozulduğunu gösterir.
    """
    x, m = _tekrarlilar(x, m)
    return float(np.corrcoef(x, m)[0, 1])
