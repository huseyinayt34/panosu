"""Komut: python -m sentetik.demo_sunucu [--port 8000] [--tazeleme-yok]

Web panelini panosu_demo veritabanıyla 127.0.0.1'de başlatır. Bağlantı adresi .env'deki PANOSU_VERITABANI_URL'den
yalnızca veritabanı adı değiştirilerek türetilir (yükleyicideki kalıp) ve yalnızca bu süreçte ortam değişkenine yazılır.
Ad "_demo" ile bitmiyorsa sunucu başlamaz. Adres ve parola hiçbir çıktıya yazılmaz.

config modülü ortam değişkeni ayarlanmadan ÖNCE import edilmez: ayarlar import anında okunur; önce import edilirse
uygulama .env'deki (canlı) adrese bağlanırdı. Başlamadan önce ayarlardaki veritabanı adı ayrıca doğrulanır.

Demo tazeleme (K16, `sentetik/demo_tazele.py`): açılışta bir kez ve açık kaldıkça her gece 03:00'te (Europe/Istanbul)
demo verisi bugüne kaydırılır. Tazeleme hatası sunucuyu durdurmaz; tek satır yazılır. --tazeleme-yok ikisini de atlar.
"""

import argparse
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

DEMO_VERITABANI = "panosu_demo"
DEMO_SONEKI = "_demo"
KOK_DIZIN = Path(__file__).resolve().parent.parent
GECE_SAATI = 3
ISTANBUL = ZoneInfo("Europe/Istanbul")


def _demo_adresi(veritabani: str) -> str:
    if not veritabani.endswith(DEMO_SONEKI):
        raise SystemExit(f"HATA: demo sunucusu yalnızca adı '{DEMO_SONEKI}' ile biten veritabanıyla çalışır.")
    kaynak = dotenv_values(KOK_DIZIN / ".env").get("PANOSU_VERITABANI_URL")
    if not kaynak:
        raise SystemExit("HATA: .env'de PANOSU_VERITABANI_URL tanımlı değil.")
    return make_url(kaynak).set(database=veritabani).render_as_string(hide_password=False)


def sonraki_calisma(simdi: datetime) -> datetime:
    """simdi'den sonraki ilk 03:00 (Europe/Istanbul); simdi tam 03:00 ise ertesi gün. simdi saat dilimli olmalı."""
    yerel = simdi.astimezone(ISTANBUL)
    hedef = yerel.replace(hour=GECE_SAATI, minute=0, second=0, microsecond=0)
    if hedef <= yerel:
        hedef += timedelta(days=1)
    return hedef


def _tazele_bir_kez(etiket: str) -> None:
    """Hata yakalanır ve tek satırla yazılır (istisna metni yazılmaz: bağlantı adresi içerebilir)."""
    from sqlalchemy import create_engine

    from sentetik.demo_tazele import tazele
    from sentetik.yukleyici import baglanti_adresleri

    try:
        yonetici_url, uygulama_url = baglanti_adresleri(DEMO_VERITABANI)
        yonetici, uygulama = create_engine(yonetici_url), create_engine(uygulama_url)
        try:
            print(f"Demo tazeleme ({etiket}):", flush=True)
            tazele(yonetici, uygulama, ilerleme=lambda s: print(s, flush=True))
        finally:
            yonetici.dispose()
            uygulama.dispose()
    except Exception as e:
        print(f"Demo tazeleme ({etiket}) başarısız: {type(e).__name__}", flush=True)


def _gece_dongusu() -> None:
    while True:
        try:
            hedef = sonraki_calisma(datetime.now(ISTANBUL))
            while (kalan := (hedef - datetime.now(ISTANBUL)).total_seconds()) > 0:
                time.sleep(min(kalan, 3600))              # uyku kayması (bilgisayar uykusu) birikmesin
            _tazele_bir_kez("gece")
        except Exception as e:                            # thread ölmez
            print(f"Gece tazeleme döngüsü hatası: {type(e).__name__}", flush=True)
            time.sleep(60)


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(prog="python -m sentetik.demo_sunucu", description="Web paneli, panosu_demo ile")
    a.add_argument("--port", type=int, default=8000)
    a.add_argument("--tazeleme-yok", action="store_true", help="açılışta ve gece demo tazelemesi yapma")
    arg = a.parse_args(argv)

    os.environ["PANOSU_VERITABANI_URL"] = _demo_adresi(DEMO_VERITABANI)
    os.chdir(KOK_DIZIN)

    from config import ayarlar                            # ortam değişkeni ayarlandıktan SONRA
    if make_url(ayarlar.veritabani_url).database != DEMO_VERITABANI:
        raise SystemExit("HATA: uygulama ayarları demo veritabanını göstermiyor; sunucu başlatılmadı.")

    if not arg.tazeleme_yok:
        _tazele_bir_kez("açılış")
        threading.Thread(target=_gece_dongusu, name="demo-gece-tazeleme", daemon=True).start()

    import uvicorn
    print(f"{DEMO_VERITABANI} ile http://127.0.0.1:{arg.port} açıldı", flush=True)
    uvicorn.run("main:app", host="127.0.0.1", port=arg.port)


if __name__ == "__main__":
    main()
