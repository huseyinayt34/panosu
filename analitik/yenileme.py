"""Yenileme modeli (Adım 5b, model_versiyonu 'mbgnbd-map-v2'). Tasarım: docs/adim-5b-tasarim.md, Bölüm 3.
'mbgnbd-map-v2' (2026-10): simülasyon 'mbgnbd-sim-v1' ile aynıdır; M3 parametreleri MLE yerine MAP ile kestirilir
(θ = (ln m, ln r, logit μ, ln κ), zayıf önsel, iki başlangıç; analitik.bgnbd, docs/adim-mu-kappa-tasarim.md).

Tanım: üye, paketi bittiği anda hâlâ "hayatta" (MBG/NBD anlamında aktif) ise yeniler:
    P(yenileme) = P(paket bittiğinde hayatta)
Gerçek yenileme verisiyle kalibre edilmemiş davranışsal ilk sürümdür.

Sonsal simülasyon (her paket için N = 2 000):
  1. Şu an hayatta mı?  Bernoulli(P(hayatta | x, t_x, T))  (M3 formülü)
  2. Hayattaysa:        λ ~ Gamma(r + x, oran α + T),  p ~ Beta(a, b + x + 1)
     Türetme: (λ, p) verildiğinde "hayatta + gözlenen veri" olabilirliği (1−p)^(x+1)·λ^x·e^(−λT); öncüllerle
     çarpımı λ^(r+x−1)·e^(−(α+T)λ) · p^(a−1)·(1−p)^(b+x) olur ve iki bağımsız çarpana ayrılır.
  3. İleri simülasyon: hayattaysa ziyaretler Poisson(λ), her ziyaretten sonra p ile bırakma.
     K = pencerede gerçekleşecek ziyaret sayısı; üye K ziyaretin hepsinden sağ çıkarsa pencere sonunda hayattadır.
     K ziyaret için ayrı ayrı Bernoulli çekmek yerine tek U ~ Uniform(0,1) ile "U < (1−p)^K" sınanır
     (dağılım olarak aynı). K ters CDF ile ortak bir tekdüze sayıdan çekilir: aynı tohumda pencere uzadıkça K azalmaz.
       - Süre bazlı: pencere = bitişe kalan gün; üs = K.
       - Giriş bazlı: kalan R hak. Son kullanma yoksa üs = R (haklar mutlaka biter; son hakkı kullanan ziyaretin
         ardındaki bırakma da sayılır, proje sahibi kararı 2026-10-01). Son kullanma E gün sonraysa K ~ Poisson(λE),
         üs = min(K, R): K ≥ R ise haklar E'den önce biter, değilse E anında hayatta olma sınanır.
  4. P(yenileme) = hayatta biten simülasyonların oranı.
Tekrarlanabilirlik: tohum (paket_id, hesaplama_tarihi)'nden türetilir.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date

import numpy as np
from scipy.stats import poisson

from analitik import mbgnbd
from analitik.bgnbd import BGNBDParametreleri

MODEL_VERSIYONU = "mbgnbd-map-v2"
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
    """P(yenileme) simülasyonu (adım 1–4).

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


def yenileme_olasiligi(
    prm: BGNBDParametreleri,
    x: float,
    t_x: float,
    T: float,
    *,
    pencere_gun: float | None,
    kalan_hak: int | None,
    tohum: int,
    n: int = SIMULASYON_SAYISI,
) -> YenilemeSonucu:
    """Tek paket için P(hayatta şimdi) (M3 formülü, kesin) ve P(yenileme) (simülasyon)."""
    p_simdi = float(mbgnbd.p_hayatta(prm, [x], [t_x], [T])[0])
    rng = np.random.default_rng(tohum)
    return YenilemeSonucu(p_simdi, simule_et(p_simdi, prm, x, T, rng, pencere_gun=pencere_gun, kalan_hak=kalan_hak, n=n))
