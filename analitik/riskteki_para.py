"""Riskteki Para (tasarım belgelerindeki tanımlar).

    beklenen_aylik_ciro = 30 × (r+x)/(α+T) × beklenen_sepet
    riskteki_para       = (1 − P(hayatta)) × beklenen_aylik_ciro
    Stüdyo (Adım 5b):   riskteki_para = (1 − P(yenileme)) × mevcut paketin satış fiyatı

Model içi hesap float64; raporlamada tutarlar para_decimal ile Decimal'e çevrilir.
"""

from decimal import ROUND_HALF_UP, Decimal

import numpy as np

AY_GUN = 30


def beklenen_aylik_ciro(gunluk_oran, beklenen_sepet):
    return AY_GUN * np.asarray(gunluk_oran, dtype=float) * np.asarray(beklenen_sepet, dtype=float)


def riskteki_para(p_hayatta, gunluk_oran, beklenen_sepet):
    return (1.0 - np.asarray(p_hayatta, dtype=float)) * beklenen_aylik_ciro(gunluk_oran, beklenen_sepet)


def para_decimal(tutar: float) -> Decimal:
    """float tutarı kuruşa yuvarlanmış Decimal'e çevirir (raporlama/veritabanı sınırı)."""
    return Decimal(repr(float(tutar))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def yenileme_riskteki_para(p_yenileme: Decimal, ucret: Decimal) -> Decimal:
    """Stüdyo Riskteki Parası, yenileme_riskleri.riskteki_para ile aynı hesap:
    p_yenileme numeric(5,4)'e yuvarlanır, sonra ROUND((1 − p_yenileme) × ucret, 2)."""
    p = Decimal(p_yenileme).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return ((Decimal(1) - p) * Decimal(ucret)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
