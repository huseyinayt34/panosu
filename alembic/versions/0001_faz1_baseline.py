"""Faz 1 baseline: mevcut şemanın tamamı (tablolar, RLS politikaları, trigger'lar, view'lar, GRANT'lar).

Şemaya zaten sahip veritabanlarında upgrade ÇALIŞTIRILMAZ:
    alembic stamp 0001_faz1_baseline
Boş bir veritabanında `alembic upgrade head` şemayı sıfırdan kurar
(önkoşul: panosu_app rolü mevcut olmalı, GRANT'lar ona verilir).

Revision ID: 0001_faz1_baseline
Revises:
Create Date: 2026-09-30
"""

from pathlib import Path

from alembic import op

revision = "0001_faz1_baseline"
down_revision = None
branch_labels = None
depends_on = None

SEMA_DOSYASI = Path(__file__).resolve().parent.parent / "sql" / "0001_faz1_sema.sql"


def upgrade() -> None:
    sql = SEMA_DOSYASI.read_text(encoding="utf-8")
    # no_parameters: PL/pgSQL gövdelerindeki '%' karakterleri psycopg2 tarafından yorumlanmaz
    op.get_bind().execution_options(no_parameters=True).exec_driver_sql(sql)


def downgrade() -> None:
    raise NotImplementedError("Baseline geri alınamaz")
