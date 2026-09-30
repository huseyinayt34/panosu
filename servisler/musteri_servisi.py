"""Müşteri iş mantığı. FastAPI'ye bağımlı değildir; hataları kendi istisnalarıyla bildirir.

Kiracı izolasyonu RLS ile sağlanır: sorgulara isletme_id filtresi EKLENMEZ, yeni kayıtlarda
isletme_id veritabanındaki aktif_isletme() varsayılanıyla dolar.
"""

import re
import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from models import Musteri
from semalar.musteri import MusteriGuncelle, MusteriOlustur
from servisler.ortak import kaydet

TELEFON_TEKIL_INDEKSI = "musteri_telefon_tekil_idx"
_SEMA_ALANI = {"telefon": "telefon_e164"}   # şema alanı -> model sütunu


class MusteriBulunamadi(Exception):
    pass


class TelefonZatenKayitli(Exception):
    pass


_TEKILLIK = {TELEFON_TEKIL_INDEKSI: TelefonZatenKayitli}


def _sutunlar(alanlar: dict) -> dict:
    return {_SEMA_ALANI.get(ad, ad): deger for ad, deger in alanlar.items()}


def _like_kacis(metin: str) -> str:
    return metin.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def musteri_olustur(db: Session, veri: MusteriOlustur) -> Musteri:
    musteri = Musteri(**_sutunlar(veri.model_dump()), kaynak="manuel")
    db.add(musteri)
    kaydet(db, _TEKILLIK)
    db.refresh(musteri)     # sunucu varsayılanları: musteri_id, isletme_id, zamanlar
    return musteri


def musteri_getir(db: Session, musteri_id: uuid.UUID) -> Musteri:
    musteri = db.scalar(
        select(Musteri).where(Musteri.musteri_id == musteri_id, Musteri.silindi_at.is_(None))
    )
    if musteri is None:
        raise MusteriBulunamadi(musteri_id)
    return musteri


def musterileri_listele(
    db: Session, q: str | None, limit: int, offset: int
) -> tuple[Sequence[Musteri], int]:
    kosullar = [Musteri.silindi_at.is_(None)]
    q = (q or "").strip()
    if q:
        arama = Musteri.ad_soyad.ilike(f"%{_like_kacis(q)}%", escape="\\")
        rakamlar = re.sub(r"[^0-9]", "", q)
        if rakamlar:
            arama = or_(arama, Musteri.telefon_e164.contains(rakamlar))
        kosullar.append(arama)

    toplam = db.scalar(select(func.count()).select_from(Musteri).where(*kosullar))
    liste = db.scalars(
        select(Musteri)
        .where(*kosullar)
        .order_by(Musteri.ad_soyad, Musteri.musteri_id)
        .limit(limit)
        .offset(offset)
    ).all()
    return liste, toplam


def musteri_guncelle(db: Session, musteri_id: uuid.UUID, veri: MusteriGuncelle) -> Musteri:
    musteri = musteri_getir(db, musteri_id)
    for sutun, deger in _sutunlar(veri.model_dump(exclude_unset=True)).items():
        setattr(musteri, sutun, deger)
    kaydet(db, _TEKILLIK)
    db.refresh(musteri)     # guncelleme_zamani DB trigger'ı ile değişir
    return musteri


def musteri_sil(db: Session, musteri_id: uuid.UUID) -> None:
    """Soft delete: kayıt fiziksel olarak silinmez."""
    musteri = musteri_getir(db, musteri_id)
    musteri.silindi_at = func.now()
    db.commit()
