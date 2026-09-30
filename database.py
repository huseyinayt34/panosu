"""Veritabanı bağlantısı ve kiracı (tenant) bağlamı.

Kritik: Uygulama, RLS'ye tabi bir rolle (panosu_app) bağlanmalıdır. Süperkullanıcı (postgres)
RLS'yi tamamen atlar; onunla bağlanırsan çok kiracılı izolasyon çalışmaz.
"""

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import ayarlar

engine = create_engine(ayarlar.veritabani_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


@event.listens_for(SessionLocal, "after_begin")
def _oturum_baglamini_ayarla(session, transaction, connection):
    """Her işlem (transaction) başında kiracı/kullanıcı bağlamını PostgreSQL'e bildirir.

    set_config(..., true) = yalnızca bu işlem boyunca geçerli. Bağlantı havuzuna dönen bir bağlantıda
    önceki isteğin işletme kimliği KALMAZ; kiracılar arası sızıntı bu şekilde önlenir.
    """
    isletme_id = session.info.get("isletme_id")
    kullanici_id = session.info.get("kullanici_id")
    connection.execute(
        text("SELECT set_config('app.isletme_id', :isletme, true), "
             "set_config('app.kullanici_id', :kullanici, true)"),
        {
            "isletme": str(isletme_id) if isletme_id else "",
            "kullanici": str(kullanici_id) if kullanici_id else "",
        },
    )