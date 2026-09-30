"""Hizmet kataloğu API testleri (TestClient + panosu_test, RLS gerçek rolle devrede)."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from conftest import basliklar

YANIT_ALANLARI = {
    "hizmet_id", "ad", "kategori", "liste_fiyati", "sure_dk", "aktif_mi", "olusturma_zamani", "guncelleme_zamani",
}


@pytest.fixture()
def istemci():
    from main import app
    return TestClient(app)


def _olustur(istemci, kiraci, **alanlar):
    yanit = istemci.post("/hizmetler", json=alanlar, headers=basliklar(kiraci))
    assert yanit.status_code == 201, yanit.text
    return yanit.json()


def test_olusturma_201_ve_alanlar(istemci, iki_kiraci):
    a, _ = iki_kiraci
    h = _olustur(istemci, a, ad="  Saç Kesimi  ", kategori="Kesim", liste_fiyati="250.00", sure_dk=30)
    assert set(h) == YANIT_ALANLARI
    assert h["ad"] == "Saç Kesimi"
    assert h["kategori"] == "Kesim"
    assert Decimal(h["liste_fiyati"]) == Decimal("250.00")
    assert h["sure_dk"] == 30
    assert h["aktif_mi"] is True


@pytest.mark.parametrize("govde", [
    {"ad": ""},
    {"ad": "Fazla", "isletme_id": "00000000-0000-0000-0000-000000000000"},
    {"ad": "Negatif", "liste_fiyati": "-1"},
    {"ad": "Üç ondalık", "liste_fiyati": "10.005"},
    {"ad": "Sıfır süre", "sure_dk": 0},
])
def test_gecersiz_govde_422(istemci, iki_kiraci, govde):
    a, _ = iki_kiraci
    assert istemci.post("/hizmetler", json=govde, headers=basliklar(a)).status_code == 422


def test_ayni_ad_409_diger_kiracida_201(istemci, iki_kiraci):
    a, b = iki_kiraci
    _olustur(istemci, a, ad="Sakal")
    yanit = istemci.post("/hizmetler", json={"ad": "Sakal"}, headers=basliklar(a))
    assert yanit.status_code == 409
    assert "detail" in yanit.json()
    _olustur(istemci, b, ad="Sakal")


def test_patch_ile_ad_cakismasi_409(istemci, iki_kiraci):
    a, _ = iki_kiraci
    _olustur(istemci, a, ad="Boya")
    h = _olustur(istemci, a, ad="Fön")
    yanit = istemci.patch(f"/hizmetler/{h['hizmet_id']}", json={"ad": "Boya"}, headers=basliklar(a))
    assert yanit.status_code == 409


def test_calisan_okur_ama_yazamaz(istemci, calisan, iki_kiraci):
    a, _ = iki_kiraci
    h = _olustur(istemci, a, ad="Manikür")

    assert istemci.post("/hizmetler", json={"ad": "Pedikür"}, headers=basliklar(calisan)).status_code == 403
    yanit = istemci.patch(f"/hizmetler/{h['hizmet_id']}", json={"ad": "X"}, headers=basliklar(calisan))
    assert yanit.status_code == 403
    assert yanit.json() == {"detail": "Bu işlem için yetkiniz yok"}

    liste = istemci.get("/hizmetler", headers=basliklar(calisan))
    assert liste.status_code == 200
    assert [x["hizmet_id"] for x in liste.json()] == [h["hizmet_id"]]
    assert istemci.get(f"/hizmetler/{h['hizmet_id']}", headers=basliklar(calisan)).status_code == 200


def test_pasiflestirme_ve_durum_filtresi(istemci, iki_kiraci):
    a, _ = iki_kiraci
    kalan = _olustur(istemci, a, ad="Kesim", kategori="A")
    pasif = _olustur(istemci, a, ad="Eski Paket", kategori="B")

    yanit = istemci.patch(f"/hizmetler/{pasif['hizmet_id']}", json={"aktif_mi": False}, headers=basliklar(a))
    assert yanit.status_code == 200
    assert yanit.json()["aktif_mi"] is False
    assert yanit.json()["ad"] == "Eski Paket"                  # yalnızca gönderilen alan değişti

    varsayilan = [x["hizmet_id"] for x in istemci.get("/hizmetler", headers=basliklar(a)).json()]
    assert varsayilan == [kalan["hizmet_id"]]

    pasifler = istemci.get("/hizmetler", params={"durum": "pasif"}, headers=basliklar(a)).json()
    assert [x["hizmet_id"] for x in pasifler] == [pasif["hizmet_id"]]

    tumu = istemci.get("/hizmetler", params={"durum": "hepsi"}, headers=basliklar(a)).json()
    assert [x["hizmet_id"] for x in tumu] == [kalan["hizmet_id"], pasif["hizmet_id"]]   # kategori, ad

    assert istemci.get("/hizmetler", params={"durum": "bilinmeyen"}, headers=basliklar(a)).status_code == 422


def test_patch_bos_ve_null_422(istemci, iki_kiraci):
    a, _ = iki_kiraci
    h = _olustur(istemci, a, ad="Bakım")
    yol = f"/hizmetler/{h['hizmet_id']}"
    assert istemci.patch(yol, json={}, headers=basliklar(a)).status_code == 422
    assert istemci.patch(yol, json={"ad": None}, headers=basliklar(a)).status_code == 422
    assert istemci.patch(yol, json={"aktif_mi": None}, headers=basliklar(a)).status_code == 422


def test_baska_kiracinin_hizmeti_404(istemci, iki_kiraci):
    a, b = iki_kiraci
    h = _olustur(istemci, b, ad="B Hizmeti")
    yol = f"/hizmetler/{h['hizmet_id']}"
    assert istemci.get(yol, headers=basliklar(a)).status_code == 404
    assert istemci.patch(yol, json={"ad": "Ele geçirildi"}, headers=basliklar(a)).status_code == 404
    assert istemci.get(yol, headers=basliklar(b)).json()["ad"] == "B Hizmeti"
    assert istemci.get("/hizmetler", headers=basliklar(a)).json() == []
