"""
Müşteri Davranış Panosu - V1.0 Çekirdek
---------------------------------------
Her müşterinin ziyaretleri arasındaki gün farklarından (aralıklardan) bir
geliş ritmi çıkarır ve "şu an geri dönmüş olması beklenirken dönmemiş olma"
olasılığını churn riski olarak hesaplar.

Model:
    aralik_i ~ Normal(mu, sigma)            (mu, sigma: müşterinin kendi aralıkları)
    r        = son ziyaretten bu yana geçen gün
    risk     = P(aralik <= r) = Phi((r - mu) / sigma_etkin)

    sigma_etkin = max(sigma, SIGMA_TABAN_ORANI * mu)
    (Çok düzenli müşterilerde sigma ~ 0 olur; taban, riskin aşırı sıçramasını önler.)
"""

from dataclasses import dataclass
from datetime import date
from math import erf, sqrt
from statistics import mean, stdev

# --------------------------------------------------------------------------
# Sabitler
# --------------------------------------------------------------------------
REFERANS_TARIHI = date(2026, 9, 29)  # Raporun "bugün"ü (tekrarlanabilir sonuç için sabit)
MIN_ZIYARET_SAYISI = 3               # En az 2 aralık olmadan std. sapma hesaplanamaz
SIGMA_TABAN_ORANI = 0.25             # sigma_etkin >= 0.25 * mu

# (üst_sinir, etiket) - risk değeri üst sınırın altındaysa etiket geçerlidir
SEGMENT_ESIKLERI = [
    (0.35, "GÜVENLİ"),
    (0.75, "İZLENMELİ"),
    (0.95, "YÜKSEK RİSK"),
    (1.01, "KRİTİK"),
]

# --------------------------------------------------------------------------
# Örnek veri (V2'de SQL'den gelecek)
# --------------------------------------------------------------------------
MUSTERILER = {
    "Ayşe Demir": [
        "2026-08-05", "2026-08-12", "2026-08-19", "2026-08-27",
        "2026-09-03", "2026-09-11", "2026-09-19", "2026-09-26",
    ],
    "Mehmet Kaya": [
        "2026-06-05", "2026-06-20", "2026-07-03", "2026-07-18",
        "2026-08-01", "2026-08-15", "2026-08-29", "2026-09-14",
    ],
    "Zeynep Arslan": [
        "2026-05-02", "2026-05-13", "2026-05-22", "2026-06-03",
        "2026-06-12", "2026-06-24", "2026-07-04", "2026-07-15",
    ],
    "Can Yıldız": [
        "2026-03-25", "2026-04-23", "2026-05-27", "2026-06-24",
        "2026-07-26", "2026-08-22",
    ],
    "Elif Şahin": [
        "2026-09-01", "2026-09-15",
    ],
}


# --------------------------------------------------------------------------
# Veri modeli
# --------------------------------------------------------------------------
@dataclass
class MusteriAnalizi:
    ad: str
    ziyaret_sayisi: int
    ort_aralik: float | None
    std_aralik: float | None
    gecen_gun: int
    risk: float | None
    segment: str


# --------------------------------------------------------------------------
# Matematik
# --------------------------------------------------------------------------
def normal_cdf(x: float) -> float:
    """Standart normal dağılımın birikimli dağılım fonksiyonu Phi(x)."""
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def ziyaret_araliklari(tarihler: list[date]) -> list[int]:
    """Ardışık ziyaretler arasındaki gün farklarını döndürür."""
    sirali = sorted(tarihler)
    return [(b - a).days for a, b in zip(sirali, sirali[1:])]


def churn_riski(gecen_gun: int, mu: float, sigma: float) -> float:
    """Müşterinin, kendi ritmine göre şimdiye kadar dönmüş olması gerekme olasılığı."""
    sigma_etkin = max(sigma, SIGMA_TABAN_ORANI * mu)
    z = (gecen_gun - mu) / sigma_etkin
    return normal_cdf(z)


def segment_belirle(risk: float) -> str:
    for ust_sinir, etiket in SEGMENT_ESIKLERI:
        if risk < ust_sinir:
            return etiket
    return SEGMENT_ESIKLERI[-1][1]


# --------------------------------------------------------------------------
# Analiz
# --------------------------------------------------------------------------
def musteri_analiz_et(ad: str, ham_tarihler: list[str]) -> MusteriAnalizi:
    tarihler = sorted(date.fromisoformat(t) for t in ham_tarihler)
    gecen_gun = (REFERANS_TARIHI - tarihler[-1]).days

    if len(tarihler) < MIN_ZIYARET_SAYISI:
        return MusteriAnalizi(ad, len(tarihler), None, None, gecen_gun, None, "YETERSİZ VERİ")

    araliklar = ziyaret_araliklari(tarihler)
    mu = mean(araliklar)
    sigma = stdev(araliklar)
    risk = churn_riski(gecen_gun, mu, sigma)

    return MusteriAnalizi(ad, len(tarihler), mu, sigma, gecen_gun, risk, segment_belirle(risk))


# --------------------------------------------------------------------------
# Rapor
# --------------------------------------------------------------------------
def rapor_yazdir(sonuclar: list[MusteriAnalizi]) -> None:
    cizgi = "=" * 88
    ince = "-" * 88

    print(cizgi)
    print("MÜŞTERİ DAVRANIŞ PANOSU  |  CHURN RİSK RAPORU  |  V1.0")
    print(f"Referans tarihi: {REFERANS_TARIHI.isoformat()}   Müşteri sayısı: {len(sonuclar)}")
    print(cizgi)
    print(f"{'Müşteri':<16}{'Ziyaret':>8}{'Ort.Aralık':>12}{'Std.Sapma':>11}"
          f"{'Geçen Gün':>11}{'Risk':>8}   Segment")
    print(ince)

    for s in sorted(sonuclar, key=lambda x: (x.risk is None, -(x.risk or 0))):
        ort = f"{s.ort_aralik:.1f} g" if s.ort_aralik is not None else "-"
        std = f"{s.std_aralik:.1f} g" if s.std_aralik is not None else "-"
        risk = f"%{s.risk * 100:.1f}" if s.risk is not None else "-"
        print(f"{s.ad:<16}{s.ziyaret_sayisi:>8}{ort:>12}{std:>11}"
              f"{s.gecen_gun:>9} g{risk:>8}   {s.segment}")

    print(ince)
    dagilim: dict[str, int] = {}
    for s in sonuclar:
        dagilim[s.segment] = dagilim.get(s.segment, 0) + 1
    print("Segment dağılımı: " + " | ".join(f"{k}: {v}" for k, v in dagilim.items()))
    print(cizgi)


def main() -> None:
    sonuclar = [musteri_analiz_et(ad, tarihler) for ad, tarihler in MUSTERILER.items()]
    rapor_yazdir(sonuclar)


if __name__ == "__main__":
    main()