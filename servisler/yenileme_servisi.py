"""Yenileme riski servisi (Adım 5b). FastAPI'ye bağımlı değildir.

Kiracı bağlamlı bir oturumla (RLS) işletmenin tamamlanmış ziyaretlerini ve aktif paketlerini okur, M3 (MBG/NBD)
parametrelerini işletmenin tüm ziyaret geçmişiyle tahmin eder, her aktif paket için P(yenileme)'yi simüle eder ve
`yenileme_riskleri`'ne yazar. Aynı gün + model için yeniden çalıştırma idempotenttir (ON CONFLICT ... DO UPDATE).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from analitik import mbgnbd
from analitik.ozellikler import ozellik_cikar
from analitik.yenileme import MODEL_VERSIYONU, tohum_turet, yenileme_olasiligi
from models import Isletme, MusteriPaketi, YenilemeRiski, Ziyaret
from servisler.paket_servisi import kalan_giris

_GUN_SANIYE = 86_400.0
_DORT_HANE = Decimal("0.0001")


class YetersizVeri(Exception):
    """Model tahmini için işletmede yeterli ziyaret geçmişi yok."""


def isletme_bugun(db: Session) -> date:
    dilim = db.scalar(select(Isletme.saat_dilimi).where(Isletme.isletme_id == func.aktif_isletme()))
    return datetime.now(ZoneInfo(dilim)).date()


def _gozlem_sonu(db: Session, hesaplama_tarihi: date) -> datetime:
    """Hesaplama gününün sonu (işletmenin yerel gece yarısı); bu ana kadarki ziyaretler kullanılır."""
    dilim = db.scalar(select(Isletme.saat_dilimi).where(Isletme.isletme_id == func.aktif_isletme()))
    return datetime.combine(hesaplama_tarihi + timedelta(days=1), time(0), tzinfo=ZoneInfo(dilim))


def _olasilik(deger: float) -> Decimal:
    return Decimal(repr(deger)).quantize(_DORT_HANE, rounding=ROUND_HALF_UP)


def yenileme_hesapla(db: Session, hesaplama_tarihi: date | None = None) -> int:
    """Aktif paketlerin yenileme riskini hesaplayıp yazar; yazılan (eklenen/güncellenen) satır sayısını döndürür."""
    hesaplama_tarihi = hesaplama_tarihi or isletme_bugun(db)
    son = _gozlem_sonu(db, hesaplama_tarihi)

    ziyaretler: dict[uuid.UUID, list[float]] = defaultdict(list)
    for musteri_id, zaman in db.execute(
        select(Ziyaret.musteri_id, Ziyaret.ziyaret_zamani)
        .where(Ziyaret.durum == "tamamlandi", Ziyaret.ziyaret_zamani < son)
    ):
        ziyaretler[musteri_id].append((zaman - son).total_seconds() / _GUN_SANIYE)   # gün; gözlem sonu = 0
    if not ziyaretler:
        raise YetersizVeri("İşletmede tamamlanmış ziyaret yok")

    musteriler = list(ziyaretler)
    zamanlar = [np.array(ziyaretler[m]) for m in musteriler]
    oz = ozellik_cikar(zamanlar, zamanlar, 0.0)
    prm = mbgnbd.fit(oz.x, oz.t_x, oz.T)
    sira = {m: i for i, m in enumerate(musteriler)}

    paketler = db.scalars(select(MusteriPaketi).where(MusteriPaketi.durum == "aktif")).all()
    satirlar = []
    for paket in paketler:
        if paket.musteri_id in sira:
            i = sira[paket.musteri_id]
            x, t_x, T = oz.x[i], oz.t_x[i], oz.T[i]
        else:                                            # paketi var ama hiç gelmemiş: edinim = paket başlangıcı
            x, t_x, T = 0.0, 0.0, max((hesaplama_tarihi - paket.baslangic_tarihi).days + 1, 1)
        kalan_gun = (paket.bitis_tarihi - hesaplama_tarihi).days if paket.bitis_tarihi else None
        kalan = kalan_giris(db, paket)
        sonuc = yenileme_olasiligi(prm, x, t_x, T, pencere_gun=kalan_gun, kalan_hak=kalan,
                                   tohum=tohum_turet(paket.paket_id, hesaplama_tarihi))
        satirlar.append({
            "musteri_id": paket.musteri_id,
            "paket_id": paket.paket_id,
            "hesaplama_tarihi": hesaplama_tarihi,
            "model_versiyonu": MODEL_VERSIYONU,
            "kalan_gun": kalan_gun if paket.tur == "sure" else None,
            "kalan_giris": kalan,
            "p_hayatta_simdi": _olasilik(sonuc.p_hayatta_simdi),
            "p_yenileme": _olasilik(sonuc.p_yenileme),
            "yenileme_tutari": paket.ucret,
        })
    if not satirlar:
        return 0

    tablo = YenilemeRiski.__table__
    ifade = insert(tablo).values(satirlar)              # isletme_id: DB varsayılanı aktif_isletme()
    ifade = ifade.on_conflict_do_update(
        index_elements=[tablo.c.isletme_id, tablo.c.paket_id, tablo.c.hesaplama_tarihi, tablo.c.model_versiyonu],
        set_={ad: ifade.excluded[ad] for ad in ("musteri_id", "kalan_gun", "kalan_giris", "p_hayatta_simdi",
                                                "p_yenileme", "yenileme_tutari")}
             | {"hesaplanma_zamani": func.now()},
    )
    db.execute(ifade)
    db.commit()
    return len(satirlar)


# ---------------------------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------------------------
@dataclass
class YenilemePaneli:
    bugun: date
    gun: int
    toplam_riskteki_para: Decimal
    paket_sayisi: int
    ogeler: list[dict]


_PANEL_SUTUNLARI = (
    "paket_id, musteri_id, ad_soyad, telefon_e164, whatsapp_izni_var, son_ziyaret, paket_adi, tur, bitis_tarihi, "
    "kalan_gun, kalan_giris, p_yenileme, yenileme_tutari, riskteki_para, hesaplama_tarihi, model_versiyonu"
)


def yenileme_paneli(db: Session, gun: int) -> YenilemePaneli:
    """Bitişi önümüzdeki `gun` gün içinde (bugün dahil) olan aktif paketler, riskteki_para azalan.

    Bitiş tarihi olmayan (son kullanmasız giriş) paketler tarih penceresine giremediği için listede yoktur.
    """
    bugun = isletme_bugun(db)
    ogeler = [dict(s) for s in db.execute(
        text(f"SELECT {_PANEL_SUTUNLARI} FROM v_yenileme_paneli "
             "WHERE bitis_tarihi BETWEEN :bugun AND :son ORDER BY riskteki_para DESC, bitis_tarihi, paket_id"),
        {"bugun": bugun, "son": bugun + timedelta(days=gun)},
    ).mappings()]
    toplam = sum((o["riskteki_para"] for o in ogeler), Decimal("0.00"))
    return YenilemePaneli(bugun=bugun, gun=gun, toplam_riskteki_para=toplam, paket_sayisi=len(ogeler), ogeler=ogeler)
