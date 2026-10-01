"""Panel (Adım 7): isletme_giderleri, v_sessiz_uyeler.

Revision ID: 0003_panel
Revises: 0002_uyelik_paketleri
Create Date: 2026-10-01
"""

from pathlib import Path

from alembic import op

revision = "0003_panel"
down_revision = "0002_uyelik_paketleri"
branch_labels = None
depends_on = None

SEMA_DOSYASI = Path(__file__).resolve().parent.parent / "sql" / "0003_panel.sql"


def upgrade() -> None:
    sql = SEMA_DOSYASI.read_text(encoding="utf-8")
    # no_parameters: SQL içindeki '%' karakterleri psycopg2 tarafından yorumlanmaz
    op.get_bind().execution_options(no_parameters=True).exec_driver_sql(sql)


def downgrade() -> None:
    # Tabloyla birlikte trigger'ları, politikası ve indeksleri de silinir.
    op.execute("DROP VIEW v_sessiz_uyeler")
    op.execute("DROP TABLE isletme_giderleri")
