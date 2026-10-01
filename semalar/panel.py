"""Panel yanıt şemaları (Pydantic v2). Para alanları Decimal'dir."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


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


class SessizUyeOgesi(BaseModel):
    musteri_id: uuid.UUID
    ad_soyad: str
    telefon_e164: str | None
    whatsapp_izni_var: bool
    paket_id: uuid.UUID
    paket_adi: str
    tur: str
    bitis_tarihi: date | None
    kalan_gun: int | None
    kalan_giris: int | None
    son_ziyaret: datetime | None
    son_ziyaretten_gecen_gun: int | None
    p_hayatta_simdi: Decimal
    p_yenileme: Decimal
    paket_ucreti: Decimal
    riskteki_para: Decimal
    hesaplama_tarihi: date


class SessizUyelerYanit(BaseModel):
    esik: Decimal
    uye_sayisi: int
    toplam_riskteki_para: Decimal
    ogeler: list[SessizUyeOgesi]


class GunlukFinansYanit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tarih: date
    kasaya_giren: Decimal
    gercek_gelir: Decimal
    gider_payi: Decimal | None
    net: Decimal | None


class FinansYanit(BaseModel):
    """Ay bitmemişse gelirler bugüne kadar; kar_zarar = gercek_gelir − gider_bugune_kadar; uye_basi_aylik_gelir aya
    ölçeklenir; başabaş tüm ayın gideriyle (proje sahibi kararı, 2026-10-01). Ayın ilk 7 gününde üye başı gelir ve
    başabaş geçen ayın tamamlanmış verisinden (basabas_kaynak_ay)."""
    model_config = ConfigDict(from_attributes=True)

    ay: date
    bugun: date
    gecen_gun: int
    kasaya_giren: Decimal
    gercek_gelir: Decimal
    gider_toplam: Decimal | None
    gider_bugune_kadar: Decimal | None
    kar_zarar: Decimal | None
    gider_girilmedi: bool
    gunluk: list[GunlukFinansYanit]
    onceki_ay: date
    onceki_ay_kar_zarar: Decimal | None
    onceki_ay_gider_girilmedi: bool
    aktif_uye_sayisi: int
    ortalama_aktif_uye: Decimal | None
    uye_basi_aylik_gelir: Decimal | None
    basabas_uye_sayisi: int | None
    basabas_kaynak_ay: date
    basabas_farki: int | None
    zarar_icin_kayip_uye: int | None          # basabas_farki ≥ 0 ise fark + 1 (başabaşta kâr ≥ 0)
    riskteki_para_45_gun: Decimal
