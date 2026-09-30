"""Veritabanı düzeyinde kiracı izolasyonu (RLS) testleri. `main` import edilmez."""

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from models import Musteri


def test_kiraci_yalniz_kendi_musterisini_gorur(oturum, iki_kiraci):
    a, b = iki_kiraci
    for kiraci, diger in ((a, b), (b, a)):
        idler = set(oturum(kiraci).scalars(select(Musteri.musteri_id)).all())
        assert idler == {kiraci.musteri_id}
        assert diger.musteri_id not in idler


def test_baglamsiz_oturum_hicbir_sey_gormez(oturum, iki_kiraci):
    # app.isletme_id ayarlı değilse güvenli varsayılan: sıfır satır
    assert oturum().scalar(text("SELECT count(*) FROM musteriler")) == 0


def test_baska_kiracinin_musterisi_id_ile_bile_okunamaz(oturum, iki_kiraci):
    a, b = iki_kiraci
    assert oturum(a).get(Musteri, b.musteri_id) is None


def test_baska_kiracinin_adina_yazilamaz(oturum, iki_kiraci):
    a, b = iki_kiraci
    db = oturum(a)
    db.add(Musteri(isletme_id=b.isletme_id, ad_soyad="Sızıntı"))
    with pytest.raises(DBAPIError):      # "new row violates row-level security policy"
        db.flush()


def test_baska_kiracinin_musterisi_guncellenemez(oturum, iki_kiraci):
    a, b = iki_kiraci
    db = oturum(a)
    sonuc = db.execute(
        update(Musteri).where(Musteri.musteri_id == b.musteri_id).values(ad_soyad="Ele geçirildi")
    )
    assert sonuc.rowcount == 0
    db.rollback()
    assert oturum(b).get(Musteri, b.musteri_id).ad_soyad == b.musteri_adi


def test_varsayilan_isletme_id_oturumdan_gelir(oturum, iki_kiraci):
    a, _ = iki_kiraci
    db = oturum(a)
    yeni = Musteri(ad_soyad="Varsayılan Testi")     # isletme_id verilmedi: DB aktif_isletme() ile doldurur
    db.add(yeni)
    db.flush()
    db.refresh(yeni)
    assert yeni.isletme_id == a.isletme_id          # commit edilmez, oturum kapanınca geri alınır


def test_kiraci_baglami_havuzda_sizmaz(oturum, iki_kiraci):
    a, _ = iki_kiraci
    sorgu = text("SELECT current_setting('app.isletme_id', true)")
    for _ in range(6):                              # bağlantı havuzunda farklı bağlantıları yakalamak için tekrar
        db = oturum(a)
        assert db.scalar(sorgu) == str(a.isletme_id)
        db.close()

        bos = oturum()
        assert bos.scalar(sorgu) in ("", None)      # önceki işletmenin kimliği KALMAMALI
        bos.close()