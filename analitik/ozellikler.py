"""Ziyaret geçmişinden BG/NBD ve Gamma-Gamma girdileri.

  x    : tekrar ziyaret sayısı (ilk ziyaret sayılmaz)
  t_x  : son ziyaretin ilk ziyarete göre zamanı (x = 0 ise 0)
  T    : gözlem süresi = gözlem sonu - ilk ziyaret
  m̄    : tekrar ziyaretlerin ortalama tutarı (x = 0 ise NaN). Gamma-Gamma'daki x ile tutarlı olması
         için ilk ziyaret ortalamaya katılmaz.
Zaman birimi: gün. Gözlem sonundan sonraki ziyaretler yok sayılır.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Ozellikler:
    x: np.ndarray
    t_x: np.ndarray
    T: np.ndarray
    m: np.ndarray


def ozellik_cikar(
    zamanlar: Sequence[np.ndarray],
    tutarlar: Sequence[np.ndarray],
    gozlem_sonu: float,
) -> Ozellikler:
    """Her müşteri için (x, t_x, T, m̄). Gözlem sonundan önce en az bir ziyareti olmalıdır."""
    n = len(zamanlar)
    x, t_x, T, m = np.zeros(n), np.zeros(n), np.zeros(n), np.full(n, np.nan)
    for i, (z, tutar) in enumerate(zip(zamanlar, tutarlar)):
        z, tutar = np.asarray(z, dtype=float), np.asarray(tutar, dtype=float)
        sira = np.argsort(z, kind="stable")
        z, tutar = z[sira], tutar[sira]
        icinde = z <= gozlem_sonu
        z, tutar = z[icinde], tutar[icinde]
        if len(z) == 0:
            raise ValueError(f"{i}. müşterinin gözlem sonundan önce ziyareti yok")
        x[i] = len(z) - 1
        t_x[i] = z[-1] - z[0]
        T[i] = gozlem_sonu - z[0]
        if len(z) > 1:
            m[i] = tutar[1:].mean()
    return Ozellikler(x=x, t_x=t_x, T=T, m=m)
