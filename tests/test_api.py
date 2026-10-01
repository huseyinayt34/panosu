"""API düzeyinde testler. `main` import edilir (ImportError giderilmeden bu dosya çalışmaz)."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def istemci():
    from main import app
    return TestClient(app)


def _basliklar(kiraci, isletme_id=None):
    """Kiracının kullanıcısı için imzalı erişim tokenı; isl = isletme_id (verilmezse kiracının işletmesi)."""
    from servisler.kimlik import erisim_tokeni_uret
    return {"Authorization": f"Bearer {erisim_tokeni_uret(kiraci.kullanici_id, isletme_id or kiraci.isletme_id)}"}


def test_saglik_ucu_calisir(istemci):
    yanit = istemci.get("/saglik")
    assert yanit.status_code == 200
    assert yanit.json() == {"durum": "ok"}


def test_musteriler_yalniz_kendi_kiracisini_dondurur(istemci, iki_kiraci):
    a, _ = iki_kiraci
    yanit = istemci.get("/musteriler", headers=_basliklar(a))
    assert yanit.status_code == 200
    assert [m["musteri_id"] for m in yanit.json()["ogeler"]] == [str(a.musteri_id)]


def test_uye_olmayan_kullanici_baska_isletmeye_giremez(istemci, iki_kiraci):
    a, b = iki_kiraci
    yanit = istemci.get("/musteriler", headers=_basliklar(a, isletme_id=b.isletme_id))
    assert yanit.status_code == 403


def test_kimlik_basliklari_olmadan_401(istemci):
    assert istemci.get("/musteriler").status_code == 401