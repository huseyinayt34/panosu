"""analitik.mbgnbd: x = 0'da P(hayatta) < 1, monotonluk, log-olabilirlik, beklenen ziyaret."""

import numpy as np
import pytest

from analitik import bgnbd, mbgnbd
from analitik.bgnbd import BGNBDParametreleri
from analitik.ozellikler import ozellik_cikar
from backtest.senaryolar import GERCEK_BGNBD, GOZLEM_GUN, SENARYOLAR, uret

PRM = BGNBDParametreleri(r=0.525, alfa=6.183, a=0.891, b=1.614)


def test_x_sifirsa_p_hayatta_birden_kucuk():
    p = mbgnbd.p_hayatta(PRM, [0, 0], [0, 0], [10.0, 500.0])
    assert np.all(p < 1.0) and np.all(p > 0.0)
    # x = 0: 1 / [1 + a/b · ((α+T)/α)^r]
    beklenen = 1 / (1 + PRM.a / PRM.b * ((PRM.alfa + 10.0) / PRM.alfa) ** PRM.r)
    assert p[0] == pytest.approx(beklenen)


def test_t_x_buyudukce_p_hayatta_artar():
    t_x = np.array([1.0, 10.0, 20.0, 30.0, 39.0])
    p = mbgnbd.p_hayatta(PRM, np.full(5, 3), t_x, np.full(5, 40.0))
    assert np.all(np.diff(p) > 0)


def test_T_buyudukce_p_hayatta_azalir():
    T = np.array([20.0, 30.0, 50.0, 100.0])
    p = mbgnbd.p_hayatta(PRM, np.full(4, 3), np.full(4, 15.0), T)
    assert np.all(np.diff(p) < 0)


def test_T_buyudukce_x_sifirda_da_p_hayatta_azalir():
    p = mbgnbd.p_hayatta(PRM, np.zeros(4), np.zeros(4), np.array([5.0, 20.0, 60.0, 200.0]))
    assert np.all(np.diff(p) < 0)


def test_log_olabilirlik_onceden_hesaplanan_deger():
    # Değer, bireysel olabilirliğin (λ, p) üzerinden integrali alınmış iki terimli log'suz formunun
    # math.gamma ile doğrudan hesabından (bağımsız uygulama) alındı.
    x, t_x, T = [0, 2, 1, 5], [0.0, 30.43, 1.71, 20.0], [38.86, 38.86, 38.86, 30.0]
    assert mbgnbd.log_olabilirlik(PRM, x, t_x, T) == pytest.approx(-30.696033944257714, abs=1e-6)


def test_beklenen_ziyaret_dogrudan_integralle_eslesir():
    # x = 0, T = 100, t = 60 için öncül üzerinden 2 boyutlu sayısal integral (scipy dblquad) ile hesaplandı:
    # E[(1−p)·e^(−λT)·(1−e^(−λpt))/p] / E[(1−p)·e^(−λT) + p]
    prm = BGNBDParametreleri(r=2.0, alfa=40.0, a=2.0, b=6.0)
    assert mbgnbd.beklenen_ziyaret(prm, 60.0, [0], [0.0], [100.0])[0] == pytest.approx(0.1479952982067185, rel=1e-8)


def test_beklenen_ziyaret_a_bire_yakinken_integral_yolu():
    prm = BGNBDParametreleri(r=2.0, alfa=40.0, a=1.0 + 1e-6, b=6.0)
    yakin = BGNBDParametreleri(r=2.0, alfa=40.0, a=1.0 + 1e-3, b=6.0)
    args = (60.0, [0, 3], [0.0, 80.0], [100.0, 100.0])
    np.testing.assert_allclose(mbgnbd.beklenen_ziyaret(prm, *args), mbgnbd.beklenen_ziyaret(yakin, *args), rtol=1e-2)


def test_tekrar_ziyaretlide_bgnbd_ile_ayni_yapi():
    # x ≥ 1'de MBG/NBD'nin P(hayatta)'sı, BG/NBD'ninkinde b+1 alınmış hâlidir: a/(b+x) = a/((b+1)+x−1).
    kaydirilmis = BGNBDParametreleri(r=PRM.r, alfa=PRM.alfa, a=PRM.a, b=PRM.b + 1)
    x, t_x, T = np.array([1.0, 4.0]), np.array([10.0, 30.0]), np.array([40.0, 40.0])
    np.testing.assert_allclose(mbgnbd.p_hayatta(PRM, x, t_x, T), bgnbd.p_hayatta(kaydirilmis, x, t_x, T))


def test_parametre_geri_kazanimi_S0_r_ve_alfa():
    # S0 BG/NBD ile üretilir: M3 orada yanlış belirlenmiş modeldir ve a/(a+b)'yi sistematik olarak düşük tahmin eder
    # (fazladan bir bırakma fırsatı sayar). Bu yüzden yalnız r ve α sınanır (proje sahibi kararı, 2026-10-01).
    veri = uret("S0", np.random.default_rng([SENARYOLAR.index("S0"), 0]), 5000)
    oz = ozellik_cikar(veri.zamanlar, veri.tutarlar, GOZLEM_GUN)
    tahmin = mbgnbd.fit(oz.x, oz.t_x, oz.T)
    goreli = np.abs(np.array([tahmin.r, tahmin.alfa]) / np.array([GERCEK_BGNBD.r, GERCEK_BGNBD.alfa]) - 1)
    assert np.all(goreli < 0.15), dict(zip(("r", "alfa"), goreli.round(3)))
