"""Hizmet kataloğu iş mantığı. Kiracı izolasyonu RLS ile sağlanır (elle isletme_id filtresi yok).

Hizmetler silinmez; geçmiş ziyaret kalemleri onlara bağlıdır. Pasifleştirme aktif_mi=false ile yapılır.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Hizmet
from semalar.hizmet import HizmetDurumFiltresi, HizmetGuncelle, HizmetOlustur
from servisler.ortak import kaydet

HIZMET_ADI_TEKIL_KISITI = "hizmetler_isletme_id_ad_key"   # UNIQUE (isletme_id, ad)


class HizmetBulunamadi(Exception):
    pass


class HizmetAdiZatenVar(Exception):
    pass


_TEKILLIK = {HIZMET_ADI_TEKIL_KISITI: HizmetAdiZatenVar}


def hizmet_olustur(db: Session, veri: HizmetOlustur) -> Hizmet:
    hizmet = Hizmet(**veri.model_dump())
    db.add(hizmet)
    kaydet(db, _TEKILLIK)
    db.refresh(hizmet)
    return hizmet


def hizmet_getir(db: Session, hizmet_id: uuid.UUID) -> Hizmet:
    hizmet = db.scalar(select(Hizmet).where(Hizmet.hizmet_id == hizmet_id))
    if hizmet is None:
        raise HizmetBulunamadi(hizmet_id)
    return hizmet


def hizmetleri_listele(db: Session, durum: HizmetDurumFiltresi) -> Sequence[Hizmet]:
    sorgu = select(Hizmet).order_by(Hizmet.kategori, Hizmet.ad)
    if durum != "hepsi":
        sorgu = sorgu.where(Hizmet.aktif_mi.is_(durum == "aktif"))
    return db.scalars(sorgu).all()


def hizmet_guncelle(db: Session, hizmet_id: uuid.UUID, veri: HizmetGuncelle) -> Hizmet:
    hizmet = hizmet_getir(db, hizmet_id)
    for alan, deger in veri.model_dump(exclude_unset=True).items():
        setattr(hizmet, alan, deger)
    kaydet(db, _TEKILLIK)
    db.refresh(hizmet)
    return hizmet
