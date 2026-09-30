"""Ziyaret uçları (tüm roller). Servis istisnaları burada HTTP kodlarına çevrilir."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from bagimliliklar import kiraci_db
from semalar.ziyaret import KalemYanit, MusteriOzet, ZiyaretGuncelle, ZiyaretOlustur, ZiyaretYanit
from servisler import ziyaret_servisi as servis
from servisler.musteri_servisi import MusteriBulunamadi
from servisler.ziyaret_servisi import ZiyaretBulunamadi, ZiyaretGecersiz, ZiyaretKaydi

router = APIRouter(tags=["Ziyaretler"])

_MUSTERI_YOK = "Müşteri bulunamadı"
_ZIYARET_YOK = "Ziyaret bulunamadı"


def _yanit(kayit: ZiyaretKaydi) -> ZiyaretYanit:
    return ZiyaretYanit.model_validate(kayit.ziyaret).model_copy(
        update={"kalemler": [KalemYanit.model_validate(k) for k in kayit.kalemler]}
    )


@router.post(
    "/musteriler/{musteri_id}/ziyaretler",
    response_model=ZiyaretYanit,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"description": _MUSTERI_YOK}},
)
def ziyaret_olustur(musteri_id: uuid.UUID, veri: ZiyaretOlustur, db: Session = Depends(kiraci_db)):
    try:
        return _yanit(servis.ziyaret_olustur(db, musteri_id, veri))
    except MusteriBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _MUSTERI_YOK)
    except ZiyaretGecersiz as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))


@router.get(
    "/musteriler/{musteri_id}/ziyaretler",
    response_model=list[ZiyaretYanit],
    responses={404: {"description": _MUSTERI_YOK}},
)
def ziyaretleri_listele(
    musteri_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(kiraci_db),
):
    try:
        return [_yanit(k) for k in servis.ziyaretleri_listele(db, musteri_id, limit, offset)]
    except MusteriBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _MUSTERI_YOK)


@router.get("/ziyaretler/{ziyaret_id}", response_model=ZiyaretYanit, responses={404: {"description": _ZIYARET_YOK}})
def ziyaret_getir(ziyaret_id: uuid.UUID, db: Session = Depends(kiraci_db)):
    try:
        return _yanit(servis.ziyaret_getir(db, ziyaret_id))
    except ZiyaretBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _ZIYARET_YOK)


@router.patch("/ziyaretler/{ziyaret_id}", response_model=ZiyaretYanit, responses={404: {"description": _ZIYARET_YOK}})
def ziyaret_guncelle(ziyaret_id: uuid.UUID, veri: ZiyaretGuncelle, db: Session = Depends(kiraci_db)):
    try:
        return _yanit(servis.ziyaret_guncelle(db, ziyaret_id, veri))
    except ZiyaretBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _ZIYARET_YOK)


@router.get(
    "/musteriler/{musteri_id}/ozet",
    response_model=MusteriOzet,
    responses={404: {"description": _MUSTERI_YOK}},
)
def musteri_ozeti(musteri_id: uuid.UUID, db: Session = Depends(kiraci_db)):
    try:
        return servis.musteri_ozeti(db, musteri_id)
    except MusteriBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _MUSTERI_YOK)
