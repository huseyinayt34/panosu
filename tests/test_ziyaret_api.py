"""Ziyaret API testleri (TestClient + panosu_test, RLS gerçek rolle devrede). Para Decimal ile karşılaştırılır."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from conftest import basliklar

GECMIS = "2026-01-15T14:30:00+03:00"


@pytest.fixture()
def istemci():
    from main import app
    return TestClient(app)


def _hizmet(istemci, kiraci, **alanlar):
    yanit = istemci.post("/hizmetler", json=alanlar, headers=basliklar(kiraci))
    assert yanit.status_code == 201, yanit.text
    return yanit.json()


def _ziyaret_istegi(istemci, kiraci, musteri_id, **govde):
    govde.setdefault("ziyaret_zamani", GECMIS)
    return istemci.post(f"/musteriler/{musteri_id}/ziyaretler", json=govde, headers=basliklar(kiraci))


def _ziyaret(istemci, kiraci, musteri_id, **govde):
    yanit = _ziyaret_istegi(istemci, kiraci, musteri_id, **govde)
    assert yanit.status_code == 201, yanit.text
    return yanit.json()


def _ziyaretler(istemci, kiraci, musteri_id):
    yanit = istemci.get(f"/musteriler/{musteri_id}/ziyaretler", headers=basliklar(kiraci))
    assert yanit.status_code == 200
    return yanit.json()


# ---------------------------------------------------------------- Kalemsiz ziyaret

def test_kalemsiz_ziyarette_toplam_zorunlu(istemci, iki_kiraci):
    a, _ = iki_kiraci
    yanit = _ziyaret_istegi(istemci, a, a.musteri_id)
    assert yanit.status_code == 422
    assert "toplam_tutar" in yanit.json()["detail"]

    z = _ziyaret(istemci, a, a.musteri_id, toplam_tutar="150.00", odeme_yontemi="kart", notlar="İlk gelişi")
    assert "isletme_id" not in z
    assert Decimal(z["toplam_tutar"]) == Decimal("150.00")
    assert (z["durum"], z["odeme_yontemi"], z["notlar"], z["kalemler"]) == ("tamamlandi", "kart", "İlk gelişi", [])
    assert z["musteri_id"] == str(a.musteri_id)


# ---------------------------------------------------------------- Kalemli ziyaret

def test_kalemli_ziyaret_sunucuda_hesaplanir(istemci, iki_kiraci):
    a, _ = iki_kiraci
    kesim = _hizmet(istemci, a, ad="Saç Kesimi", liste_fiyati="250.00")

    z = _ziyaret(istemci, a, a.musteri_id, kalemler=[
        {"hizmet_id": kesim["hizmet_id"], "adet": 2},                                  # liste fiyatı devralınır
        {"aciklama": "Şampuan", "birim_fiyat": "100.00", "indirim_tutari": "20.00"},     # indirim uygulanır
    ])
    kalemler = sorted(z["kalemler"], key=lambda k: k["aciklama"] or "")
    hizmetli, serbest = kalemler
    assert hizmetli["hizmet_id"] == kesim["hizmet_id"]
    assert Decimal(hizmetli["birim_fiyat"]) == Decimal("250.00")
    assert Decimal(hizmetli["tutar"]) == Decimal("500.00")
    assert Decimal(serbest["tutar"]) == Decimal("80.00")
    assert Decimal(z["toplam_tutar"]) == Decimal("580.00")

    detay = istemci.get(f"/ziyaretler/{z['ziyaret_id']}", headers=basliklar(a)).json()
    assert Decimal(detay["toplam_tutar"]) == Decimal("580.00")
    assert len(detay["kalemler"]) == 2


def test_istemci_toplami_kalemlerle_uyusmali(istemci, iki_kiraci):
    a, _ = iki_kiraci
    kalem = {"aciklama": "Bakım", "birim_fiyat": "100.00", "adet": 3}

    yanit = _ziyaret_istegi(istemci, a, a.musteri_id, toplam_tutar="299.99", kalemler=[kalem])
    assert yanit.status_code == 422
    assert _ziyaretler(istemci, a, a.musteri_id) == []

    z = _ziyaret(istemci, a, a.musteri_id, toplam_tutar="300", kalemler=[kalem])
    assert Decimal(z["toplam_tutar"]) == Decimal("300.00")


def test_negatif_kalem_tutari_422(istemci, iki_kiraci):
    a, _ = iki_kiraci
    yanit = _ziyaret_istegi(istemci, a, a.musteri_id, kalemler=[
        {"aciklama": "Geçerli", "birim_fiyat": "50.00"},
        {"aciklama": "Aşırı indirim", "birim_fiyat": "10.00", "indirim_tutari": "50.00"},
    ])
    assert yanit.status_code == 422
    assert _ziyaretler(istemci, a, a.musteri_id) == []          # hiçbiri yazılmadı


@pytest.mark.parametrize("kalem", [
    {"adet": 1, "birim_fiyat": "10"},                          # hizmet_id ve aciklama yok
    {"aciklama": "Fiyatsız"},                                   # hizmetsiz kalemde birim_fiyat zorunlu
    {"aciklama": "Sıfır adet", "birim_fiyat": "10", "adet": 0},
])
def test_gecersiz_kalem_422(istemci, iki_kiraci, kalem):
    a, _ = iki_kiraci
    assert _ziyaret_istegi(istemci, a, a.musteri_id, kalemler=[kalem]).status_code == 422


def test_liste_fiyati_olmayan_hizmet_birim_fiyat_ister(istemci, iki_kiraci):
    a, _ = iki_kiraci
    h = _hizmet(istemci, a, ad="Fiyatı Değişken")
    assert _ziyaret_istegi(istemci, a, a.musteri_id, kalemler=[{"hizmet_id": h["hizmet_id"]}]).status_code == 422
    z = _ziyaret(istemci, a, a.musteri_id, kalemler=[{"hizmet_id": h["hizmet_id"], "birim_fiyat": "75.50"}])
    assert Decimal(z["toplam_tutar"]) == Decimal("75.50")


def test_pasif_hizmet_gecmis_kayitta_kullanilabilir(istemci, iki_kiraci):
    a, _ = iki_kiraci
    h = _hizmet(istemci, a, ad="Eski Paket", liste_fiyati="40.00")
    istemci.patch(f"/hizmetler/{h['hizmet_id']}", json={"aktif_mi": False}, headers=basliklar(a))
    z = _ziyaret(istemci, a, a.musteri_id, kalemler=[{"hizmet_id": h["hizmet_id"]}])
    assert Decimal(z["toplam_tutar"]) == Decimal("40.00")


# ---------------------------------------------------------------- Kiracılar arası

def test_baska_kiracinin_hizmeti_kalemde_422(istemci, iki_kiraci):
    a, b = iki_kiraci
    b_hizmeti = _hizmet(istemci, b, ad="B Hizmeti", liste_fiyati="10.00")
    yanit = _ziyaret_istegi(istemci, a, a.musteri_id, kalemler=[{"hizmet_id": b_hizmeti["hizmet_id"]}])
    assert yanit.status_code == 422
    assert "Hizmet bulunamadı" in yanit.json()["detail"]
    assert _ziyaretler(istemci, a, a.musteri_id) == []


def test_baska_kiracinin_musterisine_ziyaret_404(istemci, iki_kiraci):
    a, b = iki_kiraci
    assert _ziyaret_istegi(istemci, a, b.musteri_id, toplam_tutar="10").status_code == 404
    assert istemci.get(f"/musteriler/{b.musteri_id}/ziyaretler", headers=basliklar(a)).status_code == 404
    assert istemci.get(f"/musteriler/{b.musteri_id}/ozet", headers=basliklar(a)).status_code == 404
    assert _ziyaretler(istemci, b, b.musteri_id) == []


def test_baska_kiracinin_ziyareti_404(istemci, iki_kiraci):
    a, b = iki_kiraci
    z = _ziyaret(istemci, b, b.musteri_id, toplam_tutar="99.00")
    yol = f"/ziyaretler/{z['ziyaret_id']}"
    assert istemci.get(yol, headers=basliklar(a)).status_code == 404
    assert istemci.patch(yol, json={"durum": "iptal"}, headers=basliklar(a)).status_code == 404
    assert istemci.get(yol, headers=basliklar(b)).json()["durum"] == "tamamlandi"


# ---------------------------------------------------------------- Zaman

def test_saat_dilimsiz_zaman_istanbul_saatiyle_kaydedilir(istemci, iki_kiraci):
    a, _ = iki_kiraci
    z = _ziyaret(istemci, a, a.musteri_id, ziyaret_zamani="2026-01-15T14:30:00", toplam_tutar="10")
    kayitli = datetime.fromisoformat(z["ziyaret_zamani"])
    assert kayitli.tzinfo is not None
    assert kayitli.astimezone(timezone.utc) == datetime(2026, 1, 15, 11, 30, tzinfo=timezone.utc)


def test_gelecek_tarih_422(istemci, iki_kiraci):
    a, _ = iki_kiraci
    yarin = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    yanit = _ziyaret_istegi(istemci, a, a.musteri_id, ziyaret_zamani=yarin, toplam_tutar="10")
    assert yanit.status_code == 422

    az_ileri = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()   # 5 dk tolerans içinde
    assert _ziyaret_istegi(istemci, a, a.musteri_id, ziyaret_zamani=az_ileri, toplam_tutar="10").status_code == 201


def test_liste_zamana_gore_azalan(istemci, iki_kiraci):
    a, _ = iki_kiraci
    eski = _ziyaret(istemci, a, a.musteri_id, ziyaret_zamani="2026-01-01T10:00:00+03:00", toplam_tutar="1")
    yeni = _ziyaret(istemci, a, a.musteri_id, ziyaret_zamani="2026-02-01T10:00:00+03:00", toplam_tutar="2")
    assert [z["ziyaret_id"] for z in _ziyaretler(istemci, a, a.musteri_id)] == [yeni["ziyaret_id"], eski["ziyaret_id"]]

    sayfa = istemci.get(f"/musteriler/{a.musteri_id}/ziyaretler", params={"limit": 1, "offset": 1},
                        headers=basliklar(a)).json()
    assert [z["ziyaret_id"] for z in sayfa] == [eski["ziyaret_id"]]


# ---------------------------------------------------------------- Güncelleme ve özet

def test_ozet_iki_tamamlanmis_ziyaret(istemci, iki_kiraci):
    a, _ = iki_kiraci
    _ziyaret(istemci, a, a.musteri_id, ziyaret_zamani="2026-01-10T10:00:00+03:00", toplam_tutar="100.00")
    _ziyaret(istemci, a, a.musteri_id, ziyaret_zamani="2026-02-10T10:00:00+03:00", toplam_tutar="250.50")

    ozet = istemci.get(f"/musteriler/{a.musteri_id}/ozet", headers=basliklar(a)).json()
    assert ozet["musteri_id"] == str(a.musteri_id)
    assert ozet["ziyaret_sayisi"] == 2
    assert Decimal(ozet["toplam_ciro"]) == Decimal("350.50")
    assert Decimal(ozet["ort_sepet_tutari"]) == Decimal("175.25")
    assert datetime.fromisoformat(ozet["ilk_ziyaret"]) == datetime(2026, 1, 10, 7, 0, tzinfo=timezone.utc)
    assert datetime.fromisoformat(ozet["son_ziyaret"]) == datetime(2026, 2, 10, 7, 0, tzinfo=timezone.utc)


def test_iptal_edilen_ziyaret_ozete_girmez(istemci, iki_kiraci):
    a, _ = iki_kiraci
    _ziyaret(istemci, a, a.musteri_id, toplam_tutar="200.00")
    iptal = _ziyaret(istemci, a, a.musteri_id, toplam_tutar="100.00")

    yanit = istemci.patch(f"/ziyaretler/{iptal['ziyaret_id']}", json={"durum": "iptal"}, headers=basliklar(a))
    assert yanit.status_code == 200
    assert yanit.json()["durum"] == "iptal"
    assert Decimal(yanit.json()["toplam_tutar"]) == Decimal("100.00")     # tutar değişmez

    ozet = istemci.get(f"/musteriler/{a.musteri_id}/ozet", headers=basliklar(a)).json()
    assert ozet["ziyaret_sayisi"] == 1
    assert Decimal(ozet["toplam_ciro"]) == Decimal("200.00")


@pytest.mark.parametrize("govde", [
    {},
    {"toplam_tutar": "1.00"},
    {"ziyaret_zamani": GECMIS},
    {"durum": None},
    {"durum": "bilinmeyen"},
])
def test_patch_yasak_alan_ve_bos_govde_422(istemci, iki_kiraci, govde):
    a, _ = iki_kiraci
    z = _ziyaret(istemci, a, a.musteri_id, toplam_tutar="10.00")
    assert istemci.patch(f"/ziyaretler/{z['ziyaret_id']}", json=govde, headers=basliklar(a)).status_code == 422


def test_patch_odeme_ve_not_temizlenebilir(istemci, iki_kiraci):
    a, _ = iki_kiraci
    z = _ziyaret(istemci, a, a.musteri_id, toplam_tutar="10.00", odeme_yontemi="nakit", notlar="not")
    g = istemci.patch(f"/ziyaretler/{z['ziyaret_id']}", json={"notlar": None}, headers=basliklar(a)).json()
    assert (g["notlar"], g["odeme_yontemi"], g["durum"]) == (None, "nakit", "tamamlandi")


# ---------------------------------------------------------------- Silinmiş müşteri ve roller

def test_silinmis_musteriye_ziyaret_eklenemez(istemci, iki_kiraci):
    a, _ = iki_kiraci
    m = istemci.post("/musteriler", json={"ad_soyad": "Silinecek"}, headers=basliklar(a)).json()
    assert istemci.delete(f"/musteriler/{m['musteri_id']}", headers=basliklar(a)).status_code == 204
    assert _ziyaret_istegi(istemci, a, m["musteri_id"], toplam_tutar="10").status_code == 404
    assert istemci.get(f"/musteriler/{m['musteri_id']}/ozet", headers=basliklar(a)).status_code == 404


def test_calisan_ziyaret_girebilir(istemci, calisan):
    z = _ziyaret(istemci, calisan, calisan.musteri_id, toplam_tutar="45.00")
    yanit = istemci.patch(f"/ziyaretler/{z['ziyaret_id']}", json={"durum": "gelmedi"}, headers=basliklar(calisan))
    assert yanit.status_code == 200
