"""Komut: python -m sentetik.demo_sunucu [--port 8000]

Web panelini panosu_demo veritabanıyla 127.0.0.1'de başlatır. Bağlantı adresi .env'deki PANOSU_VERITABANI_URL'den
yalnızca veritabanı adı değiştirilerek türetilir (yükleyicideki kalıp) ve yalnızca bu süreçte ortam değişkenine yazılır.
Ad "_demo" ile bitmiyorsa sunucu başlamaz. Adres ve parola hiçbir çıktıya yazılmaz.

config modülü ortam değişkeni ayarlanmadan ÖNCE import edilmez: ayarlar import anında okunur; önce import edilirse
uygulama .env'deki (canlı) adrese bağlanırdı. Başlamadan önce ayarlardaki veritabanı adı ayrıca doğrulanır.
"""

import argparse
import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

DEMO_VERITABANI = "panosu_demo"
DEMO_SONEKI = "_demo"
KOK_DIZIN = Path(__file__).resolve().parent.parent


def _demo_adresi(veritabani: str) -> str:
    if not veritabani.endswith(DEMO_SONEKI):
        raise SystemExit(f"HATA: demo sunucusu yalnızca adı '{DEMO_SONEKI}' ile biten veritabanıyla çalışır.")
    kaynak = dotenv_values(KOK_DIZIN / ".env").get("PANOSU_VERITABANI_URL")
    if not kaynak:
        raise SystemExit("HATA: .env'de PANOSU_VERITABANI_URL tanımlı değil.")
    return make_url(kaynak).set(database=veritabani).render_as_string(hide_password=False)


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(prog="python -m sentetik.demo_sunucu", description="Web paneli, panosu_demo ile")
    a.add_argument("--port", type=int, default=8000)
    arg = a.parse_args(argv)

    os.environ["PANOSU_VERITABANI_URL"] = _demo_adresi(DEMO_VERITABANI)
    os.chdir(KOK_DIZIN)

    from config import ayarlar                            # ortam değişkeni ayarlandıktan SONRA
    if make_url(ayarlar.veritabani_url).database != DEMO_VERITABANI:
        raise SystemExit("HATA: uygulama ayarları demo veritabanını göstermiyor; sunucu başlatılmadı.")

    import uvicorn
    print(f"{DEMO_VERITABANI} ile http://127.0.0.1:{arg.port} açıldı", flush=True)
    uvicorn.run("main:app", host="127.0.0.1", port=arg.port)


if __name__ == "__main__":
    main()
