"""Güvenlik bekçisi: şema/rol kurallarının sessizce bozulmasını yakalayan testler.

1) Statik: create_all()/drop_all() uygulama kodunda ÇAĞRILMAZ (yalnızca models.py docstring'i ve tests/).
2) .env: uygulama veritabanına panosu_app rolüyle bağlanır (asla süperkullanıcı ile değil).
3) Veritabanı: panosu_app tablo oluşturamaz, RLS'yi atlayamaz, ayrıcalıklı bir role üye değildir.
"""

import ast
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.engine import make_url

PROJE = Path(__file__).resolve().parent.parent
HARIC_KLASORLER = {".venv", "venv", ".idea", "__pycache__", ".pytest_cache", "tests"}
YASAKLI_CAGRILAR = {"create_all", "drop_all"}
UYGULAMA_ROLU = "panosu_app"


def _uygulama_dosyalari():
    for yol in PROJE.rglob("*.py"):
        if not HARIC_KLASORLER.intersection(yol.relative_to(PROJE).parts):
            yield yol


# ---------------------------------------------------------------- 1) Statik tarama

def test_create_all_drop_all_uygulama_kodunda_cagrilmaz():
    ihlaller = []
    for yol in _uygulama_dosyalari():
        agac = ast.parse(yol.read_text(encoding="utf-8"), filename=str(yol))
        for dugum in ast.walk(agac):
            ad = None
            if isinstance(dugum, ast.Attribute):
                ad = dugum.attr
            elif isinstance(dugum, ast.Name):
                ad = dugum.id
            if ad in YASAKLI_CAGRILAR:
                ihlaller.append(f"{yol.relative_to(PROJE)}:{dugum.lineno} -> {ad}")
    assert not ihlaller, "Şema yalnızca SQL'den yönetilir; kodda yasaklı çağrı var:\n" + "\n".join(ihlaller)


def test_yasakli_kelimeler_yalnizca_models_docstringinde_gecer():
    """Metin düzeyinde de kontrol: yorum/dize içinde bile yalnızca models.py docstring'ine izin var."""
    izinli_satirlar = set()
    models = PROJE / "models.py"
    doc_dugumu = ast.parse(models.read_text(encoding="utf-8")).body[0]
    if isinstance(doc_dugumu, ast.Expr) and isinstance(doc_dugumu.value, ast.Constant):
        izinli_satirlar = {(models, n) for n in range(doc_dugumu.lineno, doc_dugumu.end_lineno + 1)}

    ihlaller = []
    for yol in _uygulama_dosyalari():
        for no, satir in enumerate(yol.read_text(encoding="utf-8").splitlines(), start=1):
            if any(k in satir for k in YASAKLI_CAGRILAR) and (yol, no) not in izinli_satirlar:
                ihlaller.append(f"{yol.relative_to(PROJE)}:{no}: {satir.strip()}")
    assert not ihlaller, "\n".join(ihlaller)


# ---------------------------------------------------------------- 2) .env kontrolü

def test_env_uygulama_rolunu_kullanir():
    env = PROJE / ".env"
    if not env.exists():
        pytest.skip(".env yok (CI ortamı olabilir)")
    url = dotenv_values(env).get("PANOSU_VERITABANI_URL")
    assert url, ".env içinde PANOSU_VERITABANI_URL tanımlı değil"
    assert make_url(url).username == UYGULAMA_ROLU


# ---------------------------------------------------------------- 3) Veritabanı yetkileri

@pytest.fixture(scope="module")
def app_baglantisi():
    """Uygulamanın gerçek engine'i (conftest onu PANOSU_TEST_APP_URL'ye yönlendirir)."""
    from database import engine

    with engine.connect() as con:
        yield con


def test_baglanti_uygulama_roluyle_yapilir(app_baglantisi):
    assert app_baglantisi.scalar(text("SELECT current_user")) == UYGULAMA_ROLU


def test_rol_superkullanici_degil_ve_rls_atlayamaz(app_baglantisi):
    rol = app_baglantisi.execute(text(
        "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user"
    )).one()
    assert rol.rolsuper is False, "panosu_app süperkullanıcı: RLS tamamen devre dışı kalır!"
    assert rol.rolbypassrls is False, "panosu_app BYPASSRLS yetkisine sahip!"
    assert rol.rolcreatedb is False
    assert rol.rolcreaterole is False


def test_rol_ayricalikli_bir_role_uye_degil(app_baglantisi):
    ayricalikli = app_baglantisi.execute(text(
        "SELECT r.rolname FROM pg_roles r "
        "WHERE pg_has_role(current_user, r.oid, 'MEMBER') AND r.rolname <> current_user "
        "AND (r.rolsuper OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb)"
    )).scalars().all()
    assert ayricalikli == []


def test_rol_tablo_olusturamaz(app_baglantisi):
    assert app_baglantisi.scalar(text("SELECT has_database_privilege(current_database(), 'CREATE')")) is False
    semalar = app_baglantisi.execute(text(
        "SELECT nspname FROM pg_namespace "
        "WHERE nspname NOT LIKE 'pg\\_%' AND nspname <> 'information_schema' "
        "AND has_schema_privilege(nspname, 'CREATE')"
    )).scalars().all()
    assert semalar == [], f"panosu_app şu şemalarda nesne oluşturabilir: {semalar}"


def test_rol_hicbir_tablonun_sahibi_degil(app_baglantisi):
    # Tablo sahibi RLS'ye (FORCE yoksa) tabi değildir ve DDL yapabilir
    sahip_olunan = app_baglantisi.execute(text(
        "SELECT schemaname || '.' || tablename FROM pg_tables WHERE tableowner = current_user"
    )).scalars().all()
    assert sahip_olunan == []


def test_kiraci_tablolarinda_rls_acik(app_baglantisi):
    rls_kapali = app_baglantisi.execute(text(
        "SELECT c.relname FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'isletme_id' AND NOT a.attisdropped "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relrowsecurity"
    )).scalars().all()
    assert rls_kapali == [], f"isletme_id içeren ama RLS'si kapalı tablolar: {rls_kapali}"
