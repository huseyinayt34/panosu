"""Müşteri API'si uçtan uca testleri (TestClient + panosu_test, RLS gerçek rolle devrede)."""

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from conftest import Kiraci

YANIT_ALANLARI = {
    "musteri_id", "ad_soyad", "telefon_e164", "eposta", "notlar", "kaynak",
    "olusturma_zamani", "guncelleme_zamani",
}


@pytest.fixture()
def istemci():
    from main import app
    return TestClient(app)


@pytest.fixture()
def calisan(admin_engine, iki_kiraci):
    """A işletmesinde 'calisan' rolünde ikinci bir kullanıcı. Test sonunda silinir."""
    a, _ = iki_kiraci
    kullanici_id = uuid.uuid4()
    k, i = str(kullanici_id), str(a.isletme_id)
    with admin_engine.begin() as con:
        con.execute(
            text("INSERT INTO kullanicilar (kullanici_id, eposta, ad_soyad) VALUES (:u, :e, 'Çalışan')"),
            {"u": k, "e": f"{k}@test.local"},
        )
        con.execute(
            text("INSERT INTO uyelikler (isletme_id, kullanici_id, rol) VALUES (:i, :u, 'calisan')"),
            {"i": i, "u": k},
        )
    try:
        yield Kiraci(a.isletme_id, kullanici_id, a.musteri_id, a.musteri_adi)
    finally:
        with admin_engine.begin() as con:
            con.execute(text("DELETE FROM uyelikler WHERE kullanici_id = :u"), {"u": k})
            con.execute(text("DELETE FROM denetim_kayitlari WHERE kullanici_id = :u"), {"u": k})
            con.execute(text("DELETE FROM kullanicilar WHERE kullanici_id = :u"), {"u": k})


def _basliklar(kiraci):
    return {"X-Kullanici-Id": str(kiraci.kullanici_id), "X-Isletme-Id": str(kiraci.isletme_id)}


def _olustur(istemci, kiraci, **alanlar):
    yanit = istemci.post("/musteriler", json=alanlar, headers=_basliklar(kiraci))
    assert yanit.status_code == 201, yanit.text
    return yanit.json()


# ---------------------------------------------------------------- 1) Oluşturma

def test_olusturma_201_ve_alanlar(istemci, iki_kiraci):
    a, _ = iki_kiraci
    m = _olustur(istemci, a, ad_soyad="  Ayşe Yılmaz  ", telefon="0532 123 45 67",
                 eposta="ayse@ornek.com", notlar="Düzenli müşteri")
    assert set(m) == YANIT_ALANLARI
    assert "isletme_id" not in m
    assert m["ad_soyad"] == "Ayşe Yılmaz"
    assert m["telefon_e164"] == "+905321234567"
    assert m["eposta"] == "ayse@ornek.com"
    assert m["notlar"] == "Düzenli müşteri"
    assert m["kaynak"] == "manuel"
    uuid.UUID(m["musteri_id"])


# ---------------------------------------------------------------- 2) Doğrulama

def test_govdede_isletme_id_422(istemci, iki_kiraci):
    a, b = iki_kiraci
    yanit = istemci.post("/musteriler", json={"ad_soyad": "Sızma", "isletme_id": str(b.isletme_id)},
                         headers=_basliklar(a))
    assert yanit.status_code == 422


def test_gecersiz_telefon_422(istemci, iki_kiraci):
    a, _ = iki_kiraci
    yanit = istemci.post("/musteriler", json={"ad_soyad": "Hatalı", "telefon": "12345"}, headers=_basliklar(a))
    assert yanit.status_code == 422


# ---------------------------------------------------------------- 3) Telefon tekilliği

def test_ayni_kiracida_ayni_telefon_409_diger_kiracida_201(istemci, iki_kiraci):
    a, b = iki_kiraci
    _olustur(istemci, a, ad_soyad="Birinci", telefon="0533 111 22 33")

    yanit = istemci.post("/musteriler", json={"ad_soyad": "İkinci", "telefon": "+905331112233"},
                         headers=_basliklar(a))
    assert yanit.status_code == 409
    assert "detail" in yanit.json()

    _olustur(istemci, b, ad_soyad="Diğer kiracı", telefon="0533 111 22 33")


# ---------------------------------------------------------------- 4) Listeleme

def test_listeleme_kiraci_sayfalama_ve_arama(istemci, iki_kiraci):
    a, b = iki_kiraci
    _olustur(istemci, a, ad_soyad="Ayşe Kaya", telefon="0532 123 45 67")
    _olustur(istemci, a, ad_soyad="Burak Demir", telefon="0544 987 65 43")
    _olustur(istemci, a, ad_soyad="Ceren Ak")
    b_musterisi = _olustur(istemci, b, ad_soyad="Ayşe B Kiracısı", telefon="0532 123 45 67")

    tumu = istemci.get("/musteriler", headers=_basliklar(a)).json()
    assert tumu["toplam"] == 4                       # 3 yeni + fixture'daki "Müşteri A"
    idler = [m["musteri_id"] for m in tumu["ogeler"]]
    assert str(a.musteri_id) in idler
    assert b_musterisi["musteri_id"] not in idler and str(b.musteri_id) not in idler

    s1 = istemci.get("/musteriler", params={"limit": 2, "offset": 0}, headers=_basliklar(a)).json()
    s2 = istemci.get("/musteriler", params={"limit": 2, "offset": 2}, headers=_basliklar(a)).json()
    assert (s1["limit"], s1["offset"], s1["toplam"]) == (2, 0, 4)
    assert len(s1["ogeler"]) == 2 and len(s2["ogeler"]) == 2
    assert [m["musteri_id"] for m in s1["ogeler"] + s2["ogeler"]] == idler

    ad = istemci.get("/musteriler", params={"q": "ayşe"}, headers=_basliklar(a)).json()
    assert [m["ad_soyad"] for m in ad["ogeler"]] == ["Ayşe Kaya"] and ad["toplam"] == 1

    tel = istemci.get("/musteriler", params={"q": "987 65"}, headers=_basliklar(a)).json()
    assert [m["ad_soyad"] for m in tel["ogeler"]] == ["Burak Demir"]

    joker = istemci.get("/musteriler", params={"q": "%"}, headers=_basliklar(a)).json()
    assert joker["toplam"] == 0                      # LIKE özel karakteri kaçışlanır


# ---------------------------------------------------------------- 5) Kiracılar arası erişim

def test_baska_kiracinin_musterisi_404(istemci, iki_kiraci):
    a, b = iki_kiraci
    yol = f"/musteriler/{b.musteri_id}"
    assert istemci.get(yol, headers=_basliklar(a)).status_code == 404
    assert istemci.patch(yol, json={"notlar": "x"}, headers=_basliklar(a)).status_code == 404
    assert istemci.delete(yol, headers=_basliklar(a)).status_code == 404

    kendi = istemci.get(yol, headers=_basliklar(b))
    assert kendi.status_code == 200
    assert kendi.json()["notlar"] is None


def test_gecersiz_uuid_422(istemci, iki_kiraci):
    a, _ = iki_kiraci
    assert istemci.get("/musteriler/uuid-degil", headers=_basliklar(a)).status_code == 422


# ---------------------------------------------------------------- 6) Kısmi güncelleme

def test_patch_kismi_gunceller(istemci, iki_kiraci):
    a, _ = iki_kiraci
    m = _olustur(istemci, a, ad_soyad="Deniz Er", telefon="0535 000 11 22", notlar="eski")
    yol = f"/musteriler/{m['musteri_id']}"

    y = istemci.patch(yol, json={"notlar": "yeni"}, headers=_basliklar(a))
    assert y.status_code == 200, y.text
    g = y.json()
    assert g["notlar"] == "yeni"
    assert (g["ad_soyad"], g["telefon_e164"], g["eposta"]) == ("Deniz Er", "+905350001122", None)
    assert datetime.fromisoformat(g["guncelleme_zamani"]) > datetime.fromisoformat(m["guncelleme_zamani"])

    temiz = istemci.patch(yol, json={"telefon": None}, headers=_basliklar(a))
    assert temiz.status_code == 200
    assert temiz.json()["telefon_e164"] is None
    assert temiz.json()["notlar"] == "yeni"

    assert istemci.patch(yol, json={}, headers=_basliklar(a)).status_code == 422
    assert istemci.patch(yol, json={"ad_soyad": None}, headers=_basliklar(a)).status_code == 422


def test_patch_telefon_cakismasi_409(istemci, iki_kiraci):
    a, _ = iki_kiraci
    _olustur(istemci, a, ad_soyad="Sahibi", telefon="0536 222 33 44")
    m = _olustur(istemci, a, ad_soyad="Diğeri")
    yanit = istemci.patch(f"/musteriler/{m['musteri_id']}", json={"telefon": "05362223344"},
                          headers=_basliklar(a))
    assert yanit.status_code == 409


# ---------------------------------------------------------------- 7) Silme

def test_silme_soft_delete(istemci, iki_kiraci):
    a, _ = iki_kiraci
    m = _olustur(istemci, a, ad_soyad="Silinecek", telefon="0537 444 55 66")
    yol = f"/musteriler/{m['musteri_id']}"

    assert istemci.delete(yol, headers=_basliklar(a)).status_code == 204
    assert istemci.get(yol, headers=_basliklar(a)).status_code == 404
    liste = istemci.get("/musteriler", headers=_basliklar(a)).json()
    assert m["musteri_id"] not in [x["musteri_id"] for x in liste["ogeler"]]

    _olustur(istemci, a, ad_soyad="Aynı Numara", telefon="0537 444 55 66")


# ---------------------------------------------------------------- 8) Roller

def test_calisan_olusturur_listeler_ama_silemez(istemci, calisan):
    m = _olustur(istemci, calisan, ad_soyad="Çalışanın Müşterisi")
    liste = istemci.get("/musteriler", headers=_basliklar(calisan))
    assert liste.status_code == 200
    assert m["musteri_id"] in [x["musteri_id"] for x in liste.json()["ogeler"]]

    yanit = istemci.delete(f"/musteriler/{m['musteri_id']}", headers=_basliklar(calisan))
    assert yanit.status_code == 403
    assert yanit.json() == {"detail": "Bu işlem için yetkiniz yok"}
