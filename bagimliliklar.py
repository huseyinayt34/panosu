"""FastAPI bağımlılıkları: veritabanı oturumu ve kiracı bağlamı."""

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import ayarlar
from database import SessionLocal
from models import Uyelik


@dataclass(frozen=True)
class Kimlik:
    kullanici_id: UUID
    isletme_id: UUID


def get_db() -> Iterator[Session]:
    """Kiracı bağlamı OLMAYAN oturum (sağlık kontrolü, giriş/kayıt gibi uçlar için)."""
    with SessionLocal() as db:
        yield db


def kimlik_al(x_kullanici_id: UUID = Header(...), x_isletme_id: UUID = Header(...)) -> Kimlik:
    """GEÇİCİ (yalnız geliştirme): kimliği istek başlıklarından alır.

    Başlıklar istemci tarafından sahteleştirilebilir; bu yüzden üretimde KAPALIDIR.
    Bir sonraki adımda JWT doğrulamasıyla değiştirilecek.
    """
    if ayarlar.ortam != "gelistirme":
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Kimlik doğrulama henüz yapılandırılmadı")
    return Kimlik(kullanici_id=x_kullanici_id, isletme_id=x_isletme_id)


def kiraci_db(kimlik: Kimlik = Depends(kimlik_al)) -> Iterator[Session]:
    """Kiracı bağlamlı oturum: her işlemde app.isletme_id ayarlanır, RLS devreye girer."""
    with SessionLocal() as db:
        db.info["isletme_id"] = kimlik.isletme_id
        db.info["kullanici_id"] = kimlik.kullanici_id

        rol = db.scalar(
            select(Uyelik.rol).where(
                Uyelik.kullanici_id == kimlik.kullanici_id,
                Uyelik.isletme_id == kimlik.isletme_id,
            )
        )
        if rol is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu işletmeye erişim yetkiniz yok")
        db.info["rol"] = rol

        yield db


def rol_gerektir(*roller: str):
    """Bağımlılık fabrikası: kiraci_db oturumunu alır, kullanıcının rolü listede değilse 403 döner."""

    def _rol_denetle(db: Session = Depends(kiraci_db)) -> Session:
        if db.info.get("rol") not in roller:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu işlem için yetkiniz yok")
        return db

    return _rol_denetle