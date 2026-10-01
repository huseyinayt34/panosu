"""Aylık gider iş mantığı. FastAPI'ye bağımlı değildir. Kiracı izolasyonu RLS ile."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from models import IsletmeGideri

KATEGORILER = ("kira", "personel", "faturalar", "diger")


@dataclass
class AylikGider:
    ay: date
    kalemler: dict[str, Decimal | None]          # kategori → tutar (girilmemişse None)

    @property
    def toplam(self) -> Decimal | None:
        girilen = [t for t in self.kalemler.values() if t is not None]
        return sum(girilen, Decimal("0.00")) if girilen else None


def aylik_gider(db: Session, ay: date) -> AylikGider:
    satirlar = dict(db.execute(select(IsletmeGideri.kategori, IsletmeGideri.tutar).where(IsletmeGideri.ay == ay)).all())
    return AylikGider(ay=ay, kalemler={k: satirlar.get(k) for k in KATEGORILER})


def gider_kaydet(db: Session, ay: date, tutarlar: dict[str, Decimal | None]) -> AylikGider:
    """None olmayan kategorileri ekler ya da günceller; None verilen (veya verilmeyen) kategori değişmez/silinmez."""
    satirlar = [{"ay": ay, "kategori": k, "tutar": t} for k, t in tutarlar.items() if t is not None]
    if satirlar:
        tablo = IsletmeGideri.__table__
        ifade = insert(tablo).values(satirlar)               # isletme_id: DB varsayılanı aktif_isletme()
        db.execute(ifade.on_conflict_do_update(
            index_elements=[tablo.c.isletme_id, tablo.c.ay, tablo.c.kategori],
            set_={"tutar": ifade.excluded.tutar},
        ))
        db.commit()
    return aylik_gider(db, ay)


def gider_var_mi(db: Session, ay: date) -> bool:
    return bool(db.scalar(select(func.count()).select_from(IsletmeGideri).where(IsletmeGideri.ay == ay)))
