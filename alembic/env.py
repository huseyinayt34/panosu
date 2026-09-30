"""Alembic ortamı.

Autogenerate kullanılmaz; migration'lar elle yazılır. Şemanın tek kaynağı SQL'dir; models.py RLS,
politika, trigger ve view'ları bilmez, autogenerate onları silmeye çalışırdı.

Bağlantı: config.ayarlar.migrasyon_url (PANOSU_MIGRASYON_URL). Bu rol DDL yetkili olmalıdır;
uygulama URL'si ve uygulama rolü (panosu_app) ASLA kullanılmaz.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url

from config import ayarlar

UYGULAMA_ROLU = "panosu_app"

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _migrasyon_url() -> str:
    url = ayarlar.migrasyon_url
    if not url:
        raise SystemExit(
            "PANOSU_MIGRASYON_URL tanımlı değil. DDL yetkili rolün bağlantı adresini ortam değişkeni "
            "veya .env ile verin (örnek için .env.example dosyasına bakın)."
        )
    if make_url(url).username == UYGULAMA_ROLU:
        raise SystemExit(f"Migration'lar {UYGULAMA_ROLU} ile çalıştırılamaz; bu rolün DDL yetkisi bilerek yok.")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_migrasyon_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_migrasyon_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # transaction_per_migration: her revizyon kendi işleminde; hata olursa yalnızca o geri alınır
        context.configure(connection=connection, target_metadata=target_metadata, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
