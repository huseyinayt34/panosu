"""Davet ve üye yönetimi iş mantığı. FastAPI'ye bağımlı değildir. Kiracı izolasyonu RLS ile.

uyelikler'in okuma politikası, aktif işletmenin üyelerine EK OLARAK kullanıcının başka işletmelerdeki kendi
üyeliklerini de gösterir; bu yüzden üye sorguları aktif işletmeyle (aktif_isletme()) sınırlandırılır.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from models import Kullanici, Uyelik
from servisler.kimlik import davet_kodu_uret, ozet


class DavetBulunamadi(Exception):
    pass


class UyeBulunamadi(Exception):
    pass


class UyeSilinemez(Exception):
    """Sahip kendini silemez; son sahip silinemez (409)."""


@dataclass
class YeniDavet:
    davet_id: uuid.UUID
    rol: str
    son_kullanma: datetime
    olusturma_zamani: datetime
    kod: str


_ACIK = "kullanilma_zamani IS NULL AND iptal_zamani IS NULL AND son_kullanma > now()"


def davet_olustur(db: Session, rol: str) -> YeniDavet:
    """isletme_id ve olusturan_kullanici_id veritabanı varsayılanlarından (aktif_isletme(), aktif_kullanici())."""
    kod = davet_kodu_uret()
    satir = db.execute(
        text("INSERT INTO davetler (rol, kod_ozeti) VALUES (:r, :o) "
             "RETURNING davet_id, rol, son_kullanma, olusturma_zamani"),
        {"r": rol, "o": ozet(kod)},
    ).one()
    db.commit()
    return YeniDavet(satir.davet_id, satir.rol, satir.son_kullanma, satir.olusturma_zamani, kod)


def acik_davetler(db: Session) -> list[dict]:
    return [dict(s) for s in db.execute(text(
        f"SELECT davet_id, rol, son_kullanma, olusturma_zamani FROM davetler WHERE {_ACIK} "
        "ORDER BY olusturma_zamani DESC")).mappings()]


def davet_iptal(db: Session, davet_id: uuid.UUID) -> None:
    sonuc = db.execute(text(f"UPDATE davetler SET iptal_zamani = now() WHERE davet_id = :d AND {_ACIK}"),
                       {"d": davet_id})
    if sonuc.rowcount == 0:
        db.rollback()
        raise DavetBulunamadi(davet_id)
    db.commit()


def uyeler(db: Session) -> list[dict]:
    satirlar = db.execute(
        select(Uyelik.kullanici_id, Kullanici.ad_soyad, Kullanici.eposta, Uyelik.rol, Uyelik.olusturma_zamani)
        .join(Kullanici, Kullanici.kullanici_id == Uyelik.kullanici_id)
        .where(Uyelik.isletme_id == func.aktif_isletme())
        .order_by(Uyelik.olusturma_zamani)
    ).mappings().all()
    return [dict(s) for s in satirlar]


def uye_sil(db: Session, kullanici_id: uuid.UUID, isteyen_id: uuid.UUID) -> None:
    aktif = Uyelik.isletme_id == func.aktif_isletme()
    rol = db.scalar(select(Uyelik.rol).where(aktif, Uyelik.kullanici_id == kullanici_id))
    if rol is None:
        raise UyeBulunamadi(kullanici_id)
    if kullanici_id == isteyen_id:
        raise UyeSilinemez("Kendi üyeliğinizi silemezsiniz")
    if rol == "sahip" and db.scalar(select(func.count()).select_from(Uyelik).where(aktif, Uyelik.rol == "sahip")) <= 1:
        raise UyeSilinemez("Son sahip silinemez")
    db.execute(Uyelik.__table__.delete().where(aktif, Uyelik.kullanici_id == kullanici_id))
    db.commit()
