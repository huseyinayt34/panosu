"""Hizmet (katalog) istek/yanıt şemaları (Pydantic v2)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from semalar.ortak import KismiGuncelleme, Para

HizmetAdi = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Kategori = Annotated[str, Field(max_length=50)]
SureDk = Annotated[int, Field(gt=0)]
HizmetDurumFiltresi = Literal["aktif", "pasif", "hepsi"]


class HizmetOlustur(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ad: HizmetAdi
    kategori: Kategori | None = None
    liste_fiyati: Para | None = None
    sure_dk: SureDk | None = None


class HizmetGuncelle(KismiGuncelleme):
    NULL_OLAMAZ = ("ad", "aktif_mi")

    ad: HizmetAdi | None = None
    kategori: Kategori | None = None
    liste_fiyati: Para | None = None
    sure_dk: SureDk | None = None
    aktif_mi: bool | None = None


class HizmetYanit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hizmet_id: uuid.UUID
    ad: str
    kategori: str | None
    liste_fiyati: Decimal | None
    sure_dk: int | None
    aktif_mi: bool
    olusturma_zamani: datetime
    guncelleme_zamani: datetime
