"""Kimlik doğrulama (Adım 8): kullanici_kimlik_bilgileri, oturumlar, davetler ve SECURITY DEFINER fonksiyonları.

Revision ID: 0004_kimlik
Revises: 0003_panel
Create Date: 2026-10-01
"""

from pathlib import Path

from alembic import op

revision = "0004_kimlik"
down_revision = "0003_panel"
branch_labels = None
depends_on = None

SEMA_DOSYASI = Path(__file__).resolve().parent.parent / "sql" / "0004_kimlik.sql"

_FONKSIYONLAR = (
    "kullanici_kaydet(citext, text, text)", "giris_bilgisi(citext)", "giris_sonucu_yaz(uuid, boolean)",
    "parola_ozeti_guncelle(uuid, text)", "oturum_ac(uuid, bytea, uuid, interval)",
    "oturum_yenile(bytea, bytea, interval)", "oturum_kapat(bytea)", "oturum_isletme_degistir(bytea, uuid)",
    "davet_kabul(bytea, uuid)",
)


def upgrade() -> None:
    sql = SEMA_DOSYASI.read_text(encoding="utf-8")
    # no_parameters: SQL içindeki '%' ve '$' karakterleri psycopg2 tarafından yorumlanmaz
    op.get_bind().execution_options(no_parameters=True).exec_driver_sql(sql)


def downgrade() -> None:
    for imza in _FONKSIYONLAR:
        op.execute(f"DROP FUNCTION {imza}")
    # Tablolarla birlikte trigger'lar, politikalar ve indeksler de silinir.
    op.execute("DROP TABLE davetler")
    op.execute("DROP TABLE oturumlar")
    op.execute("DROP TABLE kullanici_kimlik_bilgileri")
