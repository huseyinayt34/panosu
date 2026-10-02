"""Komut: python -m sentetik.demo_kur --veritabani <ad>_demo [--uygulama-parolasi-ayarla]

Demo veritabanını tek komutta, yeniden üretilebilir biçimde kurar (Adım 11, K24; `docs/adim-11-tasarim.md`).
Üreticilerin mantığı değişmez; bu modül yalnızca onları yereldeki panosu_demo'yu oluşturan sırayla ve sabit
parametrelerle çağırır (reçete, 2026-10-01'de yüklenen panosu_demo'nun kimlikleriyle birebir doğrulandı):

  1. Temizlik: tüm [DEMO] işletmeler silinir (yukleyici.temizle).
  2. Sentetik işletmeler: `python -m sentetik` ile aynı; referans 2026-10-01, 400 müşteri, 730 gün, tohum 42,
     enflasyon 0, tüm sektörler (yukleyici.yukle). Gerçek değer CSV'si (veri/) yazılmaz; veritabanı durumunun parçası
     değildir.
  3. Denge Pilates paketleri: paket_uretici.paketleri_yukle (tohum 42, bugün 2026-10-01); sonunda çift sayım düzeltmesi.
  4. Denge Pilates giderleri: paket_uretici.gecmis_giderleri_ekle (bugün 2026-10-01 → 2026-03 … 2026-10).
  5. Butik Reformer: butik_reformer.uret() + yukle() (kendi sabitleri: tohum 2026, BUGUN 2026-10-01).
  6. Demo kullanıcısı: demo_kullanici.demo_kullanici_kur; parola YALNIZCA PANOSU_DEMO_PAROLA ortam değişkeninden
     (getpass yok: iş akışı etkileşimsizdir).
  7. Demo tazeleme: demo_tazele.tazele (bugüne kaydırma + yenileme riskleri).

--uygulama-parolasi-ayarla (yalnızca yayında, demo-kur.yml): uygulama adresindeki kullanıcı panosu_app olmalıdır;
yönetici bağlantısıyla ALTER ROLE panosu_app WITH LOGIN PASSWORD <adresteki parola> çalıştırılır (psycopg2.sql.Literal;
metin birleştirme yok). Parola hiçbir çıktıda veya hata mesajında görünmez; hata olursa yalnızca istisna türü yazılır.
Yerelde bu bayrak KULLANILMAZ.

Bağlantılar yukleyici.baglanti_adresleri ile (PANOSU_VERITABANI_URL / PANOSU_MIGRASYON_URL; .env ya da ortam
değişkeni); ad "_demo" ile bitmiyorsa bağlantı kurulmaz. Çıktı: adım adları, işletme adları, sayılar ve süreler.
"""

import argparse
import os
import time
from datetime import date

from psycopg2 import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from config import UYGULAMA_ROLU
from sentetik import butik_reformer, paket_uretici
from sentetik.demo_kullanici import DEMO_EPOSTA, demo_kullanici_kur
from sentetik.demo_tazele import tazele
from sentetik.katalog import PROFILLER
from sentetik.uretici import UretimAyarlari, uret
from sentetik.yukleyici import DemoDisiVeritabani, baglanti_adresleri, demo_veritabani_dogrula, temizle, yukle
from servisler.kimlik import parola_kurali_hatasi

REFERANS_GUNU = date(2026, 10, 1)
SENTETIK_AYARLARI = UretimAyarlari(referans=REFERANS_GUNU, musteri_sayisi=400, gecmis_gun=730, tohum=42,
                                   aylik_enflasyon=0.0, sektorler=tuple(PROFILLER))
PAKET_TOHUMU = 42
DEMO_PAROLA_DEGISKENI = "PANOSU_DEMO_PAROLA"


class KurulumHatasi(RuntimeError):
    """Kullanıcıya gösterilecek açık hata; metni adres veya parola içermez."""


def demo_parolasi() -> str:
    """PANOSU_DEMO_PAROLA'yı okur ve parola kuralını denetler (veri silinmeden ÖNCE)."""
    parola = os.environ.get(DEMO_PAROLA_DEGISKENI)
    if not parola:
        raise KurulumHatasi(f"{DEMO_PAROLA_DEGISKENI} ortam değişkeni tanımlı değil; demo kullanıcısı kurulamaz.")
    hata = parola_kurali_hatasi(parola, DEMO_EPOSTA)
    if hata:
        raise KurulumHatasi(f"{DEMO_PAROLA_DEGISKENI} parola kuralına uymuyor: {hata}")
    return parola


def uygulama_parolasi_ayarla(yonetici_url: str, uygulama_url: str) -> None:
    """Yönetici bağlantısıyla panosu_app'e uygulama adresindeki parolayı verir. Parola hiçbir metne girmez."""
    adres = make_url(uygulama_url)
    if adres.username != UYGULAMA_ROLU:
        raise KurulumHatasi(f"--uygulama-parolasi-ayarla: uygulama adresindeki kullanıcı {UYGULAMA_ROLU} değil.")
    if not adres.password:
        raise KurulumHatasi("--uygulama-parolasi-ayarla: uygulama adresinde parola yok.")
    yonetici = create_engine(yonetici_url)
    try:
        with yonetici.begin() as con:
            imlec = con.connection.dbapi_connection.cursor()
            try:
                imlec.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(UYGULAMA_ROLU), sql.Literal(adres.password)))
            finally:
                imlec.close()
    except Exception as e:
        raise KurulumHatasi(f"panosu_app parolası ayarlanamadı ({type(e).__name__})") from None
    finally:
        yonetici.dispose()


def kur(veritabani: str, demo_parola: str, ilerleme=print) -> float:
    """Reçetenin 7 adımı (modül belgesi). Toplam süreyi (sn) döndürür."""
    yonetici_url, _ = baglanti_adresleri(veritabani)     # ad doğrulanmadan bağlantı yok
    basla = time.perf_counter()

    def adim(no: int, ad: str, is_):
        t = time.perf_counter()
        ilerleme(f"[{no}/7] {ad}")
        sonuc = is_()
        ilerleme(f"      {time.perf_counter() - t:.1f} sn")
        return sonuc

    def _temizle():
        yonetici = create_engine(yonetici_url)
        try:
            ilerleme(f"  {temizle(yonetici)} [DEMO] işletme silindi")
        finally:
            yonetici.dispose()

    def _tazele():
        yon_url, uyg_url = baglanti_adresleri(veritabani)
        yonetici, uygulama = create_engine(yon_url), create_engine(uyg_url)
        try:
            tazele(yonetici, uygulama, ilerleme=ilerleme)
        finally:
            yonetici.dispose()
            uygulama.dispose()

    adim(1, "Temizlik", _temizle)
    adim(2, f"Sentetik işletmeler (referans {REFERANS_GUNU}, tohum {SENTETIK_AYARLARI.tohum})",
         lambda: yukle(uret(SENTETIK_AYARLARI), veritabani, ilerleme=ilerleme))
    adim(3, "Denge Pilates paketleri",
         lambda: paket_uretici.paketleri_yukle(veritabani, PAKET_TOHUMU, bugun=REFERANS_GUNU, ilerleme=ilerleme))
    adim(4, "Denge Pilates giderleri",
         lambda: paket_uretici.gecmis_giderleri_ekle(veritabani, bugun=REFERANS_GUNU, ilerleme=ilerleme))
    adim(5, "Butik Reformer", lambda: butik_reformer.yukle(butik_reformer.uret(), veritabani, ilerleme=ilerleme))
    adim(6, "Demo kullanıcısı", lambda: demo_kullanici_kur(veritabani, demo_parola, ilerleme=ilerleme))
    adim(7, "Demo tazeleme", _tazele)
    toplam = time.perf_counter() - basla
    ilerleme(f"Kurulum tamamlandı: {toplam:.1f} sn")
    return toplam


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(prog="python -m sentetik.demo_kur", description="Demo veritabanını baştan kur")
    a.add_argument("--veritabani", required=True, help="hedef veritabanı; '_demo' ile bitmeli")
    a.add_argument("--uygulama-parolasi-ayarla", action="store_true",
                   help="yalnızca yayında: panosu_app'e uygulama adresindeki parolayı ver (ALTER ROLE)")
    arg = a.parse_args(argv)
    if butik_reformer.BUGUN != REFERANS_GUNU:
        raise SystemExit("HATA: butik_reformer.BUGUN referans günüyle aynı değil; reçete güncellenmeli.")
    try:
        demo_veritabani_dogrula(arg.veritabani)          # bağlantıdan ÖNCE
        demo_parola = demo_parolasi()                    # veri silinmeden ÖNCE
        yonetici_url, uygulama_url = baglanti_adresleri(arg.veritabani)
        if arg.uygulama_parolasi_ayarla:
            uygulama_parolasi_ayarla(yonetici_url, uygulama_url)
            print(f"{UYGULAMA_ROLU}: giriş parolası ayarlandı", flush=True)
    except (DemoDisiVeritabani, KurulumHatasi) as hata:
        raise SystemExit(f"HATA: {hata}")
    print(f"{arg.veritabani}: demo kurulumu", flush=True)
    kur(arg.veritabani, demo_parola, ilerleme=lambda s: print(s, flush=True))


if __name__ == "__main__":
    main()
