"""Paket API testleri (TestClient + panosu_test, RLS gerçek rolle devrede). Para Decimal ile karşılaştırılır."""

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from conftest import basliklar


@pytest.fixture()
def istemci():
    from main import app
    return TestClient(app)


def _paket_istegi(istemci, kiraci, musteri_id, **govde):
    varsayilan = {"tur": "sure", "ad": "1 Aylık", "baslangic_tarihi": "2026-08-01",
                  "bitis_tarihi": "2026-09-01", "ucret": "2500.00"}
    return istemci.post(f"/musteriler/{musteri_id}/paketler", json={**varsayilan, **govde}, headers=basliklar(kiraci))


def _paket(istemci, kiraci, musteri_id, **govde):
    yanit = _paket_istegi(istemci, kiraci, musteri_id, **govde)
    assert yanit.status_code == 201, yanit.text
    return yanit.json()


def test_olusturma_ve_okuma(istemci, iki_kiraci):
    a, _ = iki_kiraci
    p = _paket(istemci, a, a.musteri_id, ad="6 Aylık", bitis_tarihi="2027-02-01", ucret="10000.00")
    assert "isletme_id" not in p
    assert (p["tur"], p["ad"], p["durum"], p["onceki_paket_id"], p["kalan_giris"]) == ("sure", "6 Aylık", "aktif", None, None)
    assert Decimal(p["ucret"]) == Decimal("10000.00")

    detay = istemci.get(f"/paketler/{p['paket_id']}", headers=basliklar(a))
    assert detay.status_code == 200 and detay.json()["paket_id"] == p["paket_id"]


@pytest.mark.parametrize("govde", [
    {"tur": "sure", "bitis_tarihi": None},
    {"tur": "sure", "giris_hakki": 12},
    {"tur": "giris", "bitis_tarihi": None},
    {"tur": "giris", "bitis_tarihi": None, "giris_hakki": 0},
    {"bitis_tarihi": "2026-07-01"},
    {"ucret": "-5"},
])
def test_tur_kurali_ihlali_422(istemci, iki_kiraci, govde):
    a, _ = iki_kiraci
    assert _paket_istegi(istemci, a, a.musteri_id, **govde).status_code == 422


def test_cakisan_paket_409(istemci, iki_kiraci):
    a, _ = iki_kiraci
    _paket(istemci, a, a.musteri_id)                                             # 2026-08-01 .. 2026-09-01
    yanit = _paket_istegi(istemci, a, a.musteri_id, baslangic_tarihi="2026-08-20", bitis_tarihi="2026-09-20")
    assert yanit.status_code == 409
    # Bitişte (veya sonra) başlayan yenileme çakışmaz
    _paket(istemci, a, a.musteri_id, baslangic_tarihi="2026-09-01", bitis_tarihi="2026-10-01")


def test_onceki_paket_otomatik_baglanir(istemci, iki_kiraci):
    a, _ = iki_kiraci
    ilk = _paket(istemci, a, a.musteri_id)
    ikinci = _paket(istemci, a, a.musteri_id, baslangic_tarihi="2026-09-01", bitis_tarihi="2026-10-01")
    assert ikinci["onceki_paket_id"] == ilk["paket_id"]

    liste = istemci.get(f"/musteriler/{a.musteri_id}/paketler", headers=basliklar(a)).json()
    assert [p["paket_id"] for p in liste] == [ikinci["paket_id"], ilk["paket_id"]]      # başlangıç azalan


def test_baska_musterinin_paketi_onceki_olamaz(istemci, iki_kiraci, admin_engine):
    a, _ = iki_kiraci
    diger = uuid.uuid4()
    with admin_engine.begin() as con:
        con.execute(text("INSERT INTO musteriler (musteri_id, isletme_id, ad_soyad) VALUES (:m, :i, 'Diğer')"),
                    {"m": str(diger), "i": str(a.isletme_id)})
    p = _paket(istemci, a, diger)
    yanit = _paket_istegi(istemci, a, a.musteri_id, onceki_paket_id=p["paket_id"])
    assert yanit.status_code == 422


def test_calisan_olusturamaz_ve_guncelleyemez_ama_okur(istemci, iki_kiraci, calisan):
    a, _ = iki_kiraci
    assert _paket_istegi(istemci, calisan, a.musteri_id).status_code == 403
    p = _paket(istemci, a, a.musteri_id)
    assert istemci.patch(f"/paketler/{p['paket_id']}", json={"durum": "iptal"},
                         headers=basliklar(calisan)).status_code == 403
    assert istemci.get(f"/paketler/{p['paket_id']}", headers=basliklar(calisan)).status_code == 200
    assert istemci.get(f"/musteriler/{a.musteri_id}/paketler", headers=basliklar(calisan)).status_code == 200


def test_kalan_giris_donemdeki_tamamlanmis_ziyaretlerden(istemci, iki_kiraci):
    a, _ = iki_kiraci
    p = _paket(istemci, a, a.musteri_id, tur="giris", ad="12 Giriş", baslangic_tarihi="2026-08-01",
               bitis_tarihi="2026-09-30", giris_hakki=12, ucret="800.00")
    zamanlar = ["2026-07-20T10:00:00+03:00",                                     # dönem öncesi: sayılmaz
                "2026-08-01T09:00:00+03:00", "2026-08-05T18:00:00+03:00", "2026-08-10T18:00:00+03:00"]
    idler = []
    for z in zamanlar:
        y = istemci.post(f"/musteriler/{a.musteri_id}/ziyaretler", json={"ziyaret_zamani": z, "toplam_tutar": "0"},
                         headers=basliklar(a))
        assert y.status_code == 201, y.text
        idler.append(y.json()["ziyaret_id"])
    istemci.patch(f"/ziyaretler/{idler[-1]}", json={"durum": "iptal"}, headers=basliklar(a))     # iptal sayılmaz

    detay = istemci.get(f"/paketler/{p['paket_id']}", headers=basliklar(a)).json()
    assert detay["kalan_giris"] == 12 - 2


def test_patch_yalniz_durum_ve_bitis(istemci, iki_kiraci):
    a, _ = iki_kiraci
    p = _paket(istemci, a, a.musteri_id)
    y = istemci.patch(f"/paketler/{p['paket_id']}", json={"durum": "donduruldu", "bitis_tarihi": "2026-09-15"},
                      headers=basliklar(a))
    assert y.status_code == 200, y.text
    assert (y.json()["durum"], y.json()["bitis_tarihi"]) == ("donduruldu", "2026-09-15")
    assert istemci.patch(f"/paketler/{p['paket_id']}", json={"ucret": "1"}, headers=basliklar(a)).status_code == 422
    assert istemci.patch(f"/paketler/{p['paket_id']}", json={"bitis_tarihi": None},
                         headers=basliklar(a)).status_code == 422


def test_baska_kiracinin_musterisi_ve_paketi_404(istemci, iki_kiraci):
    a, b = iki_kiraci
    p_b = _paket(istemci, b, b.musteri_id)
    assert _paket_istegi(istemci, a, b.musteri_id).status_code == 404
    assert istemci.get(f"/musteriler/{b.musteri_id}/paketler", headers=basliklar(a)).status_code == 404
    assert istemci.get(f"/paketler/{p_b['paket_id']}", headers=basliklar(a)).status_code == 404
    assert istemci.patch(f"/paketler/{p_b['paket_id']}", json={"durum": "iptal"},
                         headers=basliklar(a)).status_code == 404
