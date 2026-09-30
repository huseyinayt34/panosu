"""Test altyapısı.

Testler İZOLE bir veritabanında çalışır (adı '_test' ile bitmelidir), çünkü veri ekler ve siler.

Gerekli ortam değişkenleri:
  PANOSU_TEST_APP_URL    -> panosu_app rolüyle bağlantı (RLS'ye tabi; uygulamanın gerçek rolü)
  PANOSU_TEST_ADMIN_URL  -> SÜPERKULLANICI (postgres) bağlantısı; test verisini RLS'yi atlayarak kurar/temizler
"""

import os
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def pytest_configure(config):
    """Uygulama modülleri import edilmeden ÖNCE çalışır: ayarları test veritabanına yönlendirir."""
    app_url = os.environ.get("PANOSU_TEST_APP_URL")
    admin_url = os.environ.get("PANOSU_TEST_ADMIN_URL")

    if not app_url or not admin_url:
        pytest.exit(
            "PANOSU_TEST_APP_URL ve PANOSU_TEST_ADMIN_URL ortam değişkenleri tanımlı olmalı "
            "(bkz. tests/conftest.py başındaki açıklama).",
            returncode=2,
        )
    for url in (app_url, admin_url):
        if not (make_url(url).database or "").endswith("_test"):
            pytest.exit("Güvenlik: testler yalnızca adı '_test' ile biten bir veritabanında çalışır.", returncode=2)

    # Ortam değişkenleri .env dosyasından önceliklidir; uygulama test veritabanını kullanır.
    os.environ["PANOSU_VERITABANI_URL"] = app_url
    os.environ["PANOSU_ORTAM"] = "gelistirme"


@dataclass(frozen=True)
class Kiraci:
    isletme_id: uuid.UUID
    kullanici_id: uuid.UUID
    musteri_id: uuid.UUID
    musteri_adi: str


@pytest.fixture(scope="session")
def admin_engine():
    engine = create_engine(os.environ["PANOSU_TEST_ADMIN_URL"])
    yield engine
    engine.dispose()


def _kiraci_olustur(con, ad: str) -> Kiraci:
    k = Kiraci(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), f"Müşteri {ad}")
    i, u, m = str(k.isletme_id), str(k.kullanici_id), str(k.musteri_id)

    con.execute(
        text("INSERT INTO kullanicilar (kullanici_id, eposta, ad_soyad) VALUES (:u, :e, :a)"),
        {"u": u, "e": f"{u}@test.local", "a": f"Kullanıcı {ad}"},
    )
    con.execute(text("INSERT INTO isletmeler (isletme_id, ad) VALUES (:i, :a)"), {"i": i, "a": f"İşletme {ad}"})
    con.execute(
        text("INSERT INTO uyelikler (isletme_id, kullanici_id, rol) VALUES (:i, :u, 'sahip')"),
        {"i": i, "u": u},
    )
    con.execute(
        text("INSERT INTO musteriler (musteri_id, isletme_id, ad_soyad) VALUES (:m, :i, :a)"),
        {"m": m, "i": i, "a": k.musteri_adi},
    )
    return k


def _kiraci_temizle(con, k: Kiraci) -> None:
    i = {"i": str(k.isletme_id)}
    for tablo in ("ziyaret_kalemleri", "ziyaretler", "musteriler", "hizmetler", "uyelikler"):
        con.execute(text(f"DELETE FROM {tablo} WHERE isletme_id = :i"), i)
    con.execute(text("DELETE FROM isletmeler WHERE isletme_id = :i"), i)
    con.execute(text("DELETE FROM kullanicilar WHERE kullanici_id = :u"), {"u": str(k.kullanici_id)})
    # Silme trigger'ları denetim kaydı ürettiği için en son temizlenir
    con.execute(text("DELETE FROM denetim_kayitlari WHERE isletme_id = :i"), i)


@pytest.fixture()
def iki_kiraci(admin_engine):
    """İki bağımsız işletme: her birinin bir sahibi ve bir müşterisi var. Test sonunda silinir."""
    with admin_engine.begin() as con:
        con.execute(text("SET LOCAL lock_timeout = '10s'"))     # kilitlenmede asılı kalma, hatayla düş
        a = _kiraci_olustur(con, "A")
        b = _kiraci_olustur(con, "B")
    try:
        yield a, b
    finally:
        with admin_engine.begin() as con:
            con.execute(text("SET LOCAL lock_timeout = '10s'"))
            _kiraci_temizle(con, a)
            _kiraci_temizle(con, b)


@pytest.fixture()
def oturum(request):
    """Uygulamanın gerçek SessionLocal'ından oturum üretir; kiraci verilirse kiracı bağlamı ayarlanır."""
    # Test iki_kiraci'yi de istiyorsa önce o kurulur: pytest ters sırada temizlediği için oturumlar,
    # iki_kiraci'nin DELETE'lerinden ÖNCE kapanır (açık işlem FK kilidini tutup temizliği kilitlemez).
    if "iki_kiraci" in request.fixturenames:
        request.getfixturevalue("iki_kiraci")

    from database import SessionLocal

    acilanlar = []

    def _ac(kiraci: Kiraci | None = None):
        db = SessionLocal()
        if kiraci is not None:
            db.info["isletme_id"] = kiraci.isletme_id
            db.info["kullanici_id"] = kiraci.kullanici_id
        acilanlar.append(db)
        return db

    yield _ac

    for db in acilanlar:
        db.close()