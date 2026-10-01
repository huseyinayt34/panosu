"""S0–S4 sentetik senaryoları (tasarım belgesi, "Senaryolar"). Veritabanına hiçbir şey yazılmaz.

Zaman sürekli ve gün cinsindendir: gözlem [0, GOZLEM_GUN], edinim t0 ~ Uniform(0, GOZLEM_GUN).
Her müşteri için tüm ziyaret zamanları, tutarları, edinim ve kayıp (ölüm) anı üretilir.
Kayıp anı = müşterinin artık hiç gelmeyeceği an (np.inf: gözlem sonunda hâlâ hayatta).

Belgede sayısı verilmeyen değerler (BELGEDE YOK işaretli) katalogdaki berber profilinden alındı;
backtest raporunda varsayım olarak listelenir.
"""

from dataclasses import dataclass

import numpy as np

from analitik.bgnbd import BGNBDParametreleri
from analitik.gamma_gamma import GammaGammaParametreleri
from sentetik.katalog import PROFILLER
from sentetik.uretici import ziyaret_zamanlarini_uret

GOZLEM_GUN = 730.0                    # 2 yıl
KALIBRASYON_GUN = GOZLEM_GUN * 0.75   # ilk 18 ay; son 6 ay bekleme dönemi
MUSTERI_SAYISI = 2000

_BERBER = PROFILLER["berber"]
# S0 (ve S1/S2/S4'teki ziyaret sonrası bırakma, S3'teki Poisson hızı): berber profili. BELGEDE YOK.
GERCEK_BGNBD = BGNBDParametreleri(r=_BERBER.r, alfa=_BERBER.alfa, a=_BERBER.beta_a, b=_BERBER.beta_b)
# Harcama: Gamma-Gamma, ortalama sepet p·γ/(q−1) = 400 TL. BELGEDE YOK.
GERCEK_GG = GammaGammaParametreleri(p=6.0, q=4.0, gamma=200.0)

S1_ARALIK_SEKLI = 8.0                 # aralık ~ Gamma(k=8, ortalama μ_i); değişim katsayısı 1/√8 ≈ 0.35
S1_MU_ORTALAMA = 30.0
S1_MU_SEKLI = _BERBER.r               # μ_i ~ Gamma(şekil 3, ortalama 30). Şekil BELGEDE YOK.
S3_OMUR_ORTALAMA = 18 * 30.0          # ömür ~ Üstel(ortalama 18 ay)

# S2 karışımı (HİPOTEZ): (grup, oran, ortalama aralık μ; None = tek seferlik)
S2_GRUPLARI = (
    ("haftalik", 0.05, 7.0),
    ("aylik", 0.65, 30.0),
    ("seyrek", 0.20, 50.0),
    ("tek_seferlik", 0.10, None),
)
# S4: grup bazında ortalama sepet çarpanı (HİPOTEZ); belirtilmeyen gruplar 1.0.
S4_SEPET_CARPANI = {"haftalik": 1.4, "aylik": 1.0, "seyrek": 0.9, "tek_seferlik": 1.0}

# S5 "Güzellik salonu" (HİPOTEZ: "ilk ziyaret sonrası müşterilerin yarısından fazlası dönmüyor"):
# %55 tek seferlik; kalanlar S1'deki gibi düzenli (μ_i ~ Gamma(şekil S1_MU_SEKLI, ortalama 35 g)), ortalama sepet 900 TL.
S5_TEK_SEFERLIK_ORANI = 0.55
S5_MU_ORTALAMA = 35.0
S5_ORTALAMA_SEPET = 900.0

SENARYOLAR = ("S0", "S1", "S2", "S3", "S4", "S5")
GRUPLU_SENARYOLAR = ("S2", "S4", "S5")
TEK_SEFERLIK = "tek_seferlik"
SENARYO_ACIKLAMA = {
    "S0": "Hiçbir şey bozulmaz (BG/NBD varsayımları)",
    "S1": "Poisson bozulur: düzenli aralıklar, Gamma(k=8)",
    "S2": "Gamma heterojenliği bozulur: grup karışımı",
    "S3": "Ziyaret sonrası bırakma bozulur: sürekli zamanda üstel ömür",
    "S4": "Harcama–sıklık bağımsızlığı bozulur (S2 grupları)",
    "S5": "Güzellik salonu: %55 tek seferlik, kalanlar düzenli (35 g), sepet 900 TL",
}


@dataclass
class SenaryoVerisi:
    kod: str
    zamanlar: list[np.ndarray]        # müşteri başına sıralı ziyaret zamanları (gün)
    tutarlar: list[np.ndarray]        # aynı sırada ziyaret tutarları (TL)
    edinim: np.ndarray                # t0
    olum: np.ndarray                  # kayıp anı; np.inf = hiç kaybolmadı
    grup: np.ndarray                  # segment etiketi (grupsuz senaryolarda "tumu")


# ---------------------------------------------------------------------------------------------
# Ziyaret süreçleri
# ---------------------------------------------------------------------------------------------
def _duzenli_ziyaretler(mu: float, p: float, t0: float, rng: np.random.Generator) -> tuple[list[float], float]:
    """Aralıklar ~ Gamma(k, ortalama μ); her tekrar ziyaretten sonra p olasılıkla bırakma (S1, S2)."""
    zamanlar, t = [t0], t0
    while True:
        t += rng.gamma(S1_ARALIK_SEKLI, mu / S1_ARALIK_SEKLI)
        if t >= GOZLEM_GUN:
            return zamanlar, np.inf
        zamanlar.append(t)
        if rng.random() < p:
            return zamanlar, t


def _omurlu_poisson(lam: float, t0: float, olum: float, rng: np.random.Generator) -> list[float]:
    """Poisson(λ) ziyaretler, t0'dan min(ölüm, gözlem sonu)'na kadar (S3)."""
    zamanlar, t, son = [t0], t0, min(olum, GOZLEM_GUN)
    while True:
        t += rng.exponential(1.0 / lam)
        if t >= son:
            return zamanlar
        zamanlar.append(t)


def _bgnbd_p(rng: np.random.Generator) -> float:
    return float(rng.beta(GERCEK_BGNBD.a, GERCEK_BGNBD.b))


def _bgnbd_lambda(rng: np.random.Generator) -> float:
    return float(rng.gamma(GERCEK_BGNBD.r, 1.0 / GERCEK_BGNBD.alfa))


def _s2_grup_sec(n: int, rng: np.random.Generator) -> np.ndarray:
    adlar = [g[0] for g in S2_GRUPLARI]
    return rng.choice(adlar, size=n, p=[g[1] for g in S2_GRUPLARI])


# ---------------------------------------------------------------------------------------------
# Senaryo üreticisi
# ---------------------------------------------------------------------------------------------
def uret(kod: str, rng: np.random.Generator, musteri_sayisi: int = MUSTERI_SAYISI) -> SenaryoVerisi:
    if kod not in SENARYOLAR:
        raise ValueError(f"Bilinmeyen senaryo: {kod}")
    n = musteri_sayisi
    edinim = rng.uniform(0.0, GOZLEM_GUN, size=n)
    if kod in ("S2", "S4"):
        grup = _s2_grup_sec(n, rng)
    elif kod == "S5":
        grup = np.where(rng.random(n) < S5_TEK_SEFERLIK_ORANI, TEK_SEFERLIK, "duzenli")
    else:
        grup = np.full(n, "tumu")
    grup_mu = {g[0]: g[2] for g in S2_GRUPLARI}

    zamanlar, olum = [], np.full(n, np.inf)
    for i in range(n):
        t0 = float(edinim[i])
        if kod == "S0":
            z, o = ziyaret_zamanlarini_uret(_bgnbd_lambda(rng), _bgnbd_p(rng), t0, GOZLEM_GUN, rng)
            olum[i] = np.inf if o is None else o
        elif kod == "S1":
            mu = rng.gamma(S1_MU_SEKLI, S1_MU_ORTALAMA / S1_MU_SEKLI)
            z, olum[i] = _duzenli_ziyaretler(mu, _bgnbd_p(rng), t0, rng)
        elif kod == "S5":
            if grup[i] == TEK_SEFERLIK:
                z, olum[i] = [t0], t0
            else:
                mu = rng.gamma(S1_MU_SEKLI, S5_MU_ORTALAMA / S1_MU_SEKLI)
                z, olum[i] = _duzenli_ziyaretler(mu, _bgnbd_p(rng), t0, rng)
        elif kod in ("S2", "S4"):
            mu = grup_mu[grup[i]]
            if mu is None:                       # tek seferlik: ilk ziyaretten sonra hiç gelmez
                z, olum[i] = [t0], t0
            else:
                z, olum[i] = _duzenli_ziyaretler(mu, _bgnbd_p(rng), t0, rng)
        else:                                    # S3
            o = t0 + rng.exponential(S3_OMUR_ORTALAMA)
            z = _omurlu_poisson(_bgnbd_lambda(rng), t0, o, rng)
            olum[i] = o if o < GOZLEM_GUN else np.inf
        zamanlar.append(np.asarray(z, dtype=float))

    # Harcama: z ~ Gamma(p, ν_i), ν_i ~ Gamma(q, γ). S4'te grup çarpanı; S5'te ortalama 900 TL'ye ölçek (γ × 2.25'e denk).
    nu = rng.gamma(GERCEK_GG.q, 1.0 / GERCEK_GG.gamma, size=n)
    if kod == "S4":
        carpan = np.array([S4_SEPET_CARPANI[g] for g in grup])
    elif kod == "S5":
        carpan = np.full(n, S5_ORTALAMA_SEPET / GERCEK_GG.populasyon_ortalamasi)
    else:
        carpan = np.ones(n)
    tutarlar = [carpan[i] * rng.gamma(GERCEK_GG.p, 1.0 / nu[i], size=len(z)) for i, z in enumerate(zamanlar)]

    return SenaryoVerisi(kod=kod, zamanlar=zamanlar, tutarlar=tutarlar, edinim=edinim, olum=olum, grup=grup)
