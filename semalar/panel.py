"""Panel yanıt şemaları (Pydantic v2). Para alanları Decimal'dir."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class YenilemeOgesi(BaseModel):
    paket_id: uuid.UUID
    musteri_id: uuid.UUID
    ad_soyad: str
    telefon_e164: str | None
    whatsapp_izni_var: bool
    son_ziyaret: datetime | None
    paket_adi: str
    tur: str
    bitis_tarihi: date | None
    kalan_gun: int | None
    kalan_giris: int | None
    p_yenileme: Decimal
    yenileme_tutari: Decimal
    riskteki_para: Decimal
    hesaplama_tarihi: date
    model_versiyonu: str


class YenilemePaneliYanit(BaseModel):
    bugun: date
    gun: int
    toplam_riskteki_para: Decimal
    paket_sayisi: int
    ogeler: list[YenilemeOgesi]
