"""analitik.yenileme (mbgnbd-sim-v1) ve stüdyo Riskteki Parası."""

import uuid
from datetime import date
from decimal import Decimal

import numpy as np
import pytest
from scipy.integrate import dblquad
from scipy.special import betaln
from scipy.stats import beta, gamma

from analitik import mbgnbd
from analitik.bgnbd import BGNBDParametreleri
from analitik.riskteki_para import yenileme_riskteki_para
from analitik.yenileme import simule_et, tohum_turet, yenileme_olasiligi

PRM = BGNBDParametreleri(r=3.0, alfa=12.0, a=1.0, b=19.0)    # ortalama aralık ~4 gün, E[p] = 0.05


def test_p_hayatta_sifirsa_p_yenileme_sifir():
    rng = np.random.default_rng(0)
    for pencere, hak in ((30.0, None), (None, 8), (40.0, 8)):
        assert simule_et(0.0, PRM, x=10, T=60, rng=rng, pencere_gun=pencere, kalan_hak=hak) == 0.0


@pytest.mark.parametrize("hak", [None, 6])
def test_kalan_gun_arttikca_p_yenileme_artmaz(hak):
    tohum = tohum_turet(uuid.UUID(int=7), date(2026, 10, 1))
    degerler = [yenileme_olasiligi(PRM, 15, 55, 60, pencere_gun=g, kalan_hak=hak, tohum=tohum).p_yenileme
                for g in (5, 15, 30, 60, 120)]
    assert all(b <= a for a, b in zip(degerler, degerler[1:])), degerler


def test_cok_sik_gelen_dusuk_p_li_uye_yuksek():
    sik = BGNBDParametreleri(r=50.0, alfa=100.0, a=1.0, b=999.0)       # λ ≈ günde 0.5, E[p] = 0.001
    sonuc = yenileme_olasiligi(sik, x=60, t_x=119, T=120, pencere_gun=30, kalan_hak=None, tohum=1)
    assert sonuc.p_hayatta_simdi > 0.99
    assert sonuc.p_yenileme > 0.9


def test_ayni_tohum_ayni_sonuc_farkli_tohum_farkli():
    tohum = tohum_turet(uuid.UUID(int=42), date(2026, 10, 1))
    a = yenileme_olasiligi(PRM, 8, 30, 45, pencere_gun=20, kalan_hak=None, tohum=tohum)
    b = yenileme_olasiligi(PRM, 8, 30, 45, pencere_gun=20, kalan_hak=None, tohum=tohum)
    assert a == b
    assert tohum != tohum_turet(uuid.UUID(int=42), date(2026, 10, 2))


def test_sure_bazli_simulasyon_sonsal_integralle_eslesir():
    # Hayattaysa D gün sonunda hayatta olma: E[exp(−λ·p·D)], λ ~ Gamma(r+x, α+T), p ~ Beta(a, b+x+1)
    x, t_x, T, D = 6, 30.0, 50.0, 25.0
    yogunluk = lambda p, lam: gamma.pdf(lam, PRM.r + x, scale=1 / (PRM.alfa + T)) * beta.pdf(p, PRM.a, PRM.b + x + 1)
    beklenen_sag = dblquad(lambda p, lam: yogunluk(p, lam) * np.exp(-lam * p * D), 0, 3, 0, 1)[0]
    p_simdi = float(mbgnbd.p_hayatta(PRM, [x], [t_x], [T])[0])
    n = 400_000
    sim = simule_et(p_simdi, PRM, x, T, np.random.default_rng(3), pencere_gun=D, n=n)
    beklenen = p_simdi * beklenen_sag
    assert sim == pytest.approx(beklenen, abs=4 * np.sqrt(beklenen * (1 - beklenen) / n))


def test_giris_bazli_son_kullanmasiz_kapali_form():
    # Son kullanma yoksa: P = P(hayatta) · E[(1−p)^R], p ~ Beta(a, b+x+1)  →  B(a, b+x+1+R)/B(a, b+x+1)
    x, T, R = 6, 50.0, 5
    p_simdi = float(mbgnbd.p_hayatta(PRM, [x], [30.0], [T])[0])
    beklenen = p_simdi * np.exp(betaln(PRM.a, PRM.b + x + 1 + R) - betaln(PRM.a, PRM.b + x + 1))
    n = 400_000
    sim = simule_et(p_simdi, PRM, x, T, np.random.default_rng(4), pencere_gun=None, kalan_hak=R, n=n)
    assert sim == pytest.approx(beklenen, abs=4 * np.sqrt(beklenen * (1 - beklenen) / n))


def test_riskteki_para_uc_durumlar():
    assert yenileme_riskteki_para(Decimal("1"), Decimal("6000.00")) == Decimal("0.00")
    assert yenileme_riskteki_para(Decimal("0"), Decimal("6000.00")) == Decimal("6000.00")
    assert yenileme_riskteki_para(Decimal("0.375"), Decimal("6000.00")) == Decimal("3750.00")
    assert yenileme_riskteki_para(Decimal("0.33335"), Decimal("100.00")) == Decimal("66.66")   # 0.3334'e yuvarlanır
