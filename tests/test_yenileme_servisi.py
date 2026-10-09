"""Yenileme servisi, çalıştırma komutunun kilidi ve GET /panel/yenilemeler (panosu_test)."""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from conftest import basliklar
from servisler import yenileme_calistir
from servisler.yenileme_calistir import IzinsizVeritabani, calistir, hedef_dogrula

BUGUN = datetime.now(timezone(timedelta(hours=3))).date()     # işletme saat dilimi: Europe/Istanbul (UTC+3)


@pytest.fixture()
def kucuk_isletme(admin_engine, iki_kiraci):
    """A işletmesinde 30 üye (düzenli ziyaretler) ve 4 aktif paket. Temizliği iki_kiraci yapar."""
    a, _ = iki_kiraci
    rng = np.random.default_rng(5)
    i = str(a.isletme_id)
    musteriler = [uuid.uuid4() for _ in range(30)]
    with admin_engine.begin() as con:
        for no, m in enumerate(musteriler):
            con.execute(text("INSERT INTO musteriler (musteri_id, isletme_id, ad_soyad) VALUES (:m, :i, :a)"),
                        {"m": str(m), "i": i, "a": f"Üye {no}"})
            gun = -float(rng.uniform(30, 200))
            while gun < -0.5:
                con.execute(text("INSERT INTO ziyaretler (isletme_id, musteri_id, ziyaret_zamani) "
                                 "VALUES (:i, :m, now() + make_interval(secs => :s))"),
                            {"i": i, "m": str(m), "s": gun * 86400})
                if no % 3 == 0 and gun > -60 and rng.random() < 0.3:       # bir kısmı bırakır
                    break
                gun += float(rng.gamma(8, 5 / 8))
        paketler = [
            (musteriler[0], "sure", "1 Aylık", BUGUN - timedelta(days=20), BUGUN + timedelta(days=10), None, "2500.00"),
            (musteriler[1], "sure", "3 Aylık", BUGUN - timedelta(days=60), BUGUN + timedelta(days=30), None, "6000.00"),
            (musteriler[2], "giris", "12 Giriş", BUGUN - timedelta(days=15), BUGUN + timedelta(days=45), 12, "800.00"),
            (musteriler[3], "sure", "6 Aylık", BUGUN - timedelta(days=100), BUGUN + timedelta(days=80), None, "10000.00"),
        ]
        for m, tur, ad, bas, bit, hak, ucret in paketler:
            con.execute(text("INSERT INTO musteri_paketleri (isletme_id, musteri_id, tur, ad, baslangic_tarihi, "
                             "bitis_tarihi, giris_hakki, ucret) VALUES (:i, :m, :t, :a, :b, :e, :h, :u)"),
                        {"i": i, "m": str(m), "t": tur, "a": ad, "b": bas, "e": bit, "h": hak, "u": ucret})
    return a


def _riskler(admin_engine, isletme_id):
    with admin_engine.connect() as con:
        return con.execute(text(
            "SELECT paket_id, p_yenileme, yenileme_tutari, riskteki_para, kalan_gun, kalan_giris, hesaplanma_zamani "
            "FROM yenileme_riskleri WHERE isletme_id = :i ORDER BY paket_id"), {"i": str(isletme_id)}).all()


def test_servis_yazar_ve_ikinci_calistirma_idempotent(admin_engine, kucuk_isletme):
    a = kucuk_isletme
    assert calistir("panosu_test", a.isletme_id, BUGUN) == 4
    ilk = _riskler(admin_engine, a.isletme_id)
    assert len(ilk) == 4
    for satir in ilk:
        assert Decimal(0) <= satir.p_yenileme <= Decimal(1)
        beklenen = ((1 - satir.p_yenileme) * satir.yenileme_tutari).quantize(Decimal("0.01"), ROUND_HALF_UP)
        assert satir.riskteki_para == beklenen
    assert sum(s.kalan_giris is not None for s in ilk) == 1                       # yalnız giriş paketinde
    assert sum(s.kalan_gun is not None for s in ilk) == 3                         # yalnız süre paketlerinde

    assert calistir("panosu_test", a.isletme_id, BUGUN) == 4
    ikinci = _riskler(admin_engine, a.isletme_id)
    assert len(ikinci) == 4                                                       # satır sayısı değişmez
    assert [s.p_yenileme for s in ikinci] == [s.p_yenileme for s in ilk]          # aynı tohum, aynı sonuç
    assert all(b.hesaplanma_zamani >= i.hesaplanma_zamani for i, b in zip(ilk, ikinci))


def test_panel_yenilemeler(admin_engine, kucuk_isletme, iki_kiraci):
    from main import app
    a, b = iki_kiraci
    calistir("panosu_test", a.isletme_id, BUGUN)
    istemci = TestClient(app)

    yanit = istemci.get("/panel/yenilemeler", params={"gun": 45}, headers=basliklar(a))
    assert yanit.status_code == 200, yanit.text
    govde = yanit.json()
    assert govde["paket_sayisi"] == 3                                             # 80 gün sonra biten dışarıda
    riskler = [Decimal(o["riskteki_para"]) for o in govde["ogeler"]]
    assert riskler == sorted(riskler, reverse=True)
    assert Decimal(govde["toplam_riskteki_para"]) == sum(riskler)

    assert istemci.get("/panel/yenilemeler", params={"gun": 90}, headers=basliklar(a)).json()["paket_sayisi"] == 4
    assert istemci.get("/panel/yenilemeler", headers=basliklar(b)).json()["paket_sayisi"] == 0   # başka kiracı


def _p_hayatta(admin_engine, isletme_id) -> dict:
    with admin_engine.connect() as con:
        return dict(con.execute(text("SELECT paket_id, p_hayatta_simdi FROM yenileme_riskleri WHERE isletme_id = :i"),
                                {"i": str(isletme_id)}).all())


def test_sonuc_fiziksel_satir_sirasindan_bagimsiz(admin_engine, kucuk_isletme):
    """M3 uyumu üye sırasına duyarlı; yenileme_hesapla sıralı okuduğu için UPDATE'in değiştirdiği fiziksel satır
    sırası sonucu değiştirmemeli (demo tazelemesinde görülen 0,0001'lik farkların nedeni)."""
    a = kucuk_isletme
    calistir("panosu_test", a.isletme_id, BUGUN)
    ilk = _p_hayatta(admin_engine, a.isletme_id)

    with admin_engine.begin() as con:                    # yarısını, sonra öbür yarısını tablonun sonuna taşı
        for kalan in (0, 1):
            con.execute(text(
                "UPDATE ziyaretler SET notlar = notlar WHERE isletme_id = :i AND ziyaret_id IN ("
                "  SELECT ziyaret_id FROM (SELECT ziyaret_id, row_number() OVER (ORDER BY ctid) AS n "
                "  FROM ziyaretler WHERE isletme_id = :i) t WHERE n % 2 = :k)"),
                {"i": str(a.isletme_id), "k": kalan})

    calistir("panosu_test", a.isletme_id, BUGUN)
    assert _p_hayatta(admin_engine, a.isletme_id) == ilk


@pytest.mark.parametrize("esik, beklenen", [(1000, "mbgnbd-onsel-v1"), (1, "mbgnbd-map-v3")])
def test_veri_esigi_model_surumunu_belirler(admin_engine, kucuk_isletme, oturum, monkeypatch, esik, beklenen):
    """Below the data threshold the learned prior is used and the rows carry the preliminary version (K83)."""
    from analitik import soguk_baslangic
    from servisler.yenileme_servisi import on_tahmin_mi

    monkeypatch.setattr(soguk_baslangic, "ASGARI_TEKRARLI_UYE", esik)
    monkeypatch.setattr(soguk_baslangic, "ASGARI_GECMIS_GUN", 1)
    a = kucuk_isletme
    calistir("panosu_test", a.isletme_id, BUGUN)
    with admin_engine.connect() as con:
        surumler = con.execute(text("SELECT DISTINCT model_versiyonu FROM yenileme_riskleri WHERE isletme_id = :i"),
                               {"i": str(a.isletme_id)}).scalars().all()
    assert surumler == [beklenen]
    assert on_tahmin_mi(oturum(a)) == (beklenen == "mbgnbd-onsel-v1")


@pytest.mark.parametrize("ad", ["panosu", "", None, "panosu_demo_eski", "demo", "test"])
def test_kilit_reddeder(ad):
    with pytest.raises(IzinsizVeritabani):
        hedef_dogrula(ad)


@pytest.mark.parametrize("ad", ["panosu", "panosu_canli"])
def test_komut_baglanmadan_reddeder(monkeypatch, ad):
    def _yasak(*a, **k):
        raise AssertionError("Kilit, bağlantı kurulmadan önce devreye girmeliydi")
    monkeypatch.setattr(yenileme_calistir, "create_engine", _yasak)
    with pytest.raises(IzinsizVeritabani):
        calistir(ad, uuid.uuid4())
    with pytest.raises(SystemExit):
        yenileme_calistir.main(["--veritabani", ad, "--isletme", str(uuid.uuid4())])


def test_kilit_demo_ve_test_kabul():
    hedef_dogrula("panosu_demo")
    hedef_dogrula("panosu_test")
