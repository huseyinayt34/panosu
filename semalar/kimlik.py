"""Kimlik, oturum, davet ve üye şemaları (Pydantic v2)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from servisler.kimlik import PAROLA_EN_AZ, PAROLA_EN_COK, parola_kurali_hatasi

# Hesap e-postası: sözdizimi denetimi. EmailStr özel kullanım alan adlarını (.local, .test) reddeder; tasarımın demo
# hesabı demo@panosu.local olduğu için kullanılmaz. E-posta doğrulama kapsam dışı (K7); tekillik citext ile.
HesapEposta = Annotated[str, StringConstraints(strip_whitespace=True, max_length=254,
                                               pattern=r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")]
AdSoyad = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
IsletmeAdi = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Parola = Annotated[str, Field(min_length=PAROLA_EN_AZ, max_length=PAROLA_EN_COK)]
Sektor = Literal["berber", "kuafor", "guzellik", "kafe", "spor_salonu", "diger"]
DavetRolu = Literal["yonetici", "calisan"]
Token = Annotated[str, Field(min_length=1, max_length=200)]


class _ParolaliKayit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eposta: HesapEposta
    ad_soyad: AdSoyad
    parola: Parola

    @model_validator(mode="after")
    def _parola_kurali(self):
        hata = parola_kurali_hatasi(self.parola, self.eposta)
        if hata:
            raise ValueError(hata)
        return self


class KayitIstegi(_ParolaliKayit):
    isletme_adi: IsletmeAdi
    sektor: Sektor | None = None          # stüdyolar: spor_salonu


class DavetliKayitIstegi(_ParolaliKayit):
    kod: Token


class GirisIstegi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eposta: HesapEposta
    parola: Annotated[str, Field(min_length=1, max_length=PAROLA_EN_COK)]   # kural yalnız kayıtta; girişte 401


class YenilemeIstegi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    yenileme_tokeni: Token


class IsletmeSecIstegi(BaseModel):
    """İstemcinin önerdiği isletme_id; sunucu üyeliği doğrulamadan hiçbir sorguda kullanılmaz (K9)."""
    model_config = ConfigDict(extra="forbid")

    isletme_id: uuid.UUID
    yenileme_tokeni: Token


class TokenCiftiYanit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    erisim_tokeni: str
    yenileme_tokeni: str
    token_turu: Literal["bearer"] = "bearer"
    erisim_bitis_sn: int
    isletme_id: uuid.UUID | None


class UyelikYanit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    isletme_id: uuid.UUID
    isletme_adi: str
    rol: str


class GirisYanit(TokenCiftiYanit):
    uyelikler: list[UyelikYanit]


class BenYanit(BaseModel):
    kullanici_id: uuid.UUID
    eposta: str
    ad_soyad: str
    son_giris_zamani: datetime | None
    uyelikler: list[UyelikYanit]


class DavetOlustur(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rol: DavetRolu


class DavetYanit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    davet_id: uuid.UUID
    rol: DavetRolu
    son_kullanma: datetime
    olusturma_zamani: datetime


class DavetOlusturYanit(DavetYanit):
    kod: str                              # yalnızca bu yanıtta, bir kez görünür


class DavetKabulIstegi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kod: Token


class UyeYanit(BaseModel):
    kullanici_id: uuid.UUID
    ad_soyad: str
    eposta: str
    rol: str
    olusturma_zamani: datetime
