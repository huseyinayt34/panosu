"""Backtest metrikleri (tasarım belgesi, "Değerlendirme")."""

from dataclasses import dataclass

import numpy as np

from sentetik.degerlendirme import roc_auc

KUTU_SAYISI = 10


def auc(p_hayatta: np.ndarray, hayatta: np.ndarray) -> float | None:
    """Gerçek hayatta (1) / ölü (0) etiketine karşı P(hayatta) için ROC AUC. Tek sınıf varsa None."""
    return roc_auc(np.asarray(p_hayatta, dtype=float), np.asarray(hayatta, dtype=int))


def brier(p_hayatta: np.ndarray, hayatta: np.ndarray) -> float:
    return float(np.mean((np.asarray(p_hayatta, dtype=float) - np.asarray(hayatta, dtype=float)) ** 2))


@dataclass(frozen=True)
class GuvenilirlikKutusu:
    alt: float
    ust: float
    n: int
    ort_tahmin: float | None
    gercek_oran: float | None


def guvenilirlik_tablosu(p_hayatta: np.ndarray, hayatta: np.ndarray, kutu: int = KUTU_SAYISI) -> list[GuvenilirlikKutusu]:
    """Eşit genişlikli kutular [0, 0.1), ..., [0.9, 1.0]: tahmin edilen ortalama olasılık ile gerçek oran."""
    p, y = np.asarray(p_hayatta, dtype=float), np.asarray(hayatta, dtype=float)
    indeks = np.minimum((p * kutu).astype(int), kutu - 1)
    tablo = []
    for k in range(kutu):
        maske = indeks == k
        n = int(maske.sum())
        tablo.append(GuvenilirlikKutusu(
            alt=k / kutu, ust=(k + 1) / kutu, n=n,
            ort_tahmin=float(p[maske].mean()) if n else None,
            gercek_oran=float(y[maske].mean()) if n else None,
        ))
    return tablo


def mae(tahmin: np.ndarray, gercek: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(tahmin, dtype=float) - np.asarray(gercek, dtype=float))))


def toplam_hata_yuzde(tahmin: np.ndarray, gercek: np.ndarray) -> float | None:
    """(Σ tahmin − Σ gerçek) / Σ gerçek × 100. Gerçek toplam 0 ise None."""
    toplam = float(np.sum(gercek))
    if toplam == 0:
        return None
    return (float(np.sum(tahmin)) - toplam) / toplam * 100.0


def goreli_hata(tahmin: float, gercek: float) -> float:
    return abs(tahmin - gercek) / abs(gercek)
