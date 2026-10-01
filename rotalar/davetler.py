"""Davet ve üye uçları. Servis istisnaları burada HTTP kodlarına çevrilir."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from bagimliliklar import Kimlik, kimlik_dogrula, kullanici_db, rol_gerektir
from semalar.kimlik import DavetKabulIstegi, DavetOlustur, DavetOlusturYanit, DavetYanit, UyelikYanit, UyeYanit
from servisler import davet_servisi as servis
from servisler.davet_servisi import DavetBulunamadi, UyeBulunamadi, UyeSilinemez
from servisler.kimlik import DavetGecersiz, ZatenUye, davet_kabul

router = APIRouter(tags=["Davetler"])
uye_router = APIRouter(prefix="/uyeler", tags=["Üyeler"])

_YONETIM = rol_gerektir("sahip", "yonetici")
_DAVET_YOK = "Davet bulunamadı"


@router.post("/davetler", response_model=DavetOlusturYanit, status_code=status.HTTP_201_CREATED,
             responses={403: {"description": "Yönetici yalnızca çalışan davet edebilir"}})
def davet_olustur(veri: DavetOlustur, db: Session = Depends(_YONETIM)):
    """Tek kullanımlık davet kodu (7 gün). Kod yalnızca bu yanıtta görünür; sahip WhatsApp'tan iletir."""
    if db.info["rol"] == "yonetici" and veri.rol != "calisan":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Yönetici yalnızca çalışan davet edebilir")
    return DavetOlusturYanit.model_validate(servis.davet_olustur(db, veri.rol), from_attributes=True)


@router.get("/davetler", response_model=list[DavetYanit])
def davetleri_listele(db: Session = Depends(_YONETIM)):
    """Açık (kullanılmamış, iptal edilmemiş, süresi geçmemiş) davetler; kod gösterilmez."""
    return servis.acik_davetler(db)


@router.post("/davetler/{davet_id}/iptal", status_code=status.HTTP_204_NO_CONTENT,
             responses={404: {"description": _DAVET_YOK}})
def davet_iptal(davet_id: uuid.UUID, db: Session = Depends(_YONETIM)) -> Response:
    try:
        servis.davet_iptal(db, davet_id)
    except DavetBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _DAVET_YOK)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/davetler/kabul", response_model=UyelikYanit,
             responses={404: {"description": _DAVET_YOK}, 409: {"description": "Zaten üyesiniz"}})
def kabul(veri: DavetKabulIstegi, kimlik: Kimlik = Depends(kimlik_dogrula), db: Session = Depends(kullanici_db)):
    """Giriş yapmış kullanıcı davet koduyla işletmeye üye olur (sonra /oturum/isletme-sec)."""
    try:
        return UyelikYanit.model_validate(davet_kabul(db, veri.kod, kimlik.kullanici_id))
    except DavetGecersiz:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _DAVET_YOK)
    except ZatenUye:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu işletmenin zaten üyesisiniz")


@uye_router.get("", response_model=list[UyeYanit])
def uyeleri_listele(db: Session = Depends(_YONETIM)):
    return servis.uyeler(db)


@uye_router.delete("/{kullanici_id}", status_code=status.HTTP_204_NO_CONTENT,
                   responses={404: {"description": "Üye bulunamadı"}, 409: {"description": "Silinemez"}})
def uye_sil(kullanici_id: uuid.UUID, kimlik: Kimlik = Depends(kimlik_dogrula),
            db: Session = Depends(rol_gerektir("sahip"))) -> Response:
    """Üyeliği siler. Sahip kendini silemez; son sahip silinemez (409)."""
    try:
        servis.uye_sil(db, kullanici_id, kimlik.kullanici_id)
    except UyeBulunamadi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Üye bulunamadı")
    except UyeSilinemez as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
