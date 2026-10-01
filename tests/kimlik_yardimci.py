"""Kimlik testleri için ortak yardımcılar (conftest dışında; conftest yalnızca tasarımın Bölüm 5'i kadar değişir).

`kayit_temizligi` fixture'ı, /kayit ve /kayit/davet ile oluşturulan kullanıcıları ve onların açtığı işletmeleri
test sonunda yönetici bağlantısıyla siler.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

PAROLA = "dogru-at-pil-zimba"           # 19 karakter; yalnızca test verisi


@pytest.fixture()
def istemci():
    from main import app
    return TestClient(app)


@pytest.fixture()
def acik_kayit(monkeypatch):
    from config import ayarlar
    monkeypatch.setattr(ayarlar, "acik_kayit", True)


@pytest.fixture()
def kayit_temizligi(admin_engine):
    """Test, oluşturduğu e-postaları listeye ekler; sonda kullanıcılar ve sahibi oldukları işletmeler silinir."""
    epostalar: list[str] = []
    yield epostalar
    with admin_engine.begin() as con:
        con.execute(text("SET LOCAL lock_timeout = '10s'"))
        kullanicilar = con.execute(text("SELECT kullanici_id FROM kullanicilar WHERE eposta = ANY(:e)"),
                                   {"e": epostalar}).scalars().all()
        if not kullanicilar:
            return
        k = {"k": list(kullanicilar)}
        isletmeler = con.execute(text("SELECT isletme_id FROM uyelikler WHERE kullanici_id = ANY(:k) AND rol = 'sahip' "
                                      "AND isletme_id NOT IN (SELECT isletme_id FROM uyelikler WHERE rol = 'sahip' "
                                      "AND kullanici_id <> ALL(:k))"), k).scalars().all()
        i = {"i": list(isletmeler)}
        con.execute(text("DELETE FROM davetler WHERE isletme_id = ANY(:i) OR kullanan_kullanici_id = ANY(:k) "
                         "OR olusturan_kullanici_id = ANY(:k)"), {**i, **k})
        for tablo in ("abonelikler", "uyelikler", "denetim_kayitlari"):
            con.execute(text(f"DELETE FROM {tablo} WHERE isletme_id = ANY(:i)"), i)
        con.execute(text("DELETE FROM uyelikler WHERE kullanici_id = ANY(:k)"), k)
        con.execute(text("UPDATE denetim_kayitlari SET kullanici_id = NULL WHERE kullanici_id = ANY(:k)"), k)
        con.execute(text("DELETE FROM isletmeler WHERE isletme_id = ANY(:i)"), i)
        con.execute(text("DELETE FROM kullanicilar WHERE kullanici_id = ANY(:k)"), k)   # kimlik bilgileri, oturumlar: CASCADE


def eposta() -> str:
    return f"k-{uuid.uuid4().hex[:12]}@test.local"


def kayit_ol(istemci, epostalar: list[str], **alanlar) -> dict:
    govde = {"eposta": eposta(), "ad_soyad": "Stüdyo Sahibi", "parola": PAROLA, "isletme_adi": "Test Stüdyo",
             "sektor": "spor_salonu", **alanlar}
    epostalar.append(govde["eposta"])
    y = istemci.post("/kayit", json=govde)
    assert y.status_code == 201, y.text
    return {**y.json(), "eposta": govde["eposta"]}


def giris(istemci, eposta_: str, parola: str = PAROLA):
    return istemci.post("/oturum/giris", json={"eposta": eposta_, "parola": parola})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
