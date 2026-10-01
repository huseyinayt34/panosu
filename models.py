"""SQLAlchemy modelleri - faz1_sema.sql ile birebir uyumlu (çekirdek tablolar).

Şemanın tek kaynağı SQL'dir (RLS, trigger, view, CHECK'ler orada). Bu modeller yalnızca
sütunları yansıtır; Base.metadata.create_all() ASLA çağrılmaz. CHECK kısıtlarını veritabanı uygular.
Henüz eşlenmeyen tablolar: abonelikler, musteri_izinleri, churn_skorlari, kampanyalar,
mesaj_gonderimleri, geri_kazanimlar, denetim_kayitlari.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    FetchedValue,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column

from database import Base

_UUID_VARSAYILAN = text("gen_random_uuid()")
_KIRACI_VARSAYILAN = text("aktif_isletme()")   # DB, oturumdaki app.isletme_id değerini doldurur


def _olusturma_zamani() -> MappedColumn:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _guncelleme_zamani() -> MappedColumn:
    # DB trigger'ı (guncelleme_zamani_ayarla) günceller; ORM değeri DB'den okur
    return mapped_column(DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue())


class Kullanici(Base):
    __tablename__ = "kullanicilar"

    kullanici_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=_UUID_VARSAYILAN)
    dis_kimlik_id: Mapped[str | None] = mapped_column(Text, unique=True)
    eposta: Mapped[str] = mapped_column(CITEXT, unique=True)
    ad_soyad: Mapped[str] = mapped_column(Text)
    son_giris_zamani: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    olusturma_zamani: Mapped[datetime] = _olusturma_zamani()
    guncelleme_zamani: Mapped[datetime] = _guncelleme_zamani()


class Isletme(Base):
    __tablename__ = "isletmeler"

    isletme_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=_UUID_VARSAYILAN)
    ad: Mapped[str] = mapped_column(Text)
    sektor: Mapped[str | None] = mapped_column(Text)
    para_birimi: Mapped[str] = mapped_column(CHAR(3), server_default=text("'TRY'"))
    saat_dilimi: Mapped[str] = mapped_column(Text, server_default=text("'Europe/Istanbul'"))
    durum: Mapped[str] = mapped_column(Text, server_default=text("'aktif'"))
    olusturma_zamani: Mapped[datetime] = _olusturma_zamani()
    guncelleme_zamani: Mapped[datetime] = _guncelleme_zamani()


class Uyelik(Base):
    """Kullanıcı ↔ işletme ilişkisi. İşletme sahibi = rol 'sahip' (isletmeler'de sahip sütunu YOKTUR)."""
    __tablename__ = "uyelikler"

    isletme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("isletmeler.isletme_id", ondelete="CASCADE"), primary_key=True)
    kullanici_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kullanicilar.kullanici_id", ondelete="CASCADE"), primary_key=True)
    rol: Mapped[str] = mapped_column(Text)
    olusturma_zamani: Mapped[datetime] = _olusturma_zamani()


class Musteri(Base):
    __tablename__ = "musteriler"
    __table_args__ = (UniqueConstraint("isletme_id", "musteri_id"),)

    musteri_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=_UUID_VARSAYILAN)
    isletme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("isletmeler.isletme_id"), server_default=_KIRACI_VARSAYILAN)
    ad_soyad: Mapped[str] = mapped_column(Text)
    telefon_e164: Mapped[str | None] = mapped_column(Text)
    eposta: Mapped[str | None] = mapped_column(CITEXT)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    kaynak: Mapped[str] = mapped_column(Text, server_default=text("'manuel'"))
    dis_kaynak: Mapped[str | None] = mapped_column(Text)
    dis_kimlik: Mapped[str | None] = mapped_column(Text)
    notlar: Mapped[str | None] = mapped_column(Text)
    silindi_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anonimlestirildi_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    olusturma_zamani: Mapped[datetime] = _olusturma_zamani()
    guncelleme_zamani: Mapped[datetime] = _guncelleme_zamani()


class Hizmet(Base):
    __tablename__ = "hizmetler"
    __table_args__ = (
        UniqueConstraint("isletme_id", "hizmet_id"),
        UniqueConstraint("isletme_id", "ad"),
    )

    hizmet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=_UUID_VARSAYILAN)
    isletme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("isletmeler.isletme_id"), server_default=_KIRACI_VARSAYILAN)
    ad: Mapped[str] = mapped_column(Text)
    kategori: Mapped[str | None] = mapped_column(Text)
    liste_fiyati: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sure_dk: Mapped[int | None] = mapped_column(Integer)
    aktif_mi: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    olusturma_zamani: Mapped[datetime] = _olusturma_zamani()
    guncelleme_zamani: Mapped[datetime] = _guncelleme_zamani()


class Ziyaret(Base):
    __tablename__ = "ziyaretler"
    __table_args__ = (
        ForeignKeyConstraint(["isletme_id", "musteri_id"], ["musteriler.isletme_id", "musteriler.musteri_id"]),
        UniqueConstraint("isletme_id", "ziyaret_id"),
    )

    ziyaret_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=_UUID_VARSAYILAN)
    isletme_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), server_default=_KIRACI_VARSAYILAN)
    musteri_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    ziyaret_zamani: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    durum: Mapped[str] = mapped_column(Text, server_default=text("'tamamlandi'"))
    toplam_tutar: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=text("0"))
    odeme_yontemi: Mapped[str | None] = mapped_column(Text)
    kaynak: Mapped[str] = mapped_column(Text, server_default=text("'manuel'"))
    dis_kaynak: Mapped[str | None] = mapped_column(Text)
    dis_kimlik: Mapped[str | None] = mapped_column(Text)
    notlar: Mapped[str | None] = mapped_column(Text)
    olusturma_zamani: Mapped[datetime] = _olusturma_zamani()
    guncelleme_zamani: Mapped[datetime] = _guncelleme_zamani()


class ZiyaretKalemi(Base):
    __tablename__ = "ziyaret_kalemleri"
    __table_args__ = (
        ForeignKeyConstraint(
            ["isletme_id", "ziyaret_id"], ["ziyaretler.isletme_id", "ziyaretler.ziyaret_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["isletme_id", "hizmet_id"], ["hizmetler.isletme_id", "hizmetler.hizmet_id"]),
    )

    kalem_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=_UUID_VARSAYILAN)
    isletme_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), server_default=_KIRACI_VARSAYILAN)
    ziyaret_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    hizmet_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    aciklama: Mapped[str | None] = mapped_column(Text)
    adet: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    birim_fiyat: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    indirim_tutari: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=text("0"))
    # Veritabanı hesaplar (GENERATED ALWAYS); ORM asla yazmaz
    tutar: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), Computed("adet * birim_fiyat - indirim_tutari", persisted=True))
    olusturma_zamani: Mapped[datetime] = _olusturma_zamani()


class MusteriPaketi(Base):
    """Stüdyo üyelik paketi (süre veya giriş bazlı). Tür kuralları DB CHECK'lerindedir (0002)."""
    __tablename__ = "musteri_paketleri"
    __table_args__ = (
        ForeignKeyConstraint(["isletme_id", "musteri_id"], ["musteriler.isletme_id", "musteriler.musteri_id"]),
        ForeignKeyConstraint(
            ["isletme_id", "onceki_paket_id"], ["musteri_paketleri.isletme_id", "musteri_paketleri.paket_id"]),
        UniqueConstraint("isletme_id", "paket_id"),
    )

    paket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=_UUID_VARSAYILAN)
    isletme_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), server_default=_KIRACI_VARSAYILAN)
    musteri_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    tur: Mapped[str] = mapped_column(Text)
    ad: Mapped[str] = mapped_column(Text)
    baslangic_tarihi: Mapped[date] = mapped_column(Date)
    bitis_tarihi: Mapped[date | None] = mapped_column(Date)
    giris_hakki: Mapped[int | None] = mapped_column(Integer)
    ucret: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    durum: Mapped[str] = mapped_column(Text, server_default=text("'aktif'"))
    onceki_paket_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    dis_kaynak: Mapped[str | None] = mapped_column(Text)
    dis_kimlik: Mapped[str | None] = mapped_column(Text)
    olusturma_zamani: Mapped[datetime] = _olusturma_zamani()
    guncelleme_zamani: Mapped[datetime] = _guncelleme_zamani()


class YenilemeRiski(Base):
    __tablename__ = "yenileme_riskleri"
    __table_args__ = (
        ForeignKeyConstraint(["isletme_id", "musteri_id"], ["musteriler.isletme_id", "musteriler.musteri_id"]),
        ForeignKeyConstraint(["isletme_id", "paket_id"], ["musteri_paketleri.isletme_id", "musteri_paketleri.paket_id"]),
        UniqueConstraint("isletme_id", "paket_id", "hesaplama_tarihi", "model_versiyonu"),
    )

    risk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=_UUID_VARSAYILAN)
    isletme_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), server_default=_KIRACI_VARSAYILAN)
    musteri_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    paket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    hesaplama_tarihi: Mapped[date] = mapped_column(Date)
    model_versiyonu: Mapped[str] = mapped_column(Text)
    kalan_gun: Mapped[int | None] = mapped_column(Integer)
    kalan_giris: Mapped[int | None] = mapped_column(Integer)
    p_hayatta_simdi: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    p_yenileme: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    yenileme_tutari: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # Veritabanı hesaplar (GENERATED ALWAYS); ORM asla yazmaz
    riskteki_para: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), Computed("ROUND((1 - p_yenileme) * yenileme_tutari, 2)", persisted=True))
    hesaplanma_zamani: Mapped[datetime] = _olusturma_zamani()


class IsletmeGideri(Base):
    """Aylık sabit gider (0003). ay = ayın ilk günü; (isletme_id, ay, kategori) tekil."""
    __tablename__ = "isletme_giderleri"
    __table_args__ = (UniqueConstraint("isletme_id", "ay", "kategori"),)

    gider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=_UUID_VARSAYILAN)
    isletme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("isletmeler.isletme_id"), server_default=_KIRACI_VARSAYILAN)
    ay: Mapped[date] = mapped_column(Date)
    kategori: Mapped[str] = mapped_column(Text)
    tutar: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    aciklama: Mapped[str | None] = mapped_column(Text)
    olusturma_zamani: Mapped[datetime] = _olusturma_zamani()
    guncelleme_zamani: Mapped[datetime] = _guncelleme_zamani()
