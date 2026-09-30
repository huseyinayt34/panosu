"""Ziyaret ve ziyaret kalemi şemaları (Pydantic v2). Para alanları yalnızca Decimal'dir."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from semalar.ortak import KismiGuncelleme, Para

OdemeYontemi = Literal["nakit", "kart", "havale", "diger"]
ZiyaretDurumu = Literal["tamamlandi", "iptal", "gelmedi"]
ZiyaretNotu = Annotated[str, Field(max_length=1000)]


class KalemGirdi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hizmet_id: uuid.UUID | None = None
    aciklama: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None = None
    adet: int = Field(1, ge=1)
    birim_fiyat: Para | None = None           # None: hizmetin liste fiyatı kullanılır
    indirim_tutari: Para = Decimal("0")

    @model_validator(mode="after")
    def _tutarlilik(self):
        if self.hizmet_id is None and self.aciklama is None:
            raise ValueError("Kalemde hizmet_id veya aciklama verilmelidir")
        if self.hizmet_id is None and self.birim_fiyat is None:
            raise ValueError("Hizmete bağlı olmayan kalemde birim_fiyat zorunludur")
        return self


class ZiyaretOlustur(BaseModel):
    """Saat dilimi içermeyen ziyaret_zamani, işletmenin saat dilimiyle yorumlanır (servis)."""
    model_config = ConfigDict(extra="forbid")

    ziyaret_zamani: datetime
    toplam_tutar: Para | None = None          # kalem varsa sunucu hesaplar; kalem yoksa zorunlu
    odeme_yontemi: OdemeYontemi | None = None
    notlar: ZiyaretNotu | None = None
    kalemler: list[KalemGirdi] = Field(default_factory=list, max_length=50)


class ZiyaretGuncelle(KismiGuncelleme):
    """Tutar ve zaman değiştirilemez (düzeltme = iptal + yeni kayıt)."""
    NULL_OLAMAZ = ("durum",)

    durum: ZiyaretDurumu | None = None
    odeme_yontemi: OdemeYontemi | None = None
    notlar: ZiyaretNotu | None = None


class KalemYanit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kalem_id: uuid.UUID
    hizmet_id: uuid.UUID | None
    aciklama: str | None
    adet: int
    birim_fiyat: Decimal
    indirim_tutari: Decimal
    tutar: Decimal


class ZiyaretYanit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ziyaret_id: uuid.UUID
    musteri_id: uuid.UUID
    ziyaret_zamani: datetime
    durum: ZiyaretDurumu
    toplam_tutar: Decimal
    odeme_yontemi: OdemeYontemi | None
    notlar: str | None
    kalemler: list[KalemYanit] = []
    olusturma_zamani: datetime


class MusteriOzet(BaseModel):
    """v_musteri_ozet view'ından; yalnızca tamamlanmış ziyaretler sayılır."""
    musteri_id: uuid.UUID
    ziyaret_sayisi: int
    ilk_ziyaret: datetime | None
    son_ziyaret: datetime | None
    toplam_ciro: Decimal
    ort_sepet_tutari: Decimal | None
    ciro_son_90_gun: Decimal
