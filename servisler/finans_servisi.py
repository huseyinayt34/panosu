"""Gelir ve kâr özeti (Adım 7, Bölüm 3). FastAPI'ye bağımlı değildir. Kiracı izolasyonu RLS ile.

Gelir kuralları `servisler/gelir.py`'dedir. Ay bitmemişse (proje sahibi kararı, 2026-10-01):
  - kasaya_giren ve gercek_gelir bugüne kadar;
  - kar_zarar = gercek_gelir − bugüne kadarki gider payları (= günlük net toplamı); gider_toplam tüm ayın gideri;
  - uye_basi_aylik_gelir = gercek_gelir × (ayın gün sayısı / geçen gün) / ortalama günlük aktif üye;
  - basabas_uye_sayisi = ⌈gider_toplam (tüm ay) / uye_basi_aylik_gelir⌉.
Ay bittiğinde bunların hepsi tasarım belgesindeki tanımlarla aynıdır.
"""

import calendar
import math
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Isletme, MusteriPaketi, Ziyaret
from servisler import gelir as g
from servisler.gider_servisi import aylik_gider
from servisler.yenileme_servisi import isletme_bugun, yenileme_paneli

PANEL_UFUK_GUN = 45


@dataclass
class GunlukFinans:
    tarih: date
    kasaya_giren: Decimal
    gercek_gelir: Decimal
    gider_payi: Decimal | None
    net: Decimal | None


@dataclass
class FinansOzeti:
    ay: date
    bugun: date
    kasaya_giren: Decimal
    gercek_gelir: Decimal
    gider_toplam: Decimal | None
    gider_bugune_kadar: Decimal | None
    kar_zarar: Decimal | None
    gider_girilmedi: bool
    gunluk: list[GunlukFinans]
    aktif_uye_sayisi: int
    ortalama_aktif_uye: Decimal | None
    uye_basi_aylik_gelir: Decimal | None
    basabas_uye_sayisi: int | None
    basabas_farki: int | None
    riskteki_para_45_gun: Decimal


def _yerel_gun(sutun):
    dilim = select(Isletme.saat_dilimi).where(Isletme.isletme_id == func.aktif_isletme()).scalar_subquery()
    return func.date(func.timezone(dilim, sutun))


def paket_gelirleri(db: Session) -> tuple[list[tuple[uuid.UUID, g.PaketGeliri]], list[tuple[date, Decimal]]]:
    """İşletmenin tüm paketleri (gelir girdisi olarak, sahibiyle) ve tamamlanmış ziyaretleri (gün, tutar)."""
    ziyaretler = db.execute(
        select(Ziyaret.musteri_id, _yerel_gun(Ziyaret.ziyaret_zamani), Ziyaret.toplam_tutar)
        .where(Ziyaret.durum == "tamamlandi")
    ).all()
    gunler: dict[uuid.UUID, list[date]] = defaultdict(list)
    for musteri_id, gun, _ in ziyaretler:
        gunler[musteri_id].append(gun)

    paketler = []
    for p, guncelleme_gunu in db.execute(select(MusteriPaketi, _yerel_gun(MusteriPaketi.guncelleme_zamani))):
        kullanim = ()
        if p.tur == "giris":
            kullanim = tuple(sorted(d for d in gunler.get(p.musteri_id, ())
                                    if d >= p.baslangic_tarihi and (p.bitis_tarihi is None or d <= p.bitis_tarihi)))
        paketler.append((p.musteri_id, g.PaketGeliri(
            tur=p.tur, baslangic=p.baslangic_tarihi, bitis=p.bitis_tarihi, giris_hakki=p.giris_hakki, ucret=p.ucret,
            iptal_tarihi=guncelleme_gunu if p.durum == "iptal" else None, kullanim_gunleri=kullanim,
        )))
    return paketler, [(gun, tutar) for _, gun, tutar in ziyaretler]


def basabas_uye_sayisi(gider_toplam: Decimal | None, uye_basi_aylik_gelir: Decimal | None) -> int | None:
    """⌈gider / üye başı aylık gelir⌉; gider veya gelir yoksa None."""
    if gider_toplam is None or not uye_basi_aylik_gelir:
        return None
    return math.ceil(Decimal(gider_toplam) / Decimal(uye_basi_aylik_gelir))


def finans_ozeti(db: Session, ay: date) -> FinansOzeti:
    bugun = isletme_bugun(db)
    ay_gun_sayisi = calendar.monthrange(ay.year, ay.month)[1]
    son_gun = min(ay + timedelta(days=ay_gun_sayisi - 1), bugun)
    gunler = [ay + timedelta(days=i) for i in range((son_gun - ay).days + 1)]       # gelecek günler yok

    paketler, ziyaretler = paket_gelirleri(db)
    kasa: dict[date, Decimal] = defaultdict(lambda: g.SIFIR)
    hak: dict[date, Decimal] = defaultdict(lambda: g.SIFIR)
    for gun, tutar in g.ziyaret_geliri(ziyaretler).items():     # ziyaret tutarı iki görünümde de gününde
        kasa[gun] += tutar
        hak[gun] += tutar
    for _, paket in paketler:
        for gun, tutar in g.kasaya_giren(paket).items():
            kasa[gun] += tutar
        for gun, tutar in g.hak_edilen(paket, bugun).items():
            hak[gun] += tutar

    gider = aylik_gider(db, ay)
    gider_toplam = gider.toplam
    gider_paylari = g.paylastir(gider_toplam, ay_gun_sayisi) if gider_toplam is not None else None

    gunluk = []
    for gun in gunler:
        pay = gider_paylari[gun.day - 1] if gider_paylari else None
        gunluk.append(GunlukFinans(tarih=gun, kasaya_giren=kasa[gun], gercek_gelir=hak[gun], gider_payi=pay,
                                   net=hak[gun] - pay if pay is not None else None))
    kasaya_giren = sum((x.kasaya_giren for x in gunluk), g.SIFIR)
    gercek_gelir = sum((x.gercek_gelir for x in gunluk), g.SIFIR)
    gider_bugune_kadar = sum((x.gider_payi for x in gunluk), g.SIFIR) if gider_paylari else None
    kar_zarar = gercek_gelir - gider_bugune_kadar if gider_bugune_kadar is not None else None

    def aktif_uyeler(gun: date) -> int:
        return len({m for m, p in paketler if g.paket_aktif_mi(p, gun)})

    ortalama_aktif = (Decimal(sum(aktif_uyeler(gun) for gun in gunler)) / len(gunler)) if gunler else None
    uye_basi = None
    if ortalama_aktif and gunler:
        uye_basi = (gercek_gelir * ay_gun_sayisi / len(gunler) / ortalama_aktif).quantize(g.KURUS, ROUND_HALF_UP)
    aktif_bugun = aktif_uyeler(bugun)
    basabas = basabas_uye_sayisi(gider_toplam, uye_basi)

    return FinansOzeti(
        ay=ay, bugun=bugun, kasaya_giren=kasaya_giren, gercek_gelir=gercek_gelir, gider_toplam=gider_toplam,
        gider_bugune_kadar=gider_bugune_kadar, kar_zarar=kar_zarar, gider_girilmedi=gider_toplam is None,
        gunluk=gunluk, aktif_uye_sayisi=aktif_bugun,
        ortalama_aktif_uye=ortalama_aktif.quantize(g.KURUS, ROUND_HALF_UP) if ortalama_aktif is not None else None,
        uye_basi_aylik_gelir=uye_basi, basabas_uye_sayisi=basabas,
        basabas_farki=aktif_bugun - basabas if basabas is not None else None,
        riskteki_para_45_gun=yenileme_paneli(db, PANEL_UFUK_GUN).toplam_riskteki_para,
    )
