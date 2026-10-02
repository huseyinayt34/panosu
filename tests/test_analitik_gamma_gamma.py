"""analitik.gamma_gamma: parametre geri kazanımı, x = 0 müşteride popülasyon ortalaması."""

import numpy as np
import pytest

from analitik import gamma_gamma
from analitik.gamma_gamma import GammaGammaParametreleri
from analitik.ozellikler import ozellik_cikar
from backtest.senaryolar import GERCEK_GG, GOZLEM_GUN, SENARYOLAR, uret

# 5 000 müşteride a–b ve p–γ çiftlerinin örneklem gürültüsü %15'i aşabiliyordu (proje sahibi kararı, 2026-10-01).
GERI_KAZANIM_MUSTERI = 40_000


def test_x_sifir_musteride_beklenen_sepet_populasyon_ortalamasi():
    prm = GammaGammaParametreleri(p=6.0, q=4.0, gamma=200.0)
    sepet = gamma_gamma.beklenen_sepet(prm, [0], [np.nan])
    assert sepet[0] == pytest.approx(prm.populasyon_ortalamasi)
    assert sepet[0] == pytest.approx(400.0)


def test_beklenen_sepet_formulu():
    prm = GammaGammaParametreleri(p=6.0, q=4.0, gamma=200.0)
    # (γ + m̄·x)·p / (p·x + q − 1) = (200 + 500·3)·6 / (18 + 3)
    assert gamma_gamma.beklenen_sepet(prm, [3], [500.0])[0] == pytest.approx(1700 * 6 / 21)


def test_bagimsizlik_tanisi_yalniz_tekrarlilari_kullanir():
    x = np.array([0, 1, 2, 3, 4])
    m = np.array([np.nan, 10.0, 20.0, 30.0, 40.0])
    assert gamma_gamma.bagimsizlik_tanisi(x, m) == pytest.approx(1.0)


def test_parametre_geri_kazanimi_S0_40000_musteri():
    # bgnbd geri kazanım testiyle aynı veri ve eşik (tasarım: "benzer geri kazanım testi").
    veri = uret("S0", np.random.default_rng([SENARYOLAR.index("S0"), 0]), GERI_KAZANIM_MUSTERI)
    oz = ozellik_cikar(veri.zamanlar, veri.tutarlar, GOZLEM_GUN)
    tahmin = gamma_gamma.fit(oz.x, oz.m)
    goreli = np.abs(tahmin.dizi() / GERCEK_GG.dizi() - 1)
    assert np.all(goreli < 0.15), dict(zip(("p", "q", "gamma"), goreli.round(3)))


def test_fit_girdi_sirasindan_bagimsiz_bit_bit_ayni():
    """Olabilirlik müşterilerin çoklu kümesinin fonksiyonu: permütasyon parametreyi TAM olarak değiştirmez."""
    veri = uret("S0", np.random.default_rng(7), 2_000)
    oz = ozellik_cikar(veri.zamanlar, veri.tutarlar, GOZLEM_GUN)
    sira = np.random.default_rng(8).permutation(len(oz.x))
    assert gamma_gamma.fit(oz.x, oz.m) == gamma_gamma.fit(oz.x[sira], oz.m[sira])
