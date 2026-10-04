"""Web paneli riskli ve sessiz üye tabloları + "neden riskli" açıklaması (Adım 9b, K4–K9 `docs/adim-9-tasarim.md`).
FastAPI'ye bağımlı değildir.

Listeler `yenileme_servisi`'nin panel sorgularından gelir (sıralama: riskteki para azalan). Açıklama için gereken ek
veri yalnızca gösterilecek satırlar için toplu sorgularla okunur; sorgularda elle isletme_id filtresi yoktur (RLS süzer).
Açıklamadaki sayılar riskin hesaplama_tarihi itibarıyladır (K8): ziyaretler yenileme_hesapla ile aynı kesimle
(işletmenin yerel günüyle ≤ hesaplama_tarihi) sayılır; kalan gün / giriş de risk kaydındaki değerdir.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analitik.aciklama import DUSUK_RISK_ESIGI, SESSIZ_ESIK, neden_riskli
from models import Isletme, MusteriPaketi, YenilemeRiski, Ziyaret
from servisler.finans_servisi import PANEL_UFUK_GUN
from servisler.yenileme_servisi import _gozlem_sonu, isletme_bugun, sessiz_uyeler, yenileme_paneli

TABLO_SATIRI = 10


@dataclass
class RiskListesi:
    bugun: date
    toplam_riskteki_para: Decimal
    sayi: int                       # riskli: paket sayısı; sessiz: üye sayısı
    satir_sayisi: int               # tüm listedeki satır (paket) sayısı; "Tümünü göster" kararı için
    ogeler: list[dict]              # her öğede ek "aciklama" (Aciklama | None) ve "son_ziyaret_gunu" (yerel date | None)
    en_eski_hesaplama: date | None
    eskimis: bool                   # en_eski_hesaplama < bugun
    tumu: bool                      # ogeler tüm liste mi
    # Tüm liste üzerinden, P(yenileme) DUSUK_RISK_ESIGI'nin altı (riskli) / üstü (düşük risk) (K5 eki)
    riskli_sayisi: int
    riskli_toplam: Decimal
    dusuk_sayisi: int
    dusuk_toplam: Decimal


@dataclass(frozen=True)
class _ZiyaretOzeti:
    sayi: int
    ilk: date
    son: date


def _ziyaret_ozetleri(db: Session, dilim: str, hesaplama_tarihi: date,
                      musteri_idler: set[uuid.UUID]) -> dict[uuid.UUID, _ZiyaretOzeti]:
    """Hesaplama gününe kadarki (yerel gün ≤ hesaplama_tarihi) tamamlanmış ziyaretler: sayı, ilk ve son yerel gün."""
    yerel_gun = func.date(func.timezone(dilim, Ziyaret.ziyaret_zamani))
    satirlar = db.execute(
        select(Ziyaret.musteri_id, func.count(), func.min(yerel_gun), func.max(yerel_gun))
        .where(Ziyaret.durum == "tamamlandi", Ziyaret.ziyaret_zamani < _gozlem_sonu(db, hesaplama_tarihi),
               Ziyaret.musteri_id.in_(musteri_idler))
        .group_by(Ziyaret.musteri_id)
    )
    return {m: _ZiyaretOzeti(sayi, ilk, son) for m, sayi, ilk, son in satirlar}


def _aciklamalari_ekle(db: Session, ogeler: list[dict], model_eslesmesi: bool) -> None:
    """Her öğeye "aciklama" ve "son_ziyaret_gunu" ekler. model_eslesmesi: risk kaydı (paket, tarih, model) ile
    eşleştirilir (riskli); değilse (paket, tarih)'in en son hesaplanan kaydı alınır (v_sessiz_uyeler ile aynı seçim)."""
    if not ogeler:
        return
    dilim = db.scalar(select(Isletme.saat_dilimi).where(Isletme.isletme_id == func.aktif_isletme()))
    yerel = ZoneInfo(dilim)
    paket_idler = {o["paket_id"] for o in ogeler}
    tarihler = {o["hesaplama_tarihi"] for o in ogeler}

    baslangic = dict(db.execute(select(MusteriPaketi.paket_id, MusteriPaketi.baslangic_tarihi)
                                .where(MusteriPaketi.paket_id.in_(paket_idler))).all())
    riskler: dict[tuple, YenilemeRiski] = {}
    for r in db.scalars(select(YenilemeRiski)
                        .where(YenilemeRiski.paket_id.in_(paket_idler), YenilemeRiski.hesaplama_tarihi.in_(tarihler))
                        .order_by(YenilemeRiski.hesaplanma_zamani)):
        anahtar = (r.paket_id, r.hesaplama_tarihi) + ((r.model_versiyonu,) if model_eslesmesi else ())
        riskler[anahtar] = r                                  # artan sırada: en son hesaplanan kazanır
    ozetler = {t: _ziyaret_ozetleri(db, dilim, t, {o["musteri_id"] for o in ogeler if o["hesaplama_tarihi"] == t})
               for t in tarihler}

    for o in ogeler:
        o["son_ziyaret_gunu"] = o["son_ziyaret"].astimezone(yerel).date() if o["son_ziyaret"] else None
        anahtar = (o["paket_id"], o["hesaplama_tarihi"]) + ((o["model_versiyonu"],) if model_eslesmesi else ())
        r = riskler.get(anahtar)
        if r is None or r.p_hayatta_simdi is None:
            o["aciklama"] = None
            continue
        oz = ozetler[o["hesaplama_tarihi"]].get(o["musteri_id"])
        o["aciklama"] = neden_riskli(
            p_hayatta_simdi=r.p_hayatta_simdi, p_yenileme=r.p_yenileme, ziyaret_sayisi=oz.sayi if oz else 0,
            ilk_ziyaret=oz.ilk if oz else None, son_ziyaret=oz.son if oz else None,
            hesaplama_tarihi=o["hesaplama_tarihi"], paket_baslangic=baslangic[o["paket_id"]], tur=o["tur"],
            kalan_gun=r.kalan_gun, kalan_giris=r.kalan_giris,
        )


def _liste(db: Session, bugun: date, tum_ogeler: list[dict], toplam: Decimal, sayi: int, tumu: bool,
           model_eslesmesi: bool, yalniz_riskli: bool = False) -> RiskListesi:
    """tumu=False: ilk TABLO_SATIRI satır; yalniz_riskli ise önce P(yenileme) ≥ eşik satırlar çıkarılır."""
    riskliler = [o for o in tum_ogeler if o["p_yenileme"] < DUSUK_RISK_ESIGI]
    dusukler = [o for o in tum_ogeler if o["p_yenileme"] >= DUSUK_RISK_ESIGI]
    if tumu:
        ogeler = tum_ogeler
    else:
        ogeler = (riskliler if yalniz_riskli else tum_ogeler)[:TABLO_SATIRI]
    _aciklamalari_ekle(db, ogeler, model_eslesmesi)
    en_eski = min((o["hesaplama_tarihi"] for o in tum_ogeler), default=None)
    return RiskListesi(bugun=bugun, toplam_riskteki_para=toplam, sayi=sayi, satir_sayisi=len(tum_ogeler),
                       ogeler=ogeler, en_eski_hesaplama=en_eski, eskimis=en_eski is not None and en_eski < bugun,
                       tumu=tumu, riskli_sayisi=len(riskliler),
                       riskli_toplam=sum((o["riskteki_para"] for o in riskliler), Decimal("0.00")),
                       dusuk_sayisi=len(dusukler),
                       dusuk_toplam=sum((o["riskteki_para"] for o in dusukler), Decimal("0.00")))


def riskli_uyeler(db: Session, tumu: bool = False) -> RiskListesi:
    """Önümüzdeki PANEL_UFUK_GUN günde biten aktif paketler (riskteki para azalan). Varsayılan görünüm yalnızca
    P(yenileme) < DUSUK_RISK_ESIGI satırları içerir; tumu=True düşük riskliler dahil hepsini aynı sırayla verir."""
    panel = yenileme_paneli(db, PANEL_UFUK_GUN)
    return _liste(db, panel.bugun, panel.ogeler, panel.toplam_riskteki_para, panel.paket_sayisi, tumu,
                  model_eslesmesi=True, yalniz_riskli=True)


def sessiz_uye_listesi(db: Session, tumu: bool = False) -> RiskListesi:
    """Aktif paketi olup P(aktif şimdi) < SESSIZ_ESIK olan üyeler (riskteki para azalan)."""
    s = sessiz_uyeler(db, SESSIZ_ESIK)
    return _liste(db, isletme_bugun(db), s.ogeler, s.toplam_riskteki_para, s.uye_sayisi, tumu,
                  model_eslesmesi=False)
