"""Haftalık rapor (Adım 7, Bölüm 4; 9c K17): A4'e yazdırılabilir HTML. FastAPI'ye bağımlı değildir.

Rapor panelin yazdırılabilir hâlidir: riskli ve sessiz üye tabloları panelle aynı listelerden gelir
(`risk_listeleri.riskli_uyeler` / `sessiz_uye_listesi`, tumu=False; satır sayısı ve eşikler oradaki sabitlerdir).
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analitik.aciklama import AYRISTIRMA_MIN_P_AKTIF
from models import Isletme
from servisler import bicim, risk_listeleri
from servisler.finans_servisi import finans_ozeti
from servisler.yenileme_servisi import isletme_bugun

SABLON_DIZINI = Path(__file__).resolve().parent.parent / "sablonlar"

_ortam = Environment(loader=FileSystemLoader(SABLON_DIZINI), autoescape=select_autoescape(["html"]))
_ortam.globals.update(para=bicim.para, tarih=bicim.tarih, yuzde=bicim.yuzde, ay_adi=bicim.ay_adi,
                      olasilik=bicim.olasilik, telefon=bicim.telefon, ondalik=bicim.ondalik,
                      AYRISTIRMA_MIN_P_AKTIF=AYRISTIRMA_MIN_P_AKTIF)


def haftalik_rapor(db: Session) -> str:
    bugun = isletme_bugun(db)
    return _ortam.get_template("haftalik_rapor.html").render(
        isletme_adi=db.scalar(select(Isletme.ad).where(Isletme.isletme_id == func.aktif_isletme())),
        bugun=bugun,
        finans=finans_ozeti(db, bugun.replace(day=1)),
        riskli=risk_listeleri.riskli_uyeler(db),
        sessiz=risk_listeleri.sessiz_uye_listesi(db),
        tablo_satiri=risk_listeleri.TABLO_SATIRI,         # çağrı anında okunur
    )
