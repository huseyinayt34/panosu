"""Üyelik paketi şemaları (Pydantic v2). Tür kuralları DB CHECK'leriyle aynıdır; ihlal → 422."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from semalar.ortak import KismiGuncelleme, Para

PaketTuru = Literal["sure", "giris"]
PaketDurumu = Literal["aktif", "bitti", "iptal", "donduruldu"]
PaketAdi = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class PaketOlustur(BaseModel):
    """onceki_paket_id verilmezse müşterinin en son paketi otomatik bağlanır (servis)."""
    model_config = ConfigDict(extra="forbid")

    tur: PaketTuru
    ad: PaketAdi
    baslangic_tarihi: date
    bitis_tarihi: date | None = None          # sure: zorunlu; giris: opsiyonel son kullanma
    giris_hakki: int | None = Field(None, gt=0)
    ucret: Para
    onceki_paket_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _tur_kurallari(self):
        if self.tur == "sure":
            if self.bitis_tarihi is None:
                raise ValueError("Süre bazlı pakette bitis_tarihi zorunludur")
            if self.giris_hakki is not None:
                raise ValueError("Süre bazlı pakette giris_hakki verilmez")
        elif self.giris_hakki is None:
            raise ValueError("Giriş bazlı pakette giris_hakki zorunludur")
        if self.bitis_tarihi is not None and self.bitis_tarihi <= self.baslangic_tarihi:
            raise ValueError("bitis_tarihi baslangic_tarihi'nden sonra olmalıdır")
        return self


class PaketGuncelle(KismiGuncelleme):
    """Yalnızca durum ve bitiş tarihi (dondurma uzatması) değiştirilebilir."""
    NULL_OLAMAZ = ("durum",)

    durum: PaketDurumu | None = None
    bitis_tarihi: date | None = None


class PaketYanit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    paket_id: uuid.UUID
    musteri_id: uuid.UUID
    tur: PaketTuru
    ad: str
    baslangic_tarihi: date
    bitis_tarihi: date | None
    giris_hakki: int | None
    kalan_giris: int | None = None            # giriş bazlıda: giris_hakki − paket dönemindeki tamamlanmış ziyaret
    ucret: Decimal
    durum: PaketDurumu
    onceki_paket_id: uuid.UUID | None
    olusturma_zamani: datetime
    guncelleme_zamani: datetime
