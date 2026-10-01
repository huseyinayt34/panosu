"""Haftalık rapor (Adım 7, Bölüm 4): tek sayfa, A4'e yazdırılabilir HTML. FastAPI'ye bağımlı değildir."""

from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Isletme
from servisler import bicim
from servisler.finans_servisi import PANEL_UFUK_GUN, finans_ozeti
from servisler.yenileme_servisi import isletme_bugun, sessiz_uyeler, yenileme_paneli

SABLON_DIZINI = Path(__file__).resolve().parent.parent / "sablonlar"
TABLO_SATIRI = 10
SESSIZ_ESIK = Decimal("0.5")

_ortam = Environment(loader=FileSystemLoader(SABLON_DIZINI), autoescape=select_autoescape(["html"]))
_ortam.globals.update(para=bicim.para, tarih=bicim.tarih, yuzde=bicim.yuzde)


def haftalik_rapor(db: Session) -> str:
    isletme = db.scalar(select(Isletme).where(Isletme.isletme_id == func.aktif_isletme()))
    dilim = ZoneInfo(isletme.saat_dilimi)
    bugun = isletme_bugun(db)
    sessizler = sessiz_uyeler(db, SESSIZ_ESIK).ogeler[:TABLO_SATIRI]
    for o in sessizler:
        o["son_ziyaret_gunu"] = o["son_ziyaret"].astimezone(dilim).date() if o["son_ziyaret"] else None
    return _ortam.get_template("haftalik_rapor.html").render(
        isletme_adi=isletme.ad,
        bugun=bugun,
        finans=finans_ozeti(db, bugun.replace(day=1)),
        yenilemeler=yenileme_paneli(db, PANEL_UFUK_GUN).ogeler[:TABLO_SATIRI],
        sessizler=sessizler,
    )
