"""Üyelik paketleri ve yenileme riski (Adım 5b): musteri_paketleri, yenileme_riskleri, v_yenileme_paneli.

Revision ID: 0002_uyelik_paketleri
Revises: 0001_faz1_baseline
Create Date: 2026-10-01
"""

from pathlib import Path

from alembic import op

revision = "0002_uyelik_paketleri"
down_revision = "0001_faz1_baseline"
branch_labels = None
depends_on = None

SEMA_DOSYASI = Path(__file__).resolve().parent.parent / "sql" / "0002_uyelik_paketleri.sql"


def upgrade() -> None:
    sql = SEMA_DOSYASI.read_text(encoding="utf-8")
    # no_parameters: SQL içindeki '%' karakterleri psycopg2 tarafından yorumlanmaz
    op.get_bind().execution_options(no_parameters=True).exec_driver_sql(sql)


def downgrade() -> None:
    # Tablolarla birlikte trigger'lar, politikalar ve indeksler de silinir.
    op.execute("DROP VIEW v_yenileme_paneli")
    op.execute("DROP TABLE yenileme_riskleri")
    op.execute("DROP TABLE musteri_paketleri")
