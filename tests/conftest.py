"""Test altyapısı.

Testler İZOLE bir veritabanında çalışır (adı '_test' ile bitmelidir), çünkü veri ekler ve siler.

Bağlantı adresleri:
  PANOSU_TEST_APP_URL    -> panosu_app rolüyle bağlantı (RLS'ye tabi; uygulamanın gerçek rolü)
  PANOSU_TEST_ADMIN_URL  -> SÜPERKULLANICI (postgres) bağlantısı; test verisini RLS'yi atlayarak kurar/temizler
Ortamda tanımlı değillerse .env'deki PANOSU_VERITABANI_URL / PANOSU_MIGRASYON_URL'den, yalnızca veritabanı
adı TEST_VERITABANI yapılarak türetilir. Ortam değişkeni her zaman önceliklidir.
"""

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TEST_VERITABANI = "panosu_test"
_ENV_DOSYASI = Path(__file__).resolve().parent.parent / ".env"


def _test_adresi(ortam_degiskeni: str, env_anahtari: str) -> str | None:
    if os.environ.get(ortam_degiskeni):
        return os.environ[ortam_degiskeni]
    kaynak = dotenv_values(_ENV_DOSYASI).get(env_anahtari)
    if not kaynak:
        return None
    return make_url(kaynak).set(database=TEST_VERITABANI).render_as_string(hide_password=False)


def pytest_configure(config):
    """Uygulama modülleri import edilmeden ÖNCE çalışır: ayarları test veritabanına yönlendirir."""
    app_url = _test_adresi("PANOSU_TEST_APP_URL", "PANOSU_VERITABANI_URL")
    admin_url = _test_adresi("PANOSU_TEST_ADMIN_URL", "PANOSU_MIGRASYON_URL")

    if not app_url or not admin_url:
        pytest.exit(
            "Test bağlantı adresleri bulunamadı: PANOSU_TEST_APP_URL / PANOSU_TEST_ADMIN_URL ortam değişkenlerini "
            "ya da .env'de PANOSU_VERITABANI_URL / PANOSU_MIGRASYON_URL'yi tanımlayın.",
            returncode=2,
        )
    for url in (app_url, admin_url):
        if not (make_url(url).database or "").endswith("_test"):
            pytest.exit("Güvenlik: testler yalnızca adı '_test' ile biten bir veritabanında çalışır.", returncode=2)

    os.environ["PANOSU_TEST_APP_URL"] = app_url          # fixture'lar buradan okur
    os.environ["PANOSU_TEST_ADMIN_URL"] = admin_url
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
    for tablo in ("yenileme_riskleri", "musteri_paketleri", "ziyaret_kalemleri", "ziyaretler", "musteriler",
                  "hizmetler", "uyelikler"):
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
def calisan(admin_engine, iki_kiraci):
    """A işletmesinde 'calisan' rolünde ikinci bir kullanıcı. Test sonunda silinir."""
    a, _ = iki_kiraci
    kullanici_id = uuid.uuid4()
    k, i = str(kullanici_id), str(a.isletme_id)
    with admin_engine.begin() as con:
        con.execute(text("SET LOCAL lock_timeout = '10s'"))
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
            con.execute(text("SET LOCAL lock_timeout = '10s'"))
            con.execute(text("DELETE FROM uyelikler WHERE kullanici_id = :u"), {"u": k})
            con.execute(text("DELETE FROM denetim_kayitlari WHERE kullanici_id = :u"), {"u": k})
            con.execute(text("DELETE FROM kullanicilar WHERE kullanici_id = :u"), {"u": k})


def basliklar(kiraci: Kiraci) -> dict[str, str]:
    """GEÇİCİ başlık tabanlı kimlik (yalnız geliştirme ortamı)."""
    return {"X-Kullanici-Id": str(kiraci.kullanici_id), "X-Isletme-Id": str(kiraci.isletme_id)}


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