"""Panel uçları (tüm roller)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from bagimliliklar import kiraci_db
from semalar.panel import YenilemePaneliYanit
from servisler import yenileme_servisi as servis

router = APIRouter(prefix="/panel", tags=["Panel"])


@router.get("/yenilemeler", response_model=YenilemePaneliYanit)
def yenilemeler(gun: int = Query(45, ge=1, le=365), db: Session = Depends(kiraci_db)):
    """Bitişi önümüzdeki `gun` gün içinde olan aktif paketler, Riskteki Para azalan; başta toplam ve paket sayısı."""
    p = servis.yenileme_paneli(db, gun)
    return YenilemePaneliYanit(bugun=p.bugun, gun=p.gun, toplam_riskteki_para=p.toplam_riskteki_para,
                               paket_sayisi=p.paket_sayisi, ogeler=p.ogeler)
