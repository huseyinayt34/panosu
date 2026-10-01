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
--cift-sayim ile tek başına da çalıştırılabilir. --giderler AY ile ayın demo giderleri eklenir (yoksa).

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


# Demo giderleri (HİPOTEZ, Adım 7): kategori → TL
DEMO_GIDERLERI = {"kira": Decimal("45000.00"), "personel": Decimal("60000.00"), "faturalar": Decimal("8000.00"),
                  "diger": Decimal("5000.00")}


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
    arg = a.parse_args()
    try:
        if arg.cift_sayim:
            cift_sayimi_duzelt(arg.veritabani)
        elif arg.giderler:
            yil, ay = arg.giderler.split("-")
            demo_giderleri_ekle(arg.veritabani, date(int(yil), int(ay), 1))
        else:
            paketleri_yukle(arg.veritabani, arg.tohum)
    except (DemoDisiVeritabani, DemoPaketiZatenVar) as hata:
        raise SystemExit(f"HATA: {hata}")


if __name__ == "__main__":
    main()
