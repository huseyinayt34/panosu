"""analitik.yenileme (mbgnbd-map-v3) ve stüdyo Riskteki Parası."""

import uuid
from datetime import date
from decimal import Decimal

import numpy as np
import pytest
from scipy.integrate import dblquad, quad
from scipy.special import betaln
from scipy.stats import beta, gamma

from analitik import mbgnbd
from analitik.bgnbd import BGNBDParametreleri
from analitik.riskteki_para import yenileme_riskteki_para
from analitik.yenileme import kesin_yenileme, simule_et, tohum_turet, yenileme_olasiligi

PRM = BGNBDParametreleri(r=3.0, alfa=12.0, a=1.0, b=19.0)    # ortalama aralık ~4 gün, E[p] = 0.05


def test_p_hayatta_sifirsa_p_yenileme_sifir():
    rng = np.random.default_rng(0)
    for pencere, hak in ((30.0, None), (None, 8), (40.0, 8)):
        assert simule_et(0.0, PRM, x=10, T=60, rng=rng, pencere_gun=pencere, kalan_hak=hak) == 0.0


@pytest.mark.parametrize("hak", [None, 6])
def test_kalan_gun_arttikca_p_yenileme_artmaz(hak):
    degerler = [yenileme_olasiligi(PRM, 15, 55, 60, pencere_gun=g, kalan_hak=hak).p_yenileme
                for g in (5, 15, 30, 60, 120)]
    assert all(b <= a for a, b in zip(degerler, degerler[1:])), degerler


def test_cok_sik_gelen_dusuk_p_li_uye_yuksek():
    sik = BGNBDParametreleri(r=50.0, alfa=100.0, a=1.0, b=999.0)       # λ ≈ günde 0.5, E[p] = 0.001
    sonuc = yenileme_olasiligi(sik, x=60, t_x=119, T=120, pencere_gun=30, kalan_hak=None)
    assert sonuc.p_hayatta_simdi > 0.99
    assert sonuc.p_yenileme > 0.9


def test_ayni_tohum_ayni_sonuc_farkli_tohum_farkli():
    tohum = tohum_turet(uuid.UUID(int=42), date(2026, 10, 1))
    a = simule_et(0.8, PRM, 8, 45, np.random.default_rng(tohum), pencere_gun=20)
    b = simule_et(0.8, PRM, 8, 45, np.random.default_rng(tohum), pencere_gun=20)
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


# --- K61: exact P(renewal) (full Rao-Blackwellization of the Monte Carlo) --------------------------------------------
DURUMLAR = [   # (prm, x, t_x, T, pencere_gun, kalan_hak): duration, entry without expiry, entry with expiry, edge cases
    (PRM, 6, 30.0, 50.0, 25.0, None),
    (PRM, 6, 30.0, 50.0, None, 5),
    (PRM, 6, 30.0, 50.0, 40.0, 8),
    (BGNBDParametreleri(r=0.6, alfa=3.0, a=0.4, b=2.5), 2, 10.0, 90.0, 60.0, None),   # heavy-tailed, high dropout
    (BGNBDParametreleri(r=390.0, alfa=700.0, a=1.0, b=290.0), 40, 170.0, 180.0, 30.0, 12),   # demo-like (κ ridge)
    (BGNBDParametreleri(r=2.0, alfa=5.0, a=2.0, b=3.0), 0, 0.0, 1.0, 10.0, 1),               # x = 0, one right left
]


@pytest.mark.parametrize("prm, x, t_x, T, pencere, hak", DURUMLAR)
def test_kesin_formul_monte_carlo_ile_eslesir(prm, x, t_x, T, pencere, hak):
    """The exact value is the n -> infinity limit of simule_et: within 4 standard errors at n = 400 000."""
    p_simdi = float(mbgnbd.p_hayatta(prm, [x], [t_x], [T])[0])
    kesin = kesin_yenileme(p_simdi, prm, x, T, pencere_gun=pencere, kalan_hak=hak)
    n = 400_000
    sim = simule_et(p_simdi, prm, x, T, np.random.default_rng(5), pencere_gun=pencere, kalan_hak=hak, n=n)
    assert sim == pytest.approx(kesin, abs=4 * np.sqrt(max(kesin * (1 - kesin), 1e-12) / n))


@pytest.mark.parametrize("prm, x, T, D", [(PRM, 6, 50.0, 25.0), (PRM, 0, 3.0, 400.0),
                                          (BGNBDParametreleri(r=0.6, alfa=0.5, a=0.2, b=0.7), 30, 400.0, 2.0)])
def test_sure_bazli_kesin_formul_sayisal_integralle_eslesir(prm, x, T, D):
    """Duration-based: E[(1 + p·D/(α+T))^-(r+x)], p ~ Beta(a, b+x+1), by 1-D quadrature."""
    integral = quad(lambda p: beta.pdf(p, prm.a, prm.b + x + 1) * (1 + p * D / (prm.alfa + T)) ** -(prm.r + x),
                    0, 1, limit=200, epsabs=1e-13)[0]
    assert kesin_yenileme(1.0, prm, x, T, pencere_gun=D) == pytest.approx(integral, rel=1e-9, abs=1e-12)


def test_cok_hakli_giris_bazli_sure_bazliya_yakinsar():
    """min(K, R) = K when R is huge: entry-with-expiry must equal the duration-based formula."""
    for pencere in (5.0, 30.0, 90.0):
        assert kesin_yenileme(0.7, PRM, 6, 50.0, pencere_gun=pencere, kalan_hak=5_000) == pytest.approx(
            kesin_yenileme(0.7, PRM, 6, 50.0, pencere_gun=pencere), rel=1e-10)


def test_kalan_hak_arttikca_p_yenileme_artmaz():
    for pencere in (None, 40.0):
        degerler = [kesin_yenileme(0.9, PRM, 6, 50.0, pencere_gun=pencere, kalan_hak=r) for r in range(0, 30)]
        assert all(b <= a for a, b in zip(degerler, degerler[1:])), degerler


def test_kesin_sinirlar_ve_uc_durumlar():
    for pencere, hak in ((30.0, None), (None, 8), (40.0, 8)):
        assert kesin_yenileme(0.0, PRM, 10, 60.0, pencere_gun=pencere, kalan_hak=hak) == 0.0
        for p_simdi in (1e-5, 0.3, 1.0):
            deger = kesin_yenileme(p_simdi, PRM, 10, 60.0, pencere_gun=pencere, kalan_hak=hak)
            assert 0.0 < deger <= p_simdi           # never exactly 0 from noise (K60 case), never above p_alive
    for pencere, hak in ((0.0, None), (-3.0, 4), (20.0, 0)):
        assert kesin_yenileme(0.42, PRM, 10, 60.0, pencere_gun=pencere, kalan_hak=hak) == 0.42


def test_kesin_sonuc_belirlenimci_ve_varyanssiz():
    """No random numbers: the same input gives the same bits, independent of call order."""
    a = [yenileme_olasiligi(PRM, x, 30, 60, pencere_gun=20, kalan_hak=None).p_yenileme for x in (3, 8, 15)]
    b = [yenileme_olasiligi(PRM, x, 30, 60, pencere_gun=20, kalan_hak=None).p_yenileme for x in (15, 8, 3)][::-1]
    assert a == b


def test_kesin_formul_monte_carlo_varyansini_sifirlar():
    """Rao-Blackwell: 20 Monte Carlo runs at n = 2 000 scatter around the exact value; their mean is within 4 SE."""
    p_simdi = float(mbgnbd.p_hayatta(PRM, [8], [30.0], [45.0])[0])
    kesin = kesin_yenileme(p_simdi, PRM, 8, 45.0, pencere_gun=20)
    sim = np.array([simule_et(p_simdi, PRM, 8, 45.0, np.random.default_rng(t), pencere_gun=20) for t in range(20)])
    assert sim.std(ddof=1) > 0.001                  # the old estimator really is noisy
    assert abs(sim.mean() - kesin) < 4 * sim.std(ddof=1) / np.sqrt(20)
