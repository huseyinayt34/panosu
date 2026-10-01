"""Rapor uçları (yalnızca sahip ve yönetici; finansal bilgi içerir)."""

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from bagimliliklar import rol_gerektir
from servisler.rapor_servisi import haftalik_rapor

router = APIRouter(prefix="/rapor", tags=["Rapor"])


@router.get("/haftalik", response_class=HTMLResponse)
def haftalik(db: Session = Depends(rol_gerektir("sahip", "yonetici"))):
    """Tek sayfalık, A4'e yazdırılabilir haftalık rapor (tarayıcıda Ctrl+P → PDF)."""
    return HTMLResponse(haftalik_rapor(db))
