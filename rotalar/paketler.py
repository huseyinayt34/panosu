"""Üyelik paketi uçları. Oluşturma/güncelleme sahip ve yönetici; okuma tüm roller."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from bagimliliklar import kiraci_db, rol_gerektir
from models import MusteriPaketi
from semalar.paket import PaketGuncelle, PaketOlustur, PaketYanit
from servisler import paket_servisi as servis
from servisler.musteri_servisi import MusteriBulunamadi
from servisler.paket_servisi import PaketBulunamadi, PaketCakisiyor, PaketGecersiz

router = APIRouter(tags=["Paketler"])

_MUSTERI_YOK = "Müşteri bulunamadı"
_PAKET_YOK = "Paket bulunamadı"
_CAKISMA = "Müşterinin aktif paketi bu tarihten sonra bitiyor (çakışan paket)"
_YAZICI = rol_gerektir("sahip", "yonetici")


def _yanit(db: Session, paket: MusteriPaketi) -> PaketYanit:
    return PaketYanit.model_validate(paket).model_copy(update={"kalan_giris": servis.kalan_giris(db, paket)})


@router.post(
    "/musteriler/{musteri_id}/paketler",
    response_model=PaketYanit,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"description": _MUSTERI_YOK}, 409: {"description": _CAKISMA}},
)
def paket_olustur(musteri_id: uuid.UUID, veri: PaketOlustur, db: Session = Depends(_YAZICI)):
    try:
        return _yanit(db, servis.paket_olustur(db, musteri_id, veri))
    except MusteriBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _MUSTERI_YOK)
    except PaketCakisiyor:
        raise HTTPException(status.HTTP_409_CONFLICT, _CAKISMA)
    except PaketGecersiz as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))


@router.get(
    "/musteriler/{musteri_id}/paketler",
    response_model=list[PaketYanit],
    responses={404: {"description": _MUSTERI_YOK}},
)
def paketleri_listele(musteri_id: uuid.UUID, db: Session = Depends(kiraci_db)):
    try:
        return [_yanit(db, p) for p in servis.paketleri_listele(db, musteri_id)]
    except MusteriBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _MUSTERI_YOK)


@router.get("/paketler/{paket_id}", response_model=PaketYanit, responses={404: {"description": _PAKET_YOK}})
def paket_getir(paket_id: uuid.UUID, db: Session = Depends(kiraci_db)):
    try:
        return _yanit(db, servis.paket_getir(db, paket_id))
    except PaketBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _PAKET_YOK)


@router.patch("/paketler/{paket_id}", response_model=PaketYanit, responses={404: {"description": _PAKET_YOK}})
def paket_guncelle(paket_id: uuid.UUID, veri: PaketGuncelle, db: Session = Depends(_YAZICI)):
    try:
        return _yanit(db, servis.paket_guncelle(db, paket_id, veri))
    except PaketBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _PAKET_YOK)
    except PaketGecersiz as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))
