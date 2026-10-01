"""Üyelik paketi iş mantığı. FastAPI'ye bağımlı değildir.

- Kiracı izolasyonu RLS ile sağlanır: başka kiracının müşterisi/paketi bu oturumda "yoktur".
- Para alanları Decimal'dir.
"""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Isletme, MusteriPaketi, Ziyaret
from semalar.paket import PaketGuncelle, PaketOlustur
from servisler.musteri_servisi import musteri_getir
from servisler.ortak import kaydet


class PaketBulunamadi(Exception):
    pass


class PaketGecersiz(Exception):
    """İş kuralı ihlali; mesaj kullanıcıya gösterilir (422)."""


class PaketCakisiyor(Exception):
    """Müşterinin aktif paketi bitmeden yeni paket başlıyor (409)."""


def _yerel_tarih(sutun):
    """timestamptz sütununu işletmenin yerel takvim gününe çevirir (aktif işletmenin saat dilimi)."""
    dilim = select(Isletme.saat_dilimi).where(Isletme.isletme_id == func.aktif_isletme()).scalar_subquery()
    return func.date(func.timezone(dilim, sutun))


def kalan_giris(db: Session, paket: MusteriPaketi) -> int | None:
    """Giriş bazlıda giris_hakki − paket dönemindeki (başlangıç..bitiş, bitiş yoksa açık uçlu) tamamlanmış
    ziyaret sayısı; 0'ın altına inmez. Süre bazlıda None."""
    if paket.tur != "giris":
        return None
    gun = _yerel_tarih(Ziyaret.ziyaret_zamani)
    kosullar = [Ziyaret.musteri_id == paket.musteri_id, Ziyaret.durum == "tamamlandi", gun >= paket.baslangic_tarihi]
    if paket.bitis_tarihi is not None:
        kosullar.append(gun <= paket.bitis_tarihi)
    kullanilan = db.scalar(select(func.count()).select_from(Ziyaret).where(*kosullar))
    return max(0, paket.giris_hakki - kullanilan)


def _en_son_paket(db: Session, musteri_id: uuid.UUID) -> MusteriPaketi | None:
    return db.scalar(
        select(MusteriPaketi)
        .where(MusteriPaketi.musteri_id == musteri_id)
        .order_by(MusteriPaketi.baslangic_tarihi.desc(), MusteriPaketi.olusturma_zamani.desc())
        .limit(1)
    )


def _cakisma_denetle(db: Session, musteri_id: uuid.UUID, baslangic: date) -> None:
    cakisan = db.scalar(
        select(MusteriPaketi.paket_id).where(
            MusteriPaketi.musteri_id == musteri_id,
            MusteriPaketi.durum == "aktif",
            MusteriPaketi.bitis_tarihi.is_not(None),
            MusteriPaketi.bitis_tarihi > baslangic,
        ).limit(1)
    )
    if cakisan is not None:
        raise PaketCakisiyor(cakisan)


def paket_olustur(db: Session, musteri_id: uuid.UUID, veri: PaketOlustur) -> MusteriPaketi:
    musteri_getir(db, musteri_id)                        # silinmiş / başka kiracının → MusteriBulunamadi
    _cakisma_denetle(db, musteri_id, veri.baslangic_tarihi)

    onceki_id = veri.onceki_paket_id
    if onceki_id is None:
        onceki = _en_son_paket(db, musteri_id)
        onceki_id = onceki.paket_id if onceki else None
    else:
        onceki = db.get(MusteriPaketi, onceki_id)
        if onceki is None or onceki.musteri_id != musteri_id:
            raise PaketGecersiz("onceki_paket_id bu müşterinin bir paketi değil")

    paket = MusteriPaketi(musteri_id=musteri_id, onceki_paket_id=onceki_id,
                          **veri.model_dump(exclude={"onceki_paket_id"}))
    db.add(paket)
    kaydet(db)
    db.refresh(paket)
    return paket


def paket_getir(db: Session, paket_id: uuid.UUID) -> MusteriPaketi:
    paket = db.get(MusteriPaketi, paket_id)
    if paket is None:
        raise PaketBulunamadi(paket_id)
    return paket


def paketleri_listele(db: Session, musteri_id: uuid.UUID) -> list[MusteriPaketi]:
    musteri_getir(db, musteri_id)
    return list(db.scalars(
        select(MusteriPaketi)
        .where(MusteriPaketi.musteri_id == musteri_id)
        .order_by(MusteriPaketi.baslangic_tarihi.desc(), MusteriPaketi.olusturma_zamani.desc())
    ))


def paket_guncelle(db: Session, paket_id: uuid.UUID, veri: PaketGuncelle) -> MusteriPaketi:
    paket = paket_getir(db, paket_id)
    alanlar = veri.model_dump(exclude_unset=True)
    if "bitis_tarihi" in alanlar:
        bitis = alanlar["bitis_tarihi"]
        if bitis is None and paket.tur == "sure":
            raise PaketGecersiz("Süre bazlı pakette bitis_tarihi boş olamaz")
        if bitis is not None and bitis <= paket.baslangic_tarihi:
            raise PaketGecersiz("bitis_tarihi baslangic_tarihi'nden sonra olmalıdır")
    for alan, deger in alanlar.items():
        setattr(paket, alan, deger)
    kaydet(db)
    db.refresh(paket)                                    # guncelleme_zamani DB trigger'ı ile değişir
    return paket
