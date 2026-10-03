"""(μ, κ) yeniden parametreleme ve MAP (docs/adim-mu-kappa-tasarim.md, K42–K48): θ dönüşümü, önsel, küçük veride
kararlılık, iki başlangıç, yanlış bitiş koruması, boş girdi.

Yeni yardımcılar test fonksiyonlarının içinde içe aktarılır: eski kodda b)–d) ImportError ile değil kendi ölçütleriyle
çalışır.
"""

import math
import warnings

import numpy as np
import pytest

from analitik import bgnbd, mbgnbd
from analitik.bgnbd import BGNBDParametreleri
from analitik.ozellikler import ozellik_cikar
from backtest.senaryolar import KALIBRASYON_GUN, MUSTERI_SAYISI, S6_UYE_SAYISI, SENARYOLAR, uret, uret_s6

# test_analitik_mbgnbd.py'deki önceden hesaplanmış log-olabilirlik verisi
X, T_X, T = [0, 2, 1, 5], [0.0, 30.43, 1.71, 20.0], [38.86, 38.86, 38.86, 30.0]


def test_teta_donusumu_gidis_donus():
    from analitik.bgnbd import parametreden_teta, tetadan_parametre

    rng = np.random.default_rng(0)
    for satir in 10.0 ** rng.uniform(-3, 3, size=(200, 4)):
        prm = BGNBDParametreleri(*satir)
        geri = tetadan_parametre(parametreden_teta(prm))
        goreli = np.abs(geri.dizi() / prm.dizi() - 1)
        assert np.all(goreli < 1e-12), (prm, goreli)
        assert mbgnbd.log_olabilirlik(geri, X, T_X, T) == pytest.approx(
            mbgnbd.log_olabilirlik(prm, X, T_X, T), rel=1e-12, abs=1e-12)


def _a_verisi_ozellikleri():
    """tests/test_ice_aktarma_db.py a_verisi'nin ziyaret tarifi (29 üye), gün cinsinden, gözlem sonu 1.0."""
    rng = np.random.default_rng(11)
    zamanlar = []
    for no in range(32):
        if no >= 30 or no == 18:
            continue
        gun = -int(rng.integers(150, 183))
        son = -(1 if no % 5 else int(rng.integers(40, 90)))
        t = []
        while gun <= son:
            saat = int(rng.integers(8, 21))
            dk = int(rng.choice((0, 15, 30, 45)))
            if rng.random() >= 0.03:
                t.append(gun + (saat * 60 + dk) / 1440)
            gun += int(rng.integers(2, 12))
        zamanlar.append(np.array(t))
    return ozellik_cikar(zamanlar, zamanlar, 1.0)


@pytest.mark.parametrize("model", [mbgnbd, bgnbd], ids=["mbgnbd", "bgnbd"])
def test_map_kucuk_veride_kararli(model):
    """T'ye 1e-15 göreli gürültü: zayıf belirlenen yönler (κ, r) önselle sabitlendiği için çözüm yerinde kalır."""
    oz = _a_verisi_ozellikleri()
    with warnings.catch_warnings(record=True) as kayit:
        warnings.simplefilter("always")
        uyumlar = [model.fit(oz.x, oz.t_x, oz.T)]
        for i in range(1, 11):
            T_i = oz.T * (1 + 1e-15 * np.random.default_rng(i).standard_normal(len(oz.T)))
            uyumlar.append(model.fit(oz.x, oz.t_x, T_i))
    p = np.array([model.p_hayatta(prm, oz.x, oz.t_x, oz.T) for prm in uyumlar])
    delta_p = float(np.max(p.max(axis=0) - p.min(axis=0)))
    ln_kappa = np.log([prm.a + prm.b for prm in uyumlar])
    ln_r = np.log([prm.r for prm in uyumlar])
    olcum = {"delta_p": delta_p, "kappa": (float(np.exp(ln_kappa.min())), float(np.exp(ln_kappa.max()))),
             "r": (float(np.exp(ln_r.min())), float(np.exp(ln_r.max())))}
    assert delta_p < 1e-4, olcum
    assert np.ptp(ln_kappa) < 1e-3, olcum
    assert np.ptp(ln_r) < 1e-3, olcum
    assert not any("Nelder-Mead" in str(w.message) for w in kayit), [str(w.message) for w in kayit]


def test_iki_tepeli_veride_tek_seferlikler_birakmis():
    """Yarısı tek seferlik, yarısı çok sık gelen müşteri: ikinci başlangıç (μ ≈ tek seferlik payı, κ küçük) olmadan
    MAP tek seferlikleri hayatta sanan tepede kalıyordu."""
    x = np.r_[np.zeros(15), np.full(15, 90.0)]
    t_x = np.r_[np.zeros(15), np.full(15, 179.0)]
    T = np.r_[np.linspace(30.0, 180.0, 15), np.full(15, 180.0)]
    p = mbgnbd.p_hayatta(mbgnbd.fit(x, t_x, T), x, t_x, T)
    assert p[:15].max() < 0.01, p
    assert p[15:].min() > 0.99, p


@pytest.mark.parametrize("senaryo, tohum", [("S6", 1), ("S6", 2), ("S6", 8), ("S5", 0)])
def test_s6_ve_s5_yanlis_bitis_korumasi(senaryo, tohum):
    """Koruma: S6'da κ makul aralıkta kalır (ileri fark türevli ara sürümde 1e4–1e6'ya kaçıyordu); S5'te veri κ'yı
    gerçekten küçük istiyor, önsel bunu ezmemeli. Kesim backtest.calistir ile aynı."""
    if senaryo == "S6":
        v = uret_s6(np.random.default_rng([len(SENARYOLAR), tohum]), S6_UYE_SAYISI)
    else:
        v = uret(senaryo, np.random.default_rng([SENARYOLAR.index(senaryo), tohum]), MUSTERI_SAYISI)
    sec = np.flatnonzero(v.edinim <= KALIBRASYON_GUN)
    z = [v.zamanlar[i][v.zamanlar[i] <= KALIBRASYON_GUN] for i in sec]
    oz = ozellik_cikar(z, z, KALIBRASYON_GUN)
    prm = mbgnbd.fit(oz.x, oz.t_x, oz.T)
    kappa, mu = prm.a + prm.b, prm.a / (prm.a + prm.b)
    if senaryo == "S6":
        assert 15 < kappa < 80 and 0.04 < mu < 0.065, (kappa, mu)
    else:
        assert kappa < 1, (kappa, mu)


def test_log_onsel_yalniz_kappa_ve_r(monkeypatch):
    from analitik.bgnbd import log_onsel

    rng = np.random.default_rng(3)
    for teta in rng.uniform(-8, 8, size=(20, 4)):
        beklenen = (-0.5 * ((teta[3] - bgnbd.ONSEL_LN_KAPPA_MERKEZ) / bgnbd.ONSEL_LN_KAPPA_SAPMA) ** 2
                    - 0.5 * ((teta[1] - bgnbd.ONSEL_LN_R_MERKEZ) / bgnbd.ONSEL_LN_R_SAPMA) ** 2)
        assert log_onsel(teta) == pytest.approx(beklenen)
        oynatilmis = teta.copy()
        oynatilmis[[0, 2]] = rng.uniform(-8, 8, size=2)
        assert log_onsel(oynatilmis) == log_onsel(teta)

    monkeypatch.setattr(bgnbd, "ONSEL_LN_KAPPA_SAPMA", math.inf)
    monkeypatch.setattr(bgnbd, "ONSEL_LN_R_SAPMA", math.inf)
    assert log_onsel(np.array([1.0, -7.0, 3.0, 12.0])) == 0


@pytest.mark.parametrize("model", [mbgnbd, bgnbd], ids=["mbgnbd", "bgnbd"])
def test_bos_girdi_valueerror(model):
    with pytest.raises(ValueError):
        model.fit([], [], [])
