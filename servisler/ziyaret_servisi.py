"""Ziyaret iş mantığı. FastAPI'ye bağımlı değildir.

- Kiracı izolasyonu RLS ile sağlanır: başka kiracının müşterisi/hizmeti/ziyareti bu oturumda "yoktur".
- Ziyaret ve kalemleri tek işlemde yazılır; commit yalnızca en sonda yapılır.
- Para hesapları yalnızca Decimal ile yapılır.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from models import Hizmet, Isletme, Ziyaret, ZiyaretKalemi
from semalar.ziyaret import MusteriOzet, ZiyaretGuncelle, ZiyaretOlustur
from servisler.musteri_servisi import musteri_getir

GELECEK_TOLERANSI = timedelta(minutes=5)


class ZiyaretBulunamadi(Exception):
    pass


class ZiyaretGecersiz(Exception):
    """İş kuralı ihlali; mesaj kullanıcıya gösterilir (422)."""


@dataclass
class ZiyaretKaydi:
    ziyaret: Ziyaret
    kalemler: list[ZiyaretKalemi]


def _isletme_saat_dilimi(db: Session) -> ZoneInfo:
    # Kiracı filtresi değil, aktif işletmenin ayar satırını seçmek içindir: isletmeler politikası
    # kullanıcının üyesi olduğu diğer işletmeleri de gösterir.
    dilim = db.scalar(select(Isletme.saat_dilimi).where(Isletme.isletme_id == func.aktif_isletme()))
    return ZoneInfo(dilim)


def _ziyaret_zamanini_coz(db: Session, zaman: datetime) -> datetime:
    if zaman.tzinfo is None:
        zaman = zaman.replace(tzinfo=_isletme_saat_dilimi(db))
    if zaman > datetime.now(timezone.utc) + GELECEK_TOLERANSI:
        raise ZiyaretGecersiz("Ziyaret zamanı gelecekte olamaz")
    return zaman


def _kalemleri_hazirla(db: Session, veri: ZiyaretOlustur) -> list[ZiyaretKalemi]:
    kalemler = []
    for sira, girdi in enumerate(veri.kalemler, start=1):
        birim_fiyat = girdi.birim_fiyat
        if girdi.hizmet_id is not None:
            hizmet = db.get(Hizmet, girdi.hizmet_id)     # pasif hizmet de kabul edilir (geçmiş kayıt)
            if hizmet is None:
                raise ZiyaretGecersiz(f"{sira}. kalem: Hizmet bulunamadı")
            if birim_fiyat is None:
                birim_fiyat = hizmet.liste_fiyati
            if birim_fiyat is None:
                raise ZiyaretGecersiz(f"{sira}. kalem: hizmetin liste fiyatı yok, birim_fiyat verilmelidir")

        if girdi.adet * birim_fiyat - girdi.indirim_tutari < 0:
            raise ZiyaretGecersiz(f"{sira}. kalem: indirim, kalem tutarından büyük olamaz")

        kalemler.append(ZiyaretKalemi(
            hizmet_id=girdi.hizmet_id,
            aciklama=girdi.aciklama,
            adet=girdi.adet,
            birim_fiyat=birim_fiyat,
            indirim_tutari=girdi.indirim_tutari,
        ))
    return kalemler


def _toplam_tutar(veri: ZiyaretOlustur, kalemler: list[ZiyaretKalemi]) -> Decimal:
    if not kalemler:
        if veri.toplam_tutar is None:
            raise ZiyaretGecersiz("Kalem girilmeyen ziyarette toplam_tutar zorunludur")
        return veri.toplam_tutar

    hesaplanan = sum((k.adet * k.birim_fiyat - k.indirim_tutari for k in kalemler), Decimal("0"))
    if veri.toplam_tutar is not None and veri.toplam_tutar != hesaplanan:
        raise ZiyaretGecersiz(
            f"toplam_tutar ({veri.toplam_tutar}) kalemlerin toplamıyla ({hesaplanan}) uyuşmuyor"
        )
    return hesaplanan


def _kalemleri_getir(db: Session, ziyaret_idler: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[ZiyaretKalemi]]:
    gruplar: dict[uuid.UUID, list[ZiyaretKalemi]] = defaultdict(list)
    if ziyaret_idler:
        for kalem in db.scalars(
            select(ZiyaretKalemi)
            .where(ZiyaretKalemi.ziyaret_id.in_(ziyaret_idler))
            .order_by(ZiyaretKalemi.olusturma_zamani, ZiyaretKalemi.kalem_id)
        ):
            gruplar[kalem.ziyaret_id].append(kalem)
    return gruplar


def ziyaret_olustur(db: Session, musteri_id: uuid.UUID, veri: ZiyaretOlustur) -> ZiyaretKaydi:
    musteri_getir(db, musteri_id)                        # silinmiş / başka kiracının → MusteriBulunamadi
    zaman = _ziyaret_zamanini_coz(db, veri.ziyaret_zamani)
    kalemler = _kalemleri_hazirla(db, veri)
    toplam = _toplam_tutar(veri, kalemler)

    ziyaret = Ziyaret(
        musteri_id=musteri_id,
        ziyaret_zamani=zaman,
        toplam_tutar=toplam,
        odeme_yontemi=veri.odeme_yontemi,
        notlar=veri.notlar,
    )
    db.add(ziyaret)
    db.flush()                                           # ziyaret_id (sunucu varsayılanı) için
    for kalem in kalemler:
        kalem.ziyaret_id = ziyaret.ziyaret_id
    db.add_all(kalemler)
    db.commit()

    db.refresh(ziyaret)
    for kalem in kalemler:                               # tutar (GENERATED) ve zamanlar DB'den
        db.refresh(kalem)
    return ZiyaretKaydi(ziyaret, kalemler)


def ziyaret_getir(db: Session, ziyaret_id: uuid.UUID) -> ZiyaretKaydi:
    ziyaret = db.scalar(select(Ziyaret).where(Ziyaret.ziyaret_id == ziyaret_id))
    if ziyaret is None:
        raise ZiyaretBulunamadi(ziyaret_id)
    return ZiyaretKaydi(ziyaret, _kalemleri_getir(db, [ziyaret_id])[ziyaret_id])


def ziyaretleri_listele(db: Session, musteri_id: uuid.UUID, limit: int, offset: int) -> list[ZiyaretKaydi]:
    musteri_getir(db, musteri_id)
    ziyaretler = db.scalars(
        select(Ziyaret)
        .where(Ziyaret.musteri_id == musteri_id)
        .order_by(Ziyaret.ziyaret_zamani.desc(), Ziyaret.ziyaret_id)
        .limit(limit)
        .offset(offset)
    ).all()
    kalemler = _kalemleri_getir(db, [z.ziyaret_id for z in ziyaretler])
    return [ZiyaretKaydi(z, kalemler[z.ziyaret_id]) for z in ziyaretler]


def ziyaret_guncelle(db: Session, ziyaret_id: uuid.UUID, veri: ZiyaretGuncelle) -> ZiyaretKaydi:
    kayit = ziyaret_getir(db, ziyaret_id)
    for alan, deger in veri.model_dump(exclude_unset=True).items():
        setattr(kayit.ziyaret, alan, deger)
    db.commit()
    db.refresh(kayit.ziyaret)                            # guncelleme_zamani DB trigger'ı ile değişir
    return kayit


def musteri_ozeti(db: Session, musteri_id: uuid.UUID) -> MusteriOzet:
    musteri_getir(db, musteri_id)
    satir = db.execute(
        text("SELECT musteri_id, ziyaret_sayisi, ilk_ziyaret, son_ziyaret, toplam_ciro, "
             "ort_sepet_tutari, ciro_son_90_gun FROM v_musteri_ozet WHERE musteri_id = :musteri_id"),
        {"musteri_id": musteri_id},
    ).mappings().one()
    return MusteriOzet(**satir)
