"""analitik.aciklama: "neden riskli" kuralları (K6, K7, K9)."""

import random
from datetime import date, timedelta
from decimal import Decimal

from analitik.aciklama import neden_riskli

HESAP = date(2026, 9, 24)


def _aciklama(**degisen):
    girdi = dict(p_hayatta_simdi=Decimal("0.35"), p_yenileme=Decimal("0.28"), ziyaret_sayisi=10,
                 ilk_ziyaret=date(2026, 8, 1), son_ziyaret=date(2026, 9, 6), hesaplama_tarihi=HESAP,
                 paket_baslangic=date(2026, 7, 30), tur="sure", kalan_gun=40, kalan_giris=None)
    girdi.update(degisen)
    return neden_riskli(**girdi)


def test_dusuk_risk_esik_dahil():
    for p in ("0.85", "0.80"):
        a = _aciklama(p_hayatta_simdi=Decimal("0.95"), p_yenileme=Decimal(p))
        assert a.ana_neden == "dusuk_risk"
        assert a.cumle == "Düzenli geliyor; belirgin bir risk yok."
        assert a.sessizlik_payi is None


def test_hic_gelmedi():
    a = _aciklama(ziyaret_sayisi=0, ilk_ziyaret=None, son_ziyaret=None, paket_baslangic=date(2026, 9, 4))
    assert a.ana_neden == "hic_gelmedi"
    assert a.cumle == "Paketi 4 Eylül 2026 tarihinde aldı, o günden beri hiç gelmedi (20 gün)."
    assert a.sessiz_gun is None
    assert a.sessizlik_payi is None


def test_sessizlik():
    a = _aciklama()
    assert a.ana_neden == "sessizlik"
    assert a.normal_aralik_gun == Decimal("4.0")
    assert a.sessiz_gun == 18
    assert a.kat == Decimal("4.5")
    assert "~4 günde bir" in a.cumle and "18 gündür" in a.cumle and "4,5" in a.cumle
    assert a.p_surdurme == Decimal("0.8000")
    assert a.sessizlik_payi == Decimal("0.82")


def test_az_gecmis():
    a = _aciklama(ziyaret_sayisi=2, ilk_ziyaret=date(2026, 9, 1), son_ziyaret=date(2026, 9, 10),
                  p_hayatta_simdi=Decimal("0.30"), p_yenileme=Decimal("0.25"))
    assert a.ana_neden == "az_gecmis"
    assert a.normal_aralik_gun is None and a.kat is None
    assert a.cumle == "Yalnızca 2 kez geldi; son ziyaret 14 gün önce. Geçmiş az, tahmin belirsiz."


def test_az_gecmis_son_ziyaret_hesaplama_gununde():
    a = _aciklama(ziyaret_sayisi=2, ilk_ziyaret=date(2026, 9, 1), son_ziyaret=HESAP,
                  p_hayatta_simdi=Decimal("0.30"), p_yenileme=Decimal("0.25"))
    assert a.sessiz_gun == 0
    assert a.cumle == "Yalnızca 2 kez geldi; son ziyareti hesaplama gününde. Geçmiş az, tahmin belirsiz."


def test_tum_ziyaretler_ayni_gun_az_gecmis():
    a = _aciklama(ziyaret_sayisi=5, ilk_ziyaret=date(2026, 9, 1), son_ziyaret=date(2026, 9, 1))
    assert a.ana_neden == "az_gecmis"
    assert a.normal_aralik_gun is None


def test_uzun_sure():
    a = _aciklama(p_hayatta_simdi=Decimal("0.95"), p_yenileme=Decimal("0.50"))
    assert a.ana_neden == "uzun_sure"
    assert "40 gün" in a.cumle


def test_kalan_hak():
    a = _aciklama(p_hayatta_simdi=Decimal("0.95"), p_yenileme=Decimal("0.50"), tur="giris", kalan_gun=None,
                  kalan_giris=6)
    assert a.ana_neden == "kalan_hak"
    assert "6 giriş" in a.cumle


def test_p_aktif_sifir():
    a = _aciklama(p_hayatta_simdi=Decimal("0"), p_yenileme=Decimal("0"))
    assert a.ana_neden == "sessizlik"
    assert a.p_surdurme is None
    assert a.sessizlik_payi == Decimal("1.00")
    b = _aciklama(p_hayatta_simdi=Decimal("0"), p_yenileme=Decimal("0"), ziyaret_sayisi=2)
    assert b.ana_neden == "az_gecmis"


def test_p_yenileme_p_aktiften_buyuk():
    a = _aciklama(p_hayatta_simdi=Decimal("0.50"), p_yenileme=Decimal("0.52"))
    assert a.p_surdurme == Decimal("1.0000")
    assert a.sessizlik_payi == Decimal("1.00")
    assert a.ana_neden == "sessizlik"


def test_p_yenileme_sifir_uzun_sure():
    a = _aciklama(p_hayatta_simdi=Decimal("0.9"), p_yenileme=Decimal("0"))
    assert a.ana_neden == "uzun_sure"
    assert a.sessizlik_payi == Decimal("0.00")


def test_ozellik_carpanlar_ve_pay_araligi():
    rng = random.Random(20261002)
    for _ in range(200):
        p_aktif = Decimal(str(round(rng.uniform(0, 1), 4)))
        p_yen = Decimal(str(round(rng.uniform(0, 0.7999), 4)))
        ziyaret = rng.randint(0, 20)
        son = HESAP - timedelta(days=rng.randint(0, 60))
        ilk = son - timedelta(days=rng.randint(0, 200))
        a = _aciklama(p_hayatta_simdi=p_aktif, p_yenileme=p_yen, ziyaret_sayisi=ziyaret,
                      ilk_ziyaret=ilk if ziyaret else None, son_ziyaret=son if ziyaret else None,
                      tur=rng.choice(["sure", "giris"]), kalan_giris=rng.randint(1, 10))
        if a.sessizlik_payi is not None:
            assert Decimal(0) <= a.sessizlik_payi <= Decimal(1)
        if a.p_surdurme is not None and p_yen <= p_aktif:
            assert abs(a.p_aktif * a.p_surdurme - p_yen) <= Decimal("0.0002")
