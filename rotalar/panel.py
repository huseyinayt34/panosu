"""Panel uçları. Yenileme ve sessiz üye listeleri tüm roller; finans yalnızca sahip ve yönetici."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from bagimliliklar import kiraci_db, rol_gerektir
from semalar.gider import AY_DESENI, ay_coz
from semalar.panel import FinansYanit, SessizUyelerYanit, YenilemePaneliYanit
from servisler import finans_servisi, yenileme_servisi as servis

router = APIRouter(prefix="/panel", tags=["Panel"])


@router.get("/yenilemeler", response_model=YenilemePaneliYanit)
def yenilemeler(gun: int = Query(45, ge=1, le=365), db: Session = Depends(kiraci_db)):
    """Bitişi önümüzdeki `gun` gün içinde olan aktif paketler, Riskteki Para azalan; başta toplam ve paket sayısı."""
    p = servis.yenileme_paneli(db, gun)
    return YenilemePaneliYanit(bugun=p.bugun, gun=p.gun, toplam_riskteki_para=p.toplam_riskteki_para,
                               paket_sayisi=p.paket_sayisi, ogeler=p.ogeler)


@router.get("/sessiz-uyeler", response_model=SessizUyelerYanit)
def sessiz_uyeler(esik: Decimal = Query(Decimal("0.5"), ge=0, le=1), db: Session = Depends(kiraci_db)):
    """Aktif paketi olup P(hayatta şimdi) < esik olan üyeler; Riskteki Para azalan, eşitlikte sessizlik süresi azalan."""
    s = servis.sessiz_uyeler(db, esik)
    return SessizUyelerYanit(esik=s.esik, uye_sayisi=s.uye_sayisi, toplam_riskteki_para=s.toplam_riskteki_para,
                             ogeler=s.ogeler)


@router.get("/finans", response_model=FinansYanit)
def finans(ay: str | None = Query(None, pattern=AY_DESENI, description="YYYY-AA; verilmezse bu ay"),
           db: Session = Depends(rol_gerektir("sahip", "yonetici"))):
    """Kasaya giren, gerçek gelir, gider, kâr/zarar, günlük döküm, aktif üye ve başabaş."""
    hedef = ay_coz(ay) if ay else servis.isletme_bugun(db).replace(day=1)
    return FinansYanit.model_validate(finans_servisi.finans_ozeti(db, hedef))
