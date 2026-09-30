"""Hizmet kataloğu uçları. Yazma yalnızca sahip/yönetici; okuma tüm roller. Silme ucu yoktur."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from bagimliliklar import kiraci_db, rol_gerektir
from semalar.hizmet import HizmetDurumFiltresi, HizmetGuncelle, HizmetOlustur, HizmetYanit
from servisler import hizmet_servisi as servis
from servisler.hizmet_servisi import HizmetAdiZatenVar, HizmetBulunamadi

router = APIRouter(prefix="/hizmetler", tags=["Hizmetler"])

_BULUNAMADI = "Hizmet bulunamadı"
_AD_VAR = "Bu adla kayıtlı bir hizmet zaten var"
_404 = {404: {"description": _BULUNAMADI}}
_409 = {409: {"description": _AD_VAR}}

yonetici_db = rol_gerektir("sahip", "yonetici")

DurumSorgusu = Annotated[HizmetDurumFiltresi, Query(description="aktif (varsayılan), pasif veya hepsi")]


@router.post("", response_model=HizmetYanit, status_code=status.HTTP_201_CREATED, responses=_409)
def hizmet_olustur(veri: HizmetOlustur, db: Session = Depends(yonetici_db)):
    try:
        return servis.hizmet_olustur(db, veri)
    except HizmetAdiZatenVar:
        raise HTTPException(status.HTTP_409_CONFLICT, _AD_VAR)


@router.get("", response_model=list[HizmetYanit])
def hizmetleri_listele(durum: DurumSorgusu = "aktif", db: Session = Depends(kiraci_db)):
    return servis.hizmetleri_listele(db, durum)


@router.get("/{hizmet_id}", response_model=HizmetYanit, responses=_404)
def hizmet_getir(hizmet_id: uuid.UUID, db: Session = Depends(kiraci_db)):
    try:
        return servis.hizmet_getir(db, hizmet_id)
    except HizmetBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _BULUNAMADI)


@router.patch("/{hizmet_id}", response_model=HizmetYanit, responses={**_404, **_409})
def hizmet_guncelle(hizmet_id: uuid.UUID, veri: HizmetGuncelle, db: Session = Depends(yonetici_db)):
    try:
        return servis.hizmet_guncelle(db, hizmet_id, veri)
    except HizmetBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _BULUNAMADI)
    except HizmetAdiZatenVar:
        raise HTTPException(status.HTTP_409_CONFLICT, _AD_VAR)
