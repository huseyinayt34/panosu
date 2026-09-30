"""Müşteri uçları. Servis istisnaları burada HTTP kodlarına çevrilir."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from bagimliliklar import kiraci_db, rol_gerektir
from semalar.musteri import MusteriGuncelle, MusteriListesi, MusteriOlustur, MusteriYanit
from servisler import musteri_servisi as servis
from servisler.musteri_servisi import MusteriBulunamadi, TelefonZatenKayitli

router = APIRouter(prefix="/musteriler", tags=["Müşteriler"])

_BULUNAMADI = "Müşteri bulunamadı"
_TELEFON_KAYITLI = "Bu telefon numarasıyla kayıtlı bir müşteri zaten var"
_404 = {404: {"description": _BULUNAMADI}}
_409 = {409: {"description": _TELEFON_KAYITLI}}


@router.post("", response_model=MusteriYanit, status_code=status.HTTP_201_CREATED, responses=_409)
def musteri_olustur(veri: MusteriOlustur, db: Session = Depends(kiraci_db)):
    try:
        return servis.musteri_olustur(db, veri)
    except TelefonZatenKayitli:
        raise HTTPException(status.HTTP_409_CONFLICT, _TELEFON_KAYITLI)


@router.get("", response_model=MusteriListesi)
def musterileri_listele(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(kiraci_db),
):
    liste, toplam = servis.musterileri_listele(db, q, limit, offset)
    return MusteriListesi(
        ogeler=[MusteriYanit.model_validate(m) for m in liste], toplam=toplam, limit=limit, offset=offset
    )


@router.get("/{musteri_id}", response_model=MusteriYanit, responses=_404)
def musteri_getir(musteri_id: uuid.UUID, db: Session = Depends(kiraci_db)):
    try:
        return servis.musteri_getir(db, musteri_id)
    except MusteriBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _BULUNAMADI)


@router.patch("/{musteri_id}", response_model=MusteriYanit, responses={**_404, **_409})
def musteri_guncelle(musteri_id: uuid.UUID, veri: MusteriGuncelle, db: Session = Depends(kiraci_db)):
    try:
        return servis.musteri_guncelle(db, musteri_id, veri)
    except MusteriBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _BULUNAMADI)
    except TelefonZatenKayitli:
        raise HTTPException(status.HTTP_409_CONFLICT, _TELEFON_KAYITLI)


@router.delete("/{musteri_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_404)
def musteri_sil(musteri_id: uuid.UUID, db: Session = Depends(rol_gerektir("sahip", "yonetici"))) -> None:
    try:
        servis.musteri_sil(db, musteri_id)
    except MusteriBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _BULUNAMADI)
