"""Yenileme modeli (Adım 5b; model_versiyonu 'mbgnbd-map-v3'). Tasarım: docs/adim-5b-tasarim.md Bölüm 3,
docs/adim-rao-blackwell-tasarim.md (K61-K63).
'mbgnbd-map-v3' (2026-10): same model as 'mbgnbd-map-v2' (MAP parameters, analitik.bgnbd); P(renewal) is now computed
exactly instead of by Monte Carlo (K61). v2 differed from v3 only by Monte Carlo noise.

Tanım: üye, paketi bittiği anda hâlâ "hayatta" (MBG/NBD anlamında aktif) ise yeniler:
    P(yenileme) = P(paket bittiğinde hayatta)
Gerçek yenileme verisiyle kalibre edilmemiş davranışsal ilk sürümdür.

Model (unchanged since 5b): alive now with P(hayatta | x, t_x, T); if alive, λ ~ Gamma(r + x, rate α + T),
p ~ Beta(a, b + x + 1) (independent); K ~ Poisson(λ·w) visits in the window w; after each visit drop out with p.
    P(yenileme) = P(hayatta) · E[(1 − p)^e],   e = K (duration), R (entries, no expiry), min(K, R) (entries + expiry)
Exact forms (K61), with s = r + x, β = α + T, M(k) = E[(1 − p)^k] = B(a, b + x + 1 + k) / B(a, b + x + 1):
  - Duration, window D:   E[e^(−λ·p·D)] = E_p[(1 + p·D/β)^(−s)] = ₂F₁(s, a; a + b + x + 1; −D/β)
                          (Gamma MGF, then Euler's integral; evaluated after the Pfaff transform so the argument
                          is in [0, 1)).
  - Entries, no expiry:   M(R).
  - Entries, expiry E:    K ~ NBD(s, θ = β/(β + E)) after integrating λ out;
                          Σ_{k<R} P(K = k)·M(k) + P(K ≥ R)·M(R).
simule_et keeps the Monte Carlo version as a reference implementation; tests check that the exact value is its
n → ∞ limit (Rao-Blackwell: replacing a random draw by its conditional expectation never increases variance; here
every draw is integrated out, so the variance is zero).
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date

import numpy as np
from scipy.special import betaln, hyp2f1
from scipy.stats import nbinom, poisson

from analitik import mbgnbd
from analitik.bgnbd import BGNBDParametreleri

MODEL_VERSIYONU = "mbgnbd-map-v3"
SIMULASYON_SAYISI = 2_000


@dataclass(frozen=True)
class YenilemeSonucu:
    p_hayatta_simdi: float
    p_yenileme: float


def tohum_turet(paket_id: uuid.UUID, hesaplama_tarihi: date) -> int:
    """(paket_id, hesaplama_tarihi)'nden kararlı 64 bitlik tohum (Python hash()'i süreçler arası kararsızdır)."""
    ozet = hashlib.sha256(f"{paket_id}|{hesaplama_tarihi.isoformat()}".encode()).digest()
    return int.from_bytes(ozet[:8], "big")


def simule_et(
    p_hayatta_simdi: float,
    prm: BGNBDParametreleri,
    x: float,
    T: float,
    rng: np.random.Generator,
    *,
    pencere_gun: float | None,
    kalan_hak: int | None = None,
    n: int = SIMULASYON_SAYISI,
) -> float:
    """Reference Monte Carlo of P(renewal) (used by tests to check kesin_yenileme; not used in production).

    pencere_gun: süre bazlıda bitişe kalan gün; giriş bazlıda son kullanmaya kalan gün (yoksa None).
    kalan_hak:   giriş bazlıda kalan giriş hakkı; süre bazlıda None.
    """
    hayatta = rng.random(n) < p_hayatta_simdi
    lam = rng.gamma(prm.r + x, 1.0 / (prm.alfa + T), size=n)
    p = rng.beta(prm.a, prm.b + x + 1, size=n)
    u_ziyaret, u_birakma = rng.random(n), rng.random(n)

    if kalan_hak is not None and kalan_hak <= 0:          # haklar zaten bitmiş: karar şu anki durumdur
        return float(hayatta.mean())
    if pencere_gun is None:                               # giriş bazlı, son kullanma yok: tüm haklar kullanılır
        us = np.full(n, float(kalan_hak))
    elif pencere_gun <= 0:                                # bitiş/son kullanma geçmiş: karar şu anki durumdur
        return float(hayatta.mean())
    else:
        K = np.maximum(poisson.ppf(u_ziyaret, lam * pencere_gun), 0.0)   # ppf(0) = −1 uç durumu
        us = K if kalan_hak is None else np.minimum(K, kalan_hak)
    sag = u_birakma < np.exp(us * np.log1p(-p))           # (1 − p)^üs
    return float((hayatta & sag).mean())


def _beta_momenti(prm: BGNBDParametreleri, x: float, k):
    """E[(1 - p)^k], p ~ Beta(a, b + x + 1)."""
    b1 = prm.b + x + 1
    return np.exp(betaln(prm.a, b1 + k) - betaln(prm.a, b1))


def kesin_yenileme(
    p_hayatta_simdi: float,
    prm: BGNBDParametreleri,
    x: float,
    T: float,
    *,
    pencere_gun: float | None,
    kalan_hak: int | None = None,
) -> float:
    """Exact P(renewal) = p_alive * E[(1 - p)^exponent], the limit of simule_et as n -> infinity (K61)."""
    if (kalan_hak is not None and kalan_hak <= 0) or (pencere_gun is not None and pencere_gun <= 0):
        return p_hayatta_simdi
    if pencere_gun is None:
        sag = _beta_momenti(prm, x, kalan_hak)
    elif kalan_hak is None:
        s, c = prm.r + x, prm.a + prm.b + x + 1
        z = -pencere_gun / (prm.alfa + T)
        sag = (1 - z) ** (-prm.a) * hyp2f1(c - s, prm.a, c, z / (z - 1))
    else:
        s, teta = prm.r + x, (prm.alfa + T) / (prm.alfa + T + pencere_gun)
        k = np.arange(kalan_hak)
        sag = (np.sum(nbinom.pmf(k, s, teta) * _beta_momenti(prm, x, k))
               + nbinom.sf(kalan_hak - 1, s, teta) * _beta_momenti(prm, x, kalan_hak))
    return p_hayatta_simdi * min(max(float(sag), 0.0), 1.0)


def yenileme_olasiligi(
    prm: BGNBDParametreleri,
    x: float,
    t_x: float,
    T: float,
    *,
    pencere_gun: float | None,
    kalan_hak: int | None,
) -> YenilemeSonucu:
    """Tek paket için P(hayatta şimdi) ve P(yenileme), ikisi de kesin formül."""
    p_simdi = float(mbgnbd.p_hayatta(prm, [x], [t_x], [T])[0])
    return YenilemeSonucu(p_simdi, kesin_yenileme(p_simdi, prm, x, T, pencere_gun=pencere_gun, kalan_hak=kalan_hak))
