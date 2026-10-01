"""[DEMO] stüdyo için S6 kalıbında üyelik paketleri üretir ve yükler (Adım 5b, Bölüm 5).

    python -m sentetik.paket_uretici --veritabani panosu_demo

Mevcut demo verisi silinmez; yalnızca paket eklenir. Paketler üyenin VAR OLAN ziyaretlerinden türetilir:
  - Her üyeye S6 karışımından bir tür atanır (1 Aylık %45, 3 Aylık %25, 6 Aylık %15, 12 Giriş %15; aynı tür yenilenir).
  - İlk paket ilk ziyaret gününde başlar. Süre bazlı paket 30/90/180 gün sonra biter; giriş paketi 12. girişte
    (ya da 60 günlük son kullanmada) biter.
  - Paket bittikten sonra üyenin bir ziyareti daha varsa yenilemiştir: yeni paket o ziyaret gününde başlar.
  - Zincirdeki son paket, bitişi bugün veya sonrasındaysa (giriş: hakkı kalmış ve son kullanması geçmemişse) 'aktif'tir.
Kilit yükleyicininkiyle aynıdır: yalnızca adı "_demo" ile biten veritabanı; ad doğrulanmadan bağlantı kurulmaz.
Yazma panosu_app rolüyle, işletmenin kiracı bağlamında (RLS altında) yapılır.
"""

import argparse
import uuid
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


class DemoPaketiZatenVar(RuntimeError):
    pass


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
        return len(satirlar)
    finally:
        yonetici.dispose()
        uygulama.dispose()


def main() -> None:
    a = argparse.ArgumentParser(prog="python -m sentetik.paket_uretici", description="Demo stüdyoya paket yükle")
    a.add_argument("--veritabani", required=True, help="hedef veritabanı; '_demo' ile bitmeli")
    a.add_argument("--tohum", type=int, default=42)
    arg = a.parse_args()
    try:
        paketleri_yukle(arg.veritabani, arg.tohum)
    except (DemoDisiVeritabani, DemoPaketiZatenVar) as hata:
        raise SystemExit(f"HATA: {hata}")


if __name__ == "__main__":
    main()
