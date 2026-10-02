"""analitik.bgnbd: P(hayatta) özellikleri, log-olabilirlik, beklenen ziyaret, parametre geri kazanımı."""

import numpy as np
import pytest

from analitik import bgnbd
from analitik.bgnbd import BGNBDParametreleri
from analitik.ozellikler import ozellik_cikar
from backtest.senaryolar import GERCEK_BGNBD, GOZLEM_GUN, SENARYOLAR, uret

PRM = BGNBDParametreleri(r=0.243, alfa=4.414, a=0.793, b=2.426)   # Fader, Hardie & Lee (2005), CDNOW

# 5 000 müşteride a–b ve p–γ çiftlerinin örneklem gürültüsü %15'i aşabiliyordu (proje sahibi kararı, 2026-10-01).
GERI_KAZANIM_MUSTERI = 40_000


def test_x_sifirsa_p_hayatta_bir():
    p = bgnbd.p_hayatta(PRM, [0, 0], [0, 0], [10.0, 500.0])
    np.testing.assert_array_equal(p, [1.0, 1.0])


def test_t_x_buyudukce_p_hayatta_artar():
    t_x = np.array([1.0, 10.0, 20.0, 30.0, 39.0])
    p = bgnbd.p_hayatta(PRM, np.full(5, 3), t_x, np.full(5, 40.0))
    assert np.all(np.diff(p) > 0)


def test_T_buyudukce_p_hayatta_azalir():
    T = np.array([20.0, 30.0, 50.0, 100.0])
    p = bgnbd.p_hayatta(PRM, np.full(4, 3), np.full(4, 15.0), T)
    assert np.all(np.diff(p) < 0)


def test_log_olabilirlik_onceden_hesaplanan_deger():
    # Değer, log'suz kapalı formun math.gamma ile doğrudan hesabından (bağımsız uygulama) alındı.
    x, t_x, T = [0, 2, 1, 5], [0.0, 30.43, 1.71, 20.0], [38.86, 38.86, 38.86, 30.0]
    assert bgnbd.log_olabilirlik(PRM, x, t_x, T) == pytest.approx(-30.79234195213734, abs=1e-6)


@pytest.mark.parametrize("a", [0.793, 1.5, 1.0 + 1e-6])
def test_beklenen_ziyaret_kapali_form_integralle_eslesir(a):
    prm = BGNBDParametreleri(r=PRM.r, alfa=PRM.alfa, a=a, b=PRM.b)
    x, t_x, T = np.array([0.0, 2.0, 7.0]), np.array([0.0, 30.0, 35.0]), np.array([38.86, 38.86, 38.86])
    kapali = bgnbd.beklenen_ziyaret(prm, 39.0, x, t_x, T)
    integral = bgnbd.p_hayatta(prm, x, t_x, T) * bgnbd._hayattaysa_beklenen_integral(prm, 39.0, x, T)
    np.testing.assert_allclose(kapali, integral, rtol=1e-5)


def test_sonsal_oran():
    np.testing.assert_allclose(bgnbd.sonsal_oran(PRM, [2], [40.0]), [(0.243 + 2) / (4.414 + 40)])


def test_parametre_geri_kazanimi_S0_40000_musteri():
    # Tohum, backtest'in S0 / tohum 0 koşusuyla aynı kuraldır (sonuca bakılmadan önce sabitlendi).
    veri = uret("S0", np.random.default_rng([SENARYOLAR.index("S0"), 0]), GERI_KAZANIM_MUSTERI)
    oz = ozellik_cikar(veri.zamanlar, veri.tutarlar, GOZLEM_GUN)
    tahmin = bgnbd.fit(oz.x, oz.t_x, oz.T)
    goreli = np.abs(tahmin.dizi() / GERCEK_BGNBD.dizi() - 1)
    assert np.all(goreli < 0.15), dict(zip(("r", "alfa", "a", "b"), goreli.round(3)))


def test_fit_girdi_sirasindan_bagimsiz_bit_bit_ayni():
    """Olabilirlik müşterilerin çoklu kümesinin fonksiyonu: permütasyon parametreyi TAM olarak değiştirmez."""
    veri = uret("S0", np.random.default_rng(7), 2_000)
    oz = ozellik_cikar(veri.zamanlar, veri.tutarlar, GOZLEM_GUN)
    sira = np.random.default_rng(8).permutation(len(oz.x))
    assert bgnbd.fit(oz.x, oz.t_x, oz.T) == bgnbd.fit(oz.x[sira], oz.t_x[sira], oz.T[sira])
