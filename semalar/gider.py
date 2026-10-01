"""Aylık gider şemaları (Pydantic v2). Para alanları yalnızca Decimal'dir."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from semalar.ortak import Para

AY_DESENI = r"^\d{4}-(0[1-9]|1[0-2])$"         # YYYY-MM


class GiderGirdi(BaseModel):
    """null (veya gönderilmeyen) kategori değişmez ve silinmez."""
    model_config = ConfigDict(extra="forbid")

    kira: Para | None = None
    personel: Para | None = None
    faturalar: Para | None = None
    diger: Para | None = None


class GiderYanit(BaseModel):
    ay: date
    kira: Decimal | None
    personel: Decimal | None
    faturalar: Decimal | None
    diger: Decimal | None
    toplam: Decimal | None                       # hiç kategori girilmemişse null


def ay_coz(metin: str) -> date:
    """'YYYY-MM' → ayın ilk günü. Biçim AY_DESENI ile rotada doğrulanır."""
    yil, ay = metin.split("-")
    return date(int(yil), int(ay), 1)
