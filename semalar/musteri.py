"""Müşteri istek/yanıt şemaları (Pydantic v2)."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator, model_validator

from servisler.telefon import telefon_normallestir

AdSoyad = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Notlar = Annotated[str, Field(max_length=2000)]


class MusteriOlustur(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ad_soyad: AdSoyad
    telefon: str | None = None
    eposta: EmailStr | None = None
    notlar: Notlar | None = None

    @field_validator("telefon")
    @classmethod
    def _telefon(cls, deger: str | None) -> str | None:
        return telefon_normallestir(deger)


class MusteriGuncelle(BaseModel):
    """Kısmi güncelleme: yalnızca gönderilen alanlar uygulanır (model_dump(exclude_unset=True))."""
    model_config = ConfigDict(extra="forbid")

    ad_soyad: AdSoyad | None = None
    telefon: str | None = None
    eposta: EmailStr | None = None
    notlar: Notlar | None = None

    @field_validator("ad_soyad")
    @classmethod
    def _ad_soyad_bos_olamaz(cls, deger: str | None) -> str:
        # Varsayılan değer doğrulanmaz; buraya yalnızca açıkça gönderilen null düşer
        if deger is None:
            raise ValueError("ad_soyad boş (null) olamaz")
        return deger

    @field_validator("telefon")
    @classmethod
    def _telefon(cls, deger: str | None) -> str | None:
        return telefon_normallestir(deger)

    @model_validator(mode="after")
    def _en_az_bir_alan(self):
        if not self.model_fields_set:
            raise ValueError("Güncellenecek en az bir alan gönderilmelidir")
        return self


class MusteriYanit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    musteri_id: uuid.UUID
    ad_soyad: str
    telefon_e164: str | None
    eposta: str | None
    notlar: str | None
    kaynak: str
    olusturma_zamani: datetime
    guncelleme_zamani: datetime


class MusteriListesi(BaseModel):
    ogeler: list[MusteriYanit]
    toplam: int
    limit: int
    offset: int
