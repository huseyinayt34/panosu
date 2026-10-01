"""[DEMO] stüdyo için S6 kalıbında üyelik paketleri üretir ve yükler (Adım 5b, Bölüm 5).

    python -m sentetik.paket_uretici --veritabani panosu_demo

Mevcut demo verisi silinmez; yalnızca paket eklenir. Paketler üyenin VAR OLAN ziyaretlerinden türetilir:
  - Her üyeye S6 karışımından bir tür atanır (1 Aylık %45, 3 Aylık %25, 6 Aylık %15, 12 Giriş %15; aynı tür yenilenir).
  - İlk paket ilk ziyaret gününde başlar. Süre bazlı paket 30/90/180 gün sonra biter; giriş paketi 12. girişte
    (ya da 60 günlük son kullanmada) biter.
  - Paket bittikten sonra üyenin bir ziyareti daha varsa yenilemiştir: yeni paket o ziyaret gününde başlar.
  - Zincirdeki son paket, bitişi bugün veya sonrasındaysa (giriş: hakkı kalmış ve son kullanması geçmemişse) 'aktif'tir.
Çift sayım kuralı (Adım 7): paketli işletmede giriş ziyaretlerinin toplam_tutar'ı 0'dır. Paket dönemine düşen
(süre: [başlangıç, bitiş), giriş: [başlangıç, son kullanma]) ziyaretlerin tutarı 0 yapılır; kalem dökümü tutarlı kalsın
diye kalemlerde indirim tam tutara eşitlenir ("paket kapsamında"). Paket yüklemesinin sonunda otomatik çalışır;
--cift-sayim ile tek başına da çalıştırılabilir. --giderler AY ile ayın demo giderleri eklenir (yoksa);
--gecmis-giderler ile max(ilk tamamlanmış ziyaretin ayı, DEMO_GIDER_BASLANGIC)'tan bugünün ayına kadar gideri olmayan her
aya eklenir; --guncelle ile ayrıca mevcut demo gideri satırlarının tutarı DEMO_GIDERLERI'ne çekilir ve DEMO_GIDER_BASLANGIC'tan
önceki demo gideri satırları silinir (elle girilmiş giderlere dokunulmaz).

Kilit yükleyicininkiyle aynıdır: yalnızca adı "_demo" ile biten veritabanı; ad doğrulanmadan bağlantı kurulmaz.
Yazma panosu_app rolüyle, işletmenin kiracı bağlamında (RLS altında) yapılır.
"""

import argparse
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import create_engine, insert, text

from backtest.senaryolar import S6_GIRIS_SON_KULLANMA, S6_PAKETLER
from models import MusteriPaketi
from sentetik.uretici import KAYNAK_ETIKETI
from sentetik.yukleyici import DemoDisiVeritabani, _demo_sahibi, baglanti_adresleri

STUDYO_ADI = "[DEMO] Denge Pilates Stüdyosu"
SAAT_DILIMI = ZoneInfo("Europe/Istanbul")


# Demo giderleri (HİPOTEZ, Adım 7): kategori → TL. ~218 aktif üyeli stüdyo; Eylül 2026 geliri 415.892 TL ile kâr oranı
# ≈ %20.6 (proje sahibi kararı 2026-10-01), Butik Reformer'ın %10–25 hedefiyle tutarlı.
DEMO_GIDERLERI = {"kira": Decimal("90000.00"), "personel": Decimal("200000.00"), "faturalar": Decimal("25000.00"),
                  "diger": Decimal("15000.00")}
DEMO_GIDER_ACIKLAMASI = "Demo gideri (HİPOTEZ)"
# Demo hikâyesinde stüdyo Panosu'yu Mart 2026'da kullanmaya başladı ve giderlerini o aydan itibaren girdi; daha eski
# aylarda panel 'gider girilmedi' gösterir. Sabit 330.000 TL gider, sentetik verinin büyüme döneminde
# (2024-10 – 2026-02) gerçekçi değil (proje sahibi kararı 2026-10-01).
DEMO_GIDER_BASLANGIC = date(2026, 3, 1)


class DemoPaketiZatenVar(RuntimeError):
    pass


def paket_doneminde_mi(gun: date, paketler: list[tuple[str, date, date | None]]) -> bool:
    """Ziyaret günü üyenin bir paket dönemine düşüyor mu: süre [başlangıç, bitiş), giriş [başlangıç, son kullanma]."""
    for tur, baslangic, bitis in paketler:
        if gun < baslangic:
            continue
        if tur == "sure" and gun < bitis:
            return True
        if tur == "giris" and (bitis is None or gun <= bitis):
            return True
    return False


@contextmanager
def _studyo_islemi(veritabani: str) -> Iterator:
    """Stüdyonun kiracı bağlamında tek işlem (panosu_app, RLS). Ad doğrulanmadan bağlantı kurulmaz."""
    yonetici_url, uygulama_url = baglanti_adresleri(veritabani)
    yonetici, uygulama = create_engine(yonetici_url), create_engine(uygulama_url)
    try:
        sahip = _demo_sahibi(yonetici)
        with yonetici.connect() as con:
            isletme_id = con.scalar(text("SELECT isletme_id FROM isletmeler WHERE ad = :a"), {"a": STUDYO_ADI})
        if isletme_id is None:
            raise RuntimeError(f"{STUDYO_ADI} bulunamadı; önce python -m sentetik ile demo verisini yükleyin.")
        with uygulama.begin() as con:
            con.execute(text("SELECT set_config('app.kullanici_id', :u, true), set_config('app.isletme_id', :i, true)"),
                        {"u": str(sahip), "i": str(isletme_id)})
            yield con
    finally:
        yonetici.dispose()
        uygulama.dispose()


def cift_sayimi_duzelt(veritabani: str, ilerleme=print) -> int:
    """Paket dönemine düşen ve tutarı 0 olmayan tamamlanmış ziyaretlerin tutarını 0 yapar; değişen satır sayısı."""
    with _studyo_islemi(veritabani) as con:
        paketler: dict[uuid.UUID, list] = {}
        for musteri_id, tur, bas, bit in con.execute(text(
                "SELECT musteri_id, tur, baslangic_tarihi, bitis_tarihi FROM musteri_paketleri")):
            paketler.setdefault(musteri_id, []).append((tur, bas, bit))
        idler = [zid for zid, musteri_id, gun in con.execute(text(
            "SELECT ziyaret_id, musteri_id, (ziyaret_zamani AT TIME ZONE 'Europe/Istanbul')::date FROM ziyaretler "
            "WHERE durum = 'tamamlandi' AND toplam_tutar <> 0"))
            if paket_doneminde_mi(gun, paketler.get(musteri_id, []))]
        if idler:
            con.execute(text("UPDATE ziyaret_kalemleri SET indirim_tutari = adet * birim_fiyat "
                             "WHERE ziyaret_id = ANY(:idler)"), {"idler": idler})
            con.execute(text("UPDATE ziyaretler SET toplam_tutar = 0 WHERE ziyaret_id = ANY(:idler)"), {"idler": idler})
    ilerleme(f"{STUDYO_ADI}: çift sayım düzeltmesi, {len(idler)} ziyaretin tutarı 0 yapıldı")
    return len(idler)


def demo_giderleri_ekle(veritabani: str, ay: date, ilerleme=print) -> bool:
    """Ay için hiç gider yoksa DEMO_GIDERLERI'ni ekler. Eklendiyse True."""
    with _studyo_islemi(veritabani) as con:
        if con.scalar(text("SELECT count(*) FROM isletme_giderleri WHERE ay = :ay"), {"ay": ay}):
            ilerleme(f"{STUDYO_ADI}: {ay:%Y-%m} için gider zaten var, eklenmedi")
            return False
        con.execute(text("INSERT INTO isletme_giderleri (ay, kategori, tutar, aciklama) "
                         "VALUES (:ay, :k, :t, 'Demo gideri (HİPOTEZ)')"),
                    [{"ay": ay, "k": k, "t": t} for k, t in DEMO_GIDERLERI.items()])
    ilerleme(f"{STUDYO_ADI}: {ay:%Y-%m} demo giderleri eklendi ({sum(DEMO_GIDERLERI.values())} TL)")
    return True


def ay_listesi(ilk: date, son: date) -> list[date]:
    """ilk'in ayından son'un ayına kadar (ikisi dahil) her ayın ilk günü."""
    aylar, ay = [], ilk.replace(day=1)
    while ay <= son:
        aylar.append(ay)
        ay = (ay + timedelta(days=32)).replace(day=1)
    return aylar


def gider_aylari(ilk_ziyaret: date, bugun: date) -> list[date]:
    """Demo gideri yüklenecek aylar: max(ilk ziyaret ayı, DEMO_GIDER_BASLANGIC)'tan bugünün ayına kadar."""
    return ay_listesi(max(ilk_ziyaret.replace(day=1), DEMO_GIDER_BASLANGIC), bugun)


def _eski_demo_giderlerini_sil(veritabani: str) -> int:
    """DEMO_GIDER_BASLANGIC'tan önceki demo gideri satırlarını siler; silinen ay sayısını döndürür.

    panosu_app'in iş verisini silme yetkisi bilinçli olarak yoktur; bu yüzden silme, yukleyici.temizle() gibi YÖNETİCİ
    bağlantısıyla yapılır. Yönetici RLS'ye tabi olmadığından isletme_id filtresi burada elle yazılır (Kural 3'ün
    temizle()'deki ile aynı istisnası). Ad doğrulanmadan bağlantı kurulmaz.
    """
    yonetici_url, _ = baglanti_adresleri(veritabani)
    yonetici = create_engine(yonetici_url)
    try:
        with yonetici.begin() as con:
            isletme_id = con.scalar(text("SELECT isletme_id FROM isletmeler WHERE ad = :a"), {"a": STUDYO_ADI})
            if isletme_id is None:
                raise RuntimeError(f"{STUDYO_ADI} bulunamadı; önce python -m sentetik ile demo verisini yükleyin.")
            aylar = set(con.scalars(text(
                "DELETE FROM isletme_giderleri WHERE isletme_id = :i AND ay < :bas AND aciklama = :a RETURNING ay"),
                {"i": isletme_id, "bas": DEMO_GIDER_BASLANGIC, "a": DEMO_GIDER_ACIKLAMASI}))
    finally:
        yonetici.dispose()
    return len(aylar)


def gecmis_giderleri_ekle(veritabani: str, bugun: date | None = None, ilerleme=print, guncelle: bool = False) -> int:
    """gider_aylari() aralığında gideri olmayan her aya DEMO_GIDERLERI'ni ekler (tek işlem, kiracı bağlamında).
    Eklenen ay sayısını döndürür; tekrar çalıştırılınca 0.

    guncelle=True ise önce DEMO_GIDER_BASLANGIC'tan önceki demo gideri satırları (yönetici bağlantısıyla, ayrı işlemde)
    silinir; sonra aralıktaki açıklaması DEMO_GIDER_ACIKLAMASI olan satırların tutarı kategori bazında DEMO_GIDERLERI'ne
    çekilir. Başka açıklamalı (elle girilmiş) giderlere dokunulmaz. İki işlem de idempotenttir."""
    bugun = bugun or datetime.now(SAAT_DILIMI).date()
    silinen = _eski_demo_giderlerini_sil(veritabani) if guncelle else 0
    with _studyo_islemi(veritabani) as con:
        ilk = con.scalar(text("SELECT min((ziyaret_zamani AT TIME ZONE 'Europe/Istanbul')::date) FROM ziyaretler "
                              "WHERE durum = 'tamamlandi'"))
        if ilk is None:
            ilerleme(f"{STUDYO_ADI}: tamamlanmış ziyaret yok, gider eklenmedi")
            return 0
        aylar = gider_aylari(ilk, bugun)
        guncellenen: set[date] = set()
        if guncelle:
            for k, t in DEMO_GIDERLERI.items():
                guncellenen.update(con.scalars(text(
                    "UPDATE isletme_giderleri SET tutar = :t WHERE kategori = :k AND aciklama = :a "
                    "AND ay BETWEEN :ilk AND :son AND tutar <> :t RETURNING ay"),
                    {"t": t, "k": k, "a": DEMO_GIDER_ACIKLAMASI, "ilk": aylar[0], "son": aylar[-1]}))
        dolu = set(con.scalars(text("SELECT DISTINCT ay FROM isletme_giderleri")))
        eksik = [ay for ay in aylar if ay not in dolu]
        if eksik:
            con.execute(text("INSERT INTO isletme_giderleri (ay, kategori, tutar, aciklama) VALUES (:ay, :k, :t, :a)"),
                        [{"ay": ay, "k": k, "t": t, "a": DEMO_GIDER_ACIKLAMASI}
                         for ay in eksik for k, t in DEMO_GIDERLERI.items()])
    aralik = f" ({eksik[0]:%Y-%m} – {eksik[-1]:%Y-%m})" if eksik else ""
    ilerleme(f"{STUDYO_ADI}: {len(eksik)} ay için demo giderleri eklendi{aralik}")
    if guncelle:
        ilerleme(f"{STUDYO_ADI}: {len(guncellenen)} ayın demo giderleri güncellendi "
                 f"(aylık {sum(DEMO_GIDERLERI.values())} TL)")
        ilerleme(f"{STUDYO_ADI}: {DEMO_GIDER_BASLANGIC:%Y-%m} öncesi {silinen} ayın demo giderleri silindi")
    return len(eksik)


def paket_zinciri(tarihler: list[date], tur_no: int, bugun: date) -> list[dict]:
    """Bir üyenin sıralı ziyaret günlerinden paket zinciri (onceki_paket_id bağlantısı çağıranda kurulur)."""
    ad, tur, _, sure, hak, fiyat = S6_PAKETLER[tur_no]
    son_kullanma = timedelta(days=int(S6_GIRIS_SON_KULLANMA))
    zincir, baslangic = [], tarihler[0]
    while True:
        donem = [t for t in tarihler if t >= baslangic]
        if tur == "sure":
            bitis = baslangic + timedelta(days=int(sure))
            etkin_bitis, kayit_bitis, aktif = bitis, bitis, bitis >= bugun
        else:
            kayit_bitis = baslangic + son_kullanma
            donem = [t for t in donem if t <= kayit_bitis]
            if len(donem) >= hak:
                etkin_bitis, aktif = donem[hak - 1], False
            else:
                etkin_bitis, aktif = kayit_bitis, kayit_bitis >= bugun
        zincir.append({"tur": tur, "ad": ad, "baslangic_tarihi": baslangic, "bitis_tarihi": kayit_bitis,
                       "giris_hakki": hak, "ucret": Decimal(fiyat), "durum": "aktif" if aktif else "bitti"})
        sonraki = [t for t in tarihler if t > etkin_bitis]
        if aktif or not sonraki:
            return zincir
        baslangic = sonraki[0]


def paketleri_yukle(veritabani: str, tohum: int = 42, bugun: date | None = None, ilerleme=print) -> int:
    """Stüdyonun üyeleri için paketleri yükler; yüklenen paket sayısını döndürür."""
    yonetici_url, uygulama_url = baglanti_adresleri(veritabani)     # ad doğrulanmadan bağlantı yok
    bugun = bugun or datetime.now(SAAT_DILIMI).date()
    yonetici, uygulama = create_engine(yonetici_url), create_engine(uygulama_url)
    try:
        sahip = _demo_sahibi(yonetici)
        with yonetici.connect() as con:
            isletme_id = con.scalar(text("SELECT isletme_id FROM isletmeler WHERE ad = :a"), {"a": STUDYO_ADI})
        if isletme_id is None:
            raise RuntimeError(f"{STUDYO_ADI} bulunamadı; önce python -m sentetik ile demo verisini yükleyin.")

        rng = np.random.default_rng(tohum)
        oranlar = np.array([pk[2] for pk in S6_PAKETLER])
        with uygulama.begin() as con:                    # tek işlem, kiracı bağlamında
            con.execute(text("SELECT set_config('app.kullanici_id', :u, true), set_config('app.isletme_id', :i, true)"),
                        {"u": str(sahip), "i": str(isletme_id)})
            if con.scalar(text("SELECT count(*) FROM musteri_paketleri")):
                raise DemoPaketiZatenVar(f"{STUDYO_ADI} için zaten paket var; yeniden yüklenmez.")
            ziyaretler: dict[uuid.UUID, list[date]] = {}
            for musteri_id, gun in con.execute(text(
                "SELECT musteri_id, (ziyaret_zamani AT TIME ZONE 'Europe/Istanbul')::date FROM ziyaretler "
                "WHERE durum = 'tamamlandi' ORDER BY musteri_id, ziyaret_zamani"
            )):
                ziyaretler.setdefault(musteri_id, []).append(gun)

            satirlar, no = [], 0
            for musteri_id in sorted(ziyaretler):
                onceki = None
                for paket in paket_zinciri(ziyaretler[musteri_id], int(rng.choice(len(S6_PAKETLER), p=oranlar)), bugun):
                    no += 1
                    paket_id = uuid.UUID(bytes=rng.bytes(16), version=4)
                    satirlar.append({**paket, "paket_id": paket_id, "musteri_id": musteri_id, "onceki_paket_id": onceki,
                                     "dis_kaynak": KAYNAK_ETIKETI, "dis_kimlik": f"P{no:06d}"})
                    onceki = paket_id
            con.execute(insert(MusteriPaketi.__table__), satirlar)   # isletme_id: DB varsayılanı aktif_isletme()
        aktif = sum(s["durum"] == "aktif" for s in satirlar)
        ilerleme(f"{STUDYO_ADI}: {len(satirlar)} paket ({aktif} aktif), {len(ziyaretler)} üye")
    finally:
        yonetici.dispose()
        uygulama.dispose()
    cift_sayimi_duzelt(veritabani, ilerleme)
    return len(satirlar)


def main() -> None:
    a = argparse.ArgumentParser(prog="python -m sentetik.paket_uretici", description="Demo stüdyoya paket yükle")
    a.add_argument("--veritabani", required=True, help="hedef veritabanı; '_demo' ile bitmeli")
    a.add_argument("--tohum", type=int, default=42)
    a.add_argument("--cift-sayim", action="store_true", help="yalnızca çift sayım düzeltmesini çalıştır")
    a.add_argument("--giderler", metavar="YYYY-AA", help="yalnızca bu ayın demo giderlerini ekle (yoksa)")
    a.add_argument("--gecmis-giderler", action="store_true",
                   help="max(ilk ziyaret ayı, DEMO_GIDER_BASLANGIC)'tan bugünün ayına kadar gideri olmayan her aya demo giderlerini ekle")
    a.add_argument("--guncelle", action="store_true",
                   help="--gecmis-giderler ile: demo giderlerini DEMO_GIDERLERI'ne güncelle, DEMO_GIDER_BASLANGIC öncesini sil")
    arg = a.parse_args()
    if arg.guncelle and not arg.gecmis_giderler:
        a.error("--guncelle yalnızca --gecmis-giderler ile kullanılır")
    try:
        if arg.cift_sayim:
            cift_sayimi_duzelt(arg.veritabani)
        elif arg.giderler:
            yil, ay = arg.giderler.split("-")
            demo_giderleri_ekle(arg.veritabani, date(int(yil), int(ay), 1))
        elif arg.gecmis_giderler:
            gecmis_giderleri_ekle(arg.veritabani, guncelle=arg.guncelle)
        else:
            paketleri_yukle(arg.veritabani, arg.tohum)
    except (DemoDisiVeritabani, DemoPaketiZatenVar) as hata:
        raise SystemExit(f"HATA: {hata}")


if __name__ == "__main__":
    main()
