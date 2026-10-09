"""Cold start (step 8a, K81-K85, `docs/adim-8a-tasarim.md`): data guard, learned prior, empirical Bayes learning."""

import math

import numpy as np
import pytest

from analitik import mbgnbd, soguk_baslangic as sb
from analitik.bgnbd import Onsel, parametreden_teta
from analitik.ozellikler import ozellik_cikar
from analitik.yenileme import MODEL_VERSIYONU
from backtest import soguk_baslangic as bsb
from backtest.senaryolar import KALIBRASYON_GUN, uret_s6


def _s6_ozellikleri(uye: int, tohum: int):
    v = uret_s6(np.random.default_rng([8, tohum]), uye)
    secim = np.flatnonzero(v.edinim <= KALIBRASYON_GUN)
    kal = [v.zamanlar[i][v.zamanlar[i] <= KALIBRASYON_GUN] for i in secim]
    return ozellik_cikar(kal, kal, KALIBRASYON_GUN)


def test_veri_esigi_tam_sinirda():
    x = np.array([1.0] * 30 + [0.0] * 5)
    T = np.full(35, 10.0)
    T[0] = 60.0
    assert sb.veri_yeterli(x, T)                                # exactly 30 repeat members and 60 days
    assert not sb.veri_yeterli(x[1:], T[1:])                    # 29 repeat members (and 10 days)
    T[0] = 59.99
    assert not sb.veri_yeterli(x, T)                            # history just under 60 days
    assert not sb.veri_yeterli([], [])


def test_onsel_ogren_ortalama_ve_kirpilmis_sapma():
    tetalar = np.array([[0.0, 1.0, -3.0, 2.0], [2.0, 1.0, -3.0, 12.0], [4.0, 1.1, -3.0, 22.0]])
    o = sb.onsel_ogren(tetalar)
    assert o.merkez == pytest.approx((2.0, 1.0333333, -3.0, 12.0))
    assert o.sapma == pytest.approx((2.0, sb.SAPMA_TABANI, sb.SAPMA_TABANI, sb.SAPMA_TAVANI))   # 2.0, ~0.06, 0, 10
    with pytest.raises(ValueError):
        sb.onsel_ogren(tetalar[:1])


def test_onsel_log_yogunlugu():
    o = Onsel(merkez=(1.0, 2.0, 3.0, 4.0), sapma=(1.0, 2.0, 0.5, 1.0))
    assert o.log_yogunluk([2.0, 2.0, 2.0, 4.0]) == pytest.approx(-0.5 * (1.0 + 0.0 + 4.0 + 0.0))


def test_uyum_yeterli_veride_eski_model_ile_bit_bit_ayni():
    oz = _s6_ozellikleri(250, 0)
    assert sb.veri_yeterli(oz.x, oz.T)
    u = sb.uyum(oz.x, oz.t_x, oz.T)
    assert (u.model_versiyonu, u.on_tahmin) == (MODEL_VERSIYONU, False)
    assert u.prm == mbgnbd.fit(oz.x, oz.t_x, oz.T)


def test_uyum_az_veride_ogrenilmis_onsel():
    oz = _s6_ozellikleri(20, 1)
    assert not sb.veri_yeterli(oz.x, oz.T)
    u = sb.uyum(oz.x, oz.t_x, oz.T)
    assert (u.model_versiyonu, u.on_tahmin) == (sb.ON_TAHMIN_VERSIYONU, True)
    assert u.prm == mbgnbd.fit(oz.x, oz.t_x, oz.T, onsel=sb.OGRENILMIS_ONSEL)
    sira = np.random.default_rng(0).permutation(len(oz.x))      # order-free like the weak-prior fit
    assert sb.uyum(oz.x[sira], oz.t_x[sira], oz.T[sira]).prm == u.prm


def test_veri_arttikca_onselin_etkisi_azalir():
    """Bayesian update: the gap between the learned-prior and weak-prior estimates shrinks as members are added."""
    farklar = []
    for uye in (20, 1500):
        oz = _s6_ozellikleri(uye, 2)
        zayif = parametreden_teta(mbgnbd.fit(oz.x, oz.t_x, oz.T))
        ogrenilmis = parametreden_teta(mbgnbd.fit(oz.x, oz.t_x, oz.T, onsel=sb.OGRENILMIS_ONSEL))
        farklar.append(float(np.max(np.abs(zayif - ogrenilmis))))
    assert farklar[1] < farklar[0] / 3


def test_onsel_az_veride_merkeze_ceker():
    oz = _s6_ozellikleri(20, 1)
    merkez = np.array(sb.OGRENILMIS_ONSEL.merkez)
    zayif = parametreden_teta(mbgnbd.fit(oz.x, oz.t_x, oz.T))
    ogrenilmis = parametreden_teta(mbgnbd.fit(oz.x, oz.t_x, oz.T, onsel=sb.OGRENILMIS_ONSEL))
    assert np.linalg.norm(ogrenilmis - merkez) < np.linalg.norm(zayif - merkez)


def test_kayitli_onsel_demo_isletmelerinden_yeniden_uretilir():
    """OGRENILMIS_ONSEL is exactly what `python -m backtest.soguk_baslangic ogren` prints (4 decimals)."""
    onsel, tetalar = bsb.ogren()
    assert len(tetalar) == 5
    for ogrenilen, kayitli in ((onsel.merkez, sb.OGRENILMIS_ONSEL.merkez), (onsel.sapma, sb.OGRENILMIS_ONSEL.sapma)):
        assert [round(d, 4) for d in ogrenilen] == list(kayitli)
    assert all(sb.SAPMA_TABANI <= s <= sb.SAPMA_TAVANI and math.isfinite(s) for s in sb.OGRENILMIS_ONSEL.sapma)


def test_demo_ayarlari_demo_kurulumu_ile_ayni():
    from sentetik.demo_kur import SENTETIK_AYARLARI

    assert (SENTETIK_AYARLARI.referans, SENTETIK_AYARLARI.musteri_sayisi, SENTETIK_AYARLARI.gecmis_gun,
            SENTETIK_AYARLARI.tohum, SENTETIK_AYARLARI.aylik_enflasyon) == (
        bsb.DEMO_REFERANS, bsb.DEMO_MUSTERI_SAYISI, bsb.DEMO_GECMIS_GUN, bsb.DEMO_TOHUMU, 0.0)


def test_genc_studyo_backtest_duman():
    """Smoke test of the young-studio backtest (2 seeds): runs, both priors scored on the same packages."""
    s = bsb.genc_studyo("küçük stüdyo", 300, 30, range(2), sb.OGRENILMIS_ONSEL)
    assert s.paket > 0 and s.on_tahmin_orani == 1.0
    assert set(s.brier) == {"zayıf", "öğrenilmiş"} and all(0 <= b <= 1 for b in s.brier.values())
