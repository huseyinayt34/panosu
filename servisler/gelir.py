"""Gelir tanıma kuralları (Adım 7, Bölüm 3). Veritabanı bilmez; yalnızca Decimal.

İki görünüm:
  Kasaya giren (nakit): paket ücreti baslangic_tarihi gününde tamamen girer (VARSAYIM: ödeme başlangıçta yapılır;
    gerçek tahsilat verisi gelirse değişecek). Ziyaretlerin toplam_tutar'ı ziyaret gününde girer.
  Gerçek gelir (hak edilen):
    - Süre bazlı: ücret [baslangic_tarihi, bitis_tarihi) günlerine eşit dağıtılır.
    - Giriş bazlı: kullanılan her giriş için ücret / giris_hakki, o ziyaretin gününde. Son kullanma tarihi geçtiyse
      (bitis_tarihi < bugün) kullanılmayan hakların karşılığı bitis_tarihi gününde tanınır (proje sahibi kararı,
      2026-10-01). Son kullanmasız pakette kullanılmayan haklar hak edilmemiş kalır.
    - Ziyaretlerin toplam_tutar'ı ziyaret gününde (paketten bağımsız ek satış).
    - İptal edilen pakette iptal gününden SONRAsı hak edilmez (iptal tarihi = guncelleme_zamani'nın günü; VARSAYIM).
      İade modellenmez.
Yuvarlama: her pay kuruşa AŞAĞI yuvarlanır, fark son paya eklenir; böylece paylar negatif olmaz ve
toplam = tutar, tam olarak.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal

KURUS = Decimal("0.01")
SIFIR = Decimal("0.00")


def paylastir(tutar: Decimal, adet: int) -> list[Decimal]:
    """tutar'ı adet eşit paya böler; her pay kuruşa aşağı yuvarlanır, fark son paya eklenir. Σ = tutar."""
    if adet <= 0:
        raise ValueError("Pay sayısı pozitif olmalı")
    pay = (Decimal(tutar) / adet).quantize(KURUS, rounding=ROUND_DOWN)
    return [pay] * (adet - 1) + [Decimal(tutar) - pay * (adet - 1)]


@dataclass(frozen=True)
class PaketGeliri:
    tur: str                                  # 'sure' | 'giris'
    baslangic: date
    bitis: date | None
    giris_hakki: int | None
    ucret: Decimal
    iptal_tarihi: date | None = None          # yalnız durum 'iptal' ise
    kullanim_gunleri: tuple[date, ...] = field(default_factory=tuple)   # giriş: dönem içindeki tamamlanmış ziyaretler


def kasaya_giren(paket: PaketGeliri) -> dict[date, Decimal]:
    return {paket.baslangic: Decimal(paket.ucret)}


def hak_edilen(paket: PaketGeliri, bugun: date) -> dict[date, Decimal]:
    """Paketin gün bazında hak edilen geliri. Süre bazlıda gelecek günlerin payları da döner (çağıran süzer)."""
    iptal = paket.iptal_tarihi
    gelir: dict[date, Decimal] = defaultdict(lambda: SIFIR)
    if paket.tur == "sure":
        gun_sayisi = (paket.bitis - paket.baslangic).days
        for i, pay in enumerate(paylastir(paket.ucret, gun_sayisi)):
            gun = paket.baslangic + timedelta(days=i)
            if iptal is None or gun <= iptal:
                gelir[gun] += pay
        return dict(gelir)

    paylar = paylastir(paket.ucret, paket.giris_hakki)
    kullanimlar = sorted(paket.kullanim_gunleri)[: paket.giris_hakki]
    taninan = 0
    for gun, pay in zip(kullanimlar, paylar):
        if iptal is not None and gun > iptal:
            break
        gelir[gun] += pay
        taninan += 1
    suresi_doldu = paket.bitis is not None and paket.bitis < bugun and (iptal is None or iptal >= paket.bitis)
    if suresi_doldu and taninan < paket.giris_hakki:
        gelir[paket.bitis] += sum(paylar[taninan:], SIFIR)              # kullanılmayan hak geliri
    return dict(gelir)


def ziyaret_geliri(ziyaretler: Iterable[tuple[date, Decimal]]) -> dict[date, Decimal]:
    """Ziyaret tutarları gününde girer ve hak edilir (iki görünümde de aynı)."""
    gelir: dict[date, Decimal] = defaultdict(lambda: SIFIR)
    for gun, tutar in ziyaretler:
        gelir[gun] += Decimal(tutar)
    return dict(gelir)


def paket_aktif_mi(paket: PaketGeliri, gun: date) -> bool:
    """Paket o gün üyeyi kapsıyor mu (aktif üye sayımı için; geçmiş günlerde bugünkü durum sütununa bakılmaz)."""
    if gun < paket.baslangic or (paket.iptal_tarihi is not None and gun > paket.iptal_tarihi):
        return False
    if paket.tur == "sure":
        return gun < paket.bitis
    if paket.bitis is not None and gun > paket.bitis:
        return False
    onceki_kullanim = sum(1 for k in paket.kullanim_gunleri if k < gun)
    return onceki_kullanim < paket.giris_hakki
