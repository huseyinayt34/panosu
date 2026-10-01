"""Kimlik şemasının veritabanı güvenceleri (Adım 8): yetkiler, SECURITY DEFINER ayarları, düz parola yokluğu."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from kimlik_yardimci import PAROLA, acik_kayit, istemci, kayit_ol, kayit_temizligi  # noqa: F401

FONKSIYONLAR = ("kullanici_kaydet", "giris_bilgisi", "giris_sonucu_yaz", "parola_ozeti_guncelle", "oturum_ac",
                "oturum_yenile", "oturum_kapat", "oturum_isletme_degistir", "davet_kabul")


@pytest.mark.parametrize("tablo", ["kullanici_kimlik_bilgileri", "oturumlar"])
def test_uygulama_rolu_gizli_tablolari_okuyamaz(oturum, tablo):
    db = oturum()
    with pytest.raises(ProgrammingError) as hata:
        db.execute(text(f"SELECT * FROM {tablo} LIMIT 1"))
    assert hata.value.orig.pgcode == "42501"                                               # insufficient_privilege


@pytest.mark.parametrize("tablo", ["kullanici_kimlik_bilgileri", "oturumlar"])
def test_uygulama_rolunun_gizli_tablolarda_hic_yetkisi_yok(admin_engine, tablo):
    with admin_engine.connect() as con:
        yetkiler = con.execute(text(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'panosu_app' AND table_name = :t"), {"t": tablo}).scalars().all()
    assert yetkiler == []


def test_definer_fonksiyonlarinda_search_path_ve_public_yetkisi_yok(admin_engine):
    with admin_engine.connect() as con:
        satirlar = con.execute(text(
            "SELECT p.proname, p.prosecdef, p.proconfig, has_function_privilege('public', p.oid, 'EXECUTE') AS pub, "
            "has_function_privilege('panosu_app', p.oid, 'EXECUTE') AS app "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.proname = ANY(:f)"), {"f": list(FONKSIYONLAR)}).all()
    assert {s.proname for s in satirlar} == set(FONKSIYONLAR)
    for s in satirlar:
        assert s.prosecdef, s.proname
        assert s.proconfig and any(c.startswith("search_path=") for c in s.proconfig), s.proname
        assert s.pub is False and s.app is True, s.proname


def test_veritabaninda_duz_parola_yok(istemci, acik_kayit, kayit_temizligi, admin_engine):
    k = kayit_ol(istemci, kayit_temizligi)
    with admin_engine.connect() as con:
        ozet = con.scalar(text("SELECT b.parola_ozeti FROM kullanici_kimlik_bilgileri b JOIN kullanicilar k "
                               "USING (kullanici_id) WHERE k.eposta = :e"), {"e": k["eposta"]})
        kullanici = con.scalar(text("SELECT to_jsonb(k)::text FROM kullanicilar k WHERE eposta = :e"), {"e": k["eposta"]})
        denetim = con.execute(text("SELECT coalesce(eski_deger::text, '') || coalesce(yeni_deger::text, '') "
                                   "FROM denetim_kayitlari WHERE isletme_id = :i"), {"i": k["isletme_id"]}).scalars().all()
    assert ozet.startswith("$argon2id$") and PAROLA not in ozet
    assert PAROLA not in kullanici and all(PAROLA not in d for d in denetim)


def test_duz_parola_yazilamaz(oturum):
    db = oturum()
    with pytest.raises(Exception) as hata:
        db.execute(text("SELECT kullanici_kaydet('duz@test.local', 'X', 'duz-parola-1234')"))
    assert getattr(hata.value.orig, "pgcode", None) == "23514"                              # CHECK ihlali
    db.rollback()
