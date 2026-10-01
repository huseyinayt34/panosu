"""FastAPI bağımlılıkları: veritabanı oturumu, kimlik doğrulama ve kiracı bağlamı.

Kimlik yalnızca imzalı erişim tokenından okunur (Authorization: Bearer). isletme_id istemciden alınmaz: tokendaki
`isl` alanı yalnızca sunucunun üyeliği doğruladıktan sonra imzaladığı değerdir (K9). Rol ve üyelik her istekte
veritabanından okunur; token'a rol yazılmaz.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Isletme, Uyelik
from servisler.kimlik import TokenGecersiz, erisim_tokeni_coz

_bearer = HTTPBearer(auto_error=False, description="POST /oturum/giris yanıtındaki erisim_tokeni")


@dataclass(frozen=True)
class Kimlik:
    kullanici_id: UUID
    isletme_id: UUID | None


def get_db() -> Iterator[Session]:
    """Kiracı bağlamı OLMAYAN oturum (sağlık kontrolü, kayıt, giriş gibi uçlar için)."""
    with SessionLocal() as db:
        yield db


def _yetkisiz(mesaj: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, mesaj, headers={"WWW-Authenticate": "Bearer"})


def kimlik_dogrula(kimlik_bilgisi: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Kimlik:
    """Bearer erişim tokenını doğrular. Eksik / geçersiz / süresi geçmiş → 401."""
    if kimlik_bilgisi is None or kimlik_bilgisi.scheme.lower() != "bearer":
        raise _yetkisiz("Kimlik doğrulaması gerekli")
    try:
        kullanici_id, isletme_id = erisim_tokeni_coz(kimlik_bilgisi.credentials)
    except TokenGecersiz:
        raise _yetkisiz("Geçersiz veya süresi dolmuş token")
    return Kimlik(kullanici_id=kullanici_id, isletme_id=isletme_id)


def kullanici_db(kimlik: Kimlik = Depends(kimlik_dogrula)) -> Iterator[Session]:
    """Yalnızca app.kullanici_id ayarlı oturum (işletme seçmeden önceki uçlar için)."""
    with SessionLocal() as db:
        db.info["kullanici_id"] = kimlik.kullanici_id
        yield db


def kiraci_db(kimlik: Kimlik = Depends(kimlik_dogrula)) -> Iterator[Session]:
    """Kiracı bağlamlı oturum: her işlemde app.isletme_id ayarlanır, RLS devreye girer."""
    if kimlik.isletme_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "İşletme seçilmedi")
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
        durum = db.scalar(select(Isletme.durum).where(Isletme.isletme_id == func.aktif_isletme()))
        if durum != "aktif":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "İşletme aktif değil")
        db.info["rol"] = rol

        yield db


def rol_gerektir(*roller: str):
    """Bağımlılık fabrikası: kiraci_db oturumunu alır, kullanıcının rolü listede değilse 403 döner."""

    def _rol_denetle(db: Session = Depends(kiraci_db)) -> Session:
        if db.info.get("rol") not in roller:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu işlem için yetkiniz yok")
        return db

    return _rol_denetle
