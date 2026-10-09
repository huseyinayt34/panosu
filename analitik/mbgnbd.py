"""M3: MBG/NBD (Batislam, Denizel & Filiztekin, 2007).

BG/NBD'den tek farkı: bırakma ilk ziyaret DAHİL her ziyaretten sonra mümkündür (x + 1 fırsat). Böylece tek
ziyaretli (x = 0) müşterinin P(hayatta) değeri 1'den küçüktür.

    Hayattayken ziyaretler Poisson(λ),         λ ~ Gamma(r, α)   (α: oran)
    Her ziyaretten sonra bırakma olasılığı p,  p ~ Beta(a, b)

Bireysel olabilirlik: (1−p)^(x+1)·λ^x·e^(−λT) + p·(1−p)^x·λ^x·e^(−λ·t_x). (λ, p) üzerinden integral:
    L = Γ(r+x)·α^r/Γ(r) · B(a, b+x+1)/B(a,b) · (α+T)^−(r+x) · [1 + a/(b+x) · ((α+T)/(α+t_x))^(r+x)]
    P(hayatta | x, t_x, T) = 1 / [1 + a/(b+x) · ((α+T)/(α+t_x))^(r+x)]
Parametre yapısı ve MAP uyumu BG/NBD ile ortaktır (BGNBDParametreleri; θ dönüşümü, zayıf önsel ve iki başlangıç
analitik.bgnbd'de, K42–K48). Zaman birimi: gün.
"""

import numpy as np
from scipy.special import betaln, gammaln

from analitik.bgnbd import (
    BGNBDParametreleri, Onsel, _diziler, hayattaysa_beklenen_ziyaret, kanonik_sira, log_onsel, map_iki_baslangic,
    parametreden_teta, tetadan_parametre,
)


def _log_oran_terimi(prm: BGNBDParametreleri, x, t_x, T) -> np.ndarray:
    """ln[ a/(b+x) · ((α+T)/(α+t_x))^(r+x) ] (x = 0 dahil)."""
    return np.log(prm.a) - np.log(prm.b + x) + (prm.r + x) * (np.log(prm.alfa + T) - np.log(prm.alfa + t_x))


def log_olabilirlik_bireysel(prm: BGNBDParametreleri, x, t_x, T) -> np.ndarray:
    x, t_x, T = _diziler(x, t_x, T)
    r, alfa, a, b = prm.r, prm.alfa, prm.a, prm.b
    return (gammaln(r + x) - gammaln(r) + r * np.log(alfa)
            + betaln(a, b + x + 1) - betaln(a, b)
            - (r + x) * np.log(alfa + T)
            + np.logaddexp(0.0, _log_oran_terimi(prm, x, t_x, T)))


def log_olabilirlik(prm: BGNBDParametreleri, x, t_x, T) -> float:
    return float(log_olabilirlik_bireysel(prm, x, t_x, T).sum())


def fit(x, t_x, T, baslangic: BGNBDParametreleri | None = None, onsel: Onsel | None = None) -> BGNBDParametreleri:
    """(r, α, a, b) MAP; bgnbd.fit ile aynı yapı (θ = (ln m, ln r, logit μ, ln κ), zayıf önsel, merkezi fark türevli
    L-BFGS-B, iki başlangıç, plato yedeği).

    onsel verilirse zayıf önselin yerine o kullanılır ve ilk başlangıç onun merkezidir (cold start, K82).
    Girdi önce kanonik sıraya (x, t_x, T) dizilir: aynı veri hangi sırayla gelirse gelsin parametre bit bit aynıdır.
    """
    x, t_x, T = kanonik_sira(*_diziler(x, t_x, T))
    n = len(x)
    if n == 0:
        raise ValueError("MBG/NBD uyumu için en az bir müşteri gerekli")
    log_p = onsel.log_yogunluk if onsel is not None else log_onsel
    if baslangic is not None:
        baslangic_teta = parametreden_teta(baslangic)
    elif onsel is not None:
        baslangic_teta = np.array(onsel.merkez, dtype=float)
    else:
        baslangic_teta = parametreden_teta(BGNBDParametreleri(r=1.0, alfa=max(float(np.mean(T)), 1.0), a=1.0, b=1.0))

    def amac(teta):
        deger = -(log_olabilirlik(tetadan_parametre(teta), x, t_x, T) + log_p(teta)) / n
        return deger if np.isfinite(deger) else 1e300

    return tetadan_parametre(map_iki_baslangic(amac, baslangic_teta, x, n, "MBG/NBD"))


def p_hayatta(prm: BGNBDParametreleri, x, t_x, T) -> np.ndarray:
    """P(hayatta | x, t_x, T) = 1 / [1 + a/(b+x) · ((α+T)/(α+t_x))^(r+x)]."""
    x, t_x, T = _diziler(x, t_x, T)
    return np.exp(-np.logaddexp(0.0, _log_oran_terimi(prm, x, t_x, T)))


def beklenen_ziyaret(prm: BGNBDParametreleri, t: float, x, t_x, T) -> np.ndarray:
    """(T, T+t] aralığında beklenen ziyaret sayısı.

    Hayattaysa sonsal p ~ Beta(a, b+x+1) olduğundan, hayatta koşullu beklenti BG/NBD'ninkinin b → b+1 hâlidir:
        (a+b+x)/(a−1) · [1 − ((α+T)/(α+T+t))^(r+x) · ₂F₁(r+x, b+x+1; a+b+x; t/(α+T+t))]
    """
    x, t_x, T = _diziler(x, t_x, T)
    kaydirilmis = BGNBDParametreleri(r=prm.r, alfa=prm.alfa, a=prm.a, b=prm.b + 1)
    return p_hayatta(prm, x, t_x, T) * hayattaysa_beklenen_ziyaret(kaydirilmis, t, x, T)
