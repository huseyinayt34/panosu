"""Komut: python -m sentetik.demo_kullanici --veritabani panosu_demo

demo@panosu.local kullanıcısını [DEMO] Denge Pilates ve [DEMO] Butik Reformer'a SAHİP olarak bağlar (Adım 9 canlı
demosu için). Parola PANOSU_DEMO_PAROLA ortam değişkeninden veya getpass ile alınır; hiçbir çıktıya yazılmaz.
Tekrar çalıştırmak idempotenttir: parola güncellenir, kilit ve hatalı deneme sayacı sıfırlanır, üyelikler 'sahip' olur.

Kilit yükleyicininkiyle aynıdır: yalnızca adı "_demo" ile biten veritabanı; ad doğrulanmadan bağlantı kurulmaz.
  * YÖNETİCİ bağlantısı (yükleyicideki demo sahibi kalıbı): kullanıcı ve parola özeti (parola özetleri tablosuna
    panosu_app doğrudan erişemez).
  * UYGULAMA bağlantısı (panosu_app, RLS): üyelikler, her işletmenin kendi kiracı bağlamında.
"""

import argparse
import getpass
import os
import uuid

from sqlalchemy import create_engine, text

from sentetik.butik_reformer import ISLETME_ADI as BUTIK_ADI
from sentetik.paket_uretici import STUDYO_ADI as DENGE_ADI
from sentetik.yukleyici import DemoDisiVeritabani, baglanti_adresleri
from servisler.kimlik import parola_kurali_hatasi, parola_ozetle

DEMO_EPOSTA = "demo@panosu.local"
DEMO_AD = "Demo Stüdyo Sahibi"
DEMO_ISLETMELERI = (DENGE_ADI, BUTIK_ADI)


def demo_kullanici_kur(veritabani: str, parola: str, ilerleme=print) -> uuid.UUID:
    yonetici_url, uygulama_url = baglanti_adresleri(veritabani)     # ad doğrulanmadan bağlantı yok
    hata = parola_kurali_hatasi(parola, DEMO_EPOSTA)
    if hata:
        raise ValueError(hata)
    yonetici, uygulama = create_engine(yonetici_url), create_engine(uygulama_url)
    try:
        with yonetici.begin() as con:
            kullanici_id = con.execute(
                text("INSERT INTO kullanicilar (eposta, ad_soyad) VALUES (:e, :a) "
                     "ON CONFLICT (eposta) DO UPDATE SET ad_soyad = EXCLUDED.ad_soyad RETURNING kullanici_id"),
                {"e": DEMO_EPOSTA, "a": DEMO_AD},
            ).scalar_one()
            con.execute(
                text("INSERT INTO kullanici_kimlik_bilgileri (kullanici_id, parola_ozeti) VALUES (:k, :o) "
                     "ON CONFLICT (kullanici_id) DO UPDATE SET parola_ozeti = EXCLUDED.parola_ozeti, "
                     "parola_degisme_zamani = now(), basarisiz_giris = 0, kilit_bitis = NULL"),
                {"k": kullanici_id, "o": parola_ozetle(parola)},
            )
            isletmeler = dict(con.execute(text("SELECT ad, isletme_id FROM isletmeler WHERE ad = ANY(:a)"),
                                          {"a": list(DEMO_ISLETMELERI)}).all())
        eksik = [ad for ad in DEMO_ISLETMELERI if ad not in isletmeler]
        if eksik:
            raise RuntimeError(f"Demo işletmeleri bulunamadı: {eksik}")
        for ad in DEMO_ISLETMELERI:
            with uygulama.begin() as con:                 # her işletme kendi kiracı bağlamında
                con.execute(text("SELECT set_config('app.isletme_id', :i, true), set_config('app.kullanici_id', :k, true)"),
                            {"i": str(isletmeler[ad]), "k": str(kullanici_id)})
                con.execute(text("INSERT INTO uyelikler (isletme_id, kullanici_id, rol) VALUES (aktif_isletme(), :k, 'sahip') "
                                 "ON CONFLICT (isletme_id, kullanici_id) DO UPDATE SET rol = 'sahip'"),
                            {"k": kullanici_id})
            ilerleme(f"  {ad}: sahip")
        ilerleme(f"Demo kullanıcı hazır: {DEMO_EPOSTA} ({kullanici_id})")
        return kullanici_id
    finally:
        yonetici.dispose()
        uygulama.dispose()


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(prog="python -m sentetik.demo_kullanici", description="Demo giriş kullanıcısı")
    a.add_argument("--veritabani", required=True, help="hedef veritabanı; '_demo' ile bitmeli")
    arg = a.parse_args(argv)
    try:
        baglanti_adresleri(arg.veritabani)             # kilit: parola sorulmadan önce
    except DemoDisiVeritabani as hata:
        raise SystemExit(f"HATA: {hata}")
    parola = os.environ.get("PANOSU_DEMO_PAROLA") or getpass.getpass(f"{DEMO_EPOSTA} parolası: ")
    try:
        demo_kullanici_kur(arg.veritabani, parola)
    except ValueError as hata:
        raise SystemExit(f"HATA: {hata}")


if __name__ == "__main__":
    main()
