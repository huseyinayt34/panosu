"""Aylık gider uçları (yalnızca sahip ve yönetici; finansal bilgi)."""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from bagimliliklar import rol_gerektir
from semalar.gider import AY_DESENI, GiderGirdi, GiderYanit, ay_coz
from servisler import gider_servisi as servis
from servisler.gider_servisi import AylikGider

router = APIRouter(prefix="/giderler", tags=["Giderler"])
_YONETIM = rol_gerektir("sahip", "yonetici")
_AY = Path(..., pattern=AY_DESENI, description="YYYY-AA")


def _yanit(g: AylikGider) -> GiderYanit:
    return GiderYanit(ay=g.ay, toplam=g.toplam, **g.kalemler)


@router.put("/{ay}", response_model=GiderYanit)
def gider_kaydet(veri: GiderGirdi, ay: str = _AY, db: Session = Depends(_YONETIM)):
    """Kayıt yoksa oluşturur, varsa günceller; null kategori değişmez ve silinmez."""
    return _yanit(servis.gider_kaydet(db, ay_coz(ay), veri.model_dump()))


@router.get("/{ay}", response_model=GiderYanit)
def gider_getir(ay: str = _AY, db: Session = Depends(_YONETIM)):
    return _yanit(servis.aylik_gider(db, ay_coz(ay)))
