"""Komut: python -m servisler.yenileme_calistir --veritabani <ad> --isletme <uuid> [--tarih YYYY-AA-GG]

Bir işletmenin aktif paketleri için yenileme riskini hesaplayıp `yenileme_riskleri`'ne yazar.

Kilit (yükleyicideki kalıp): yalnızca adı "_demo" veya "_test" ile biten veritabanlarına yazar; başka bir ad
verilirse bağlantı kurulmadan durur (canlı `panosu` için ileride ayrı onay gerekir). Bağlantı adresi .env'deki
PANOSU_VERITABANI_URL'den (panosu_app rolü, RLS'ye tabi) yalnızca veritabanı adı değiştirilerek türetilir.
"""

import argparse
import time
import uuid
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from config import ayarlar
from database import SessionLocal
from servisler.yenileme_servisi import yenileme_hesapla

IZINLI_SONEKLER = ("_demo", "_test")


class IzinsizVeritabani(ValueError):
    pass


def hedef_dogrula(veritabani: str | None) -> None:
    """Ad "_demo" veya "_test" ile bitmiyorsa IzinsizVeritabani fırlatır. Veritabanına bağlanmaz."""
    if not veritabani or not veritabani.endswith(IZINLI_SONEKLER):
        raise IzinsizVeritabani(
            f"Güvenlik: yenileme riski yalnızca adı {' veya '.join(IZINLI_SONEKLER)} ile biten bir veritabanına "
            f"yazılabilir (verilen: {veritabani!r})."
        )


def uygulama_adresi(veritabani: str) -> str:
    hedef_dogrula(veritabani)                            # ad doğrulanmadan adres üretilmez
    return make_url(ayarlar.veritabani_url).set(database=veritabani).render_as_string(hide_password=False)


def calistir(veritabani: str, isletme_id: uuid.UUID, hesaplama_tarihi: date | None = None) -> int:
    engine = create_engine(uygulama_adresi(veritabani))
    try:
        with SessionLocal(bind=engine) as db:            # after_begin olayı kiracı bağlamını ayarlar
            db.info["isletme_id"] = isletme_id
            return yenileme_hesapla(db, hesaplama_tarihi)
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(prog="python -m servisler.yenileme_calistir", description="Yenileme riski hesapla")
    a.add_argument("--veritabani", required=True, help="hedef veritabanı; '_demo' veya '_test' ile bitmeli")
    a.add_argument("--isletme", required=True, type=uuid.UUID, help="işletme kimliği (uuid)")
    a.add_argument("--tarih", type=date.fromisoformat, help="hesaplama tarihi (varsayılan: işletmenin bugünü)")
    arg = a.parse_args(argv)
    try:
        hedef_dogrula(arg.veritabani)
    except IzinsizVeritabani as hata:
        raise SystemExit(f"HATA: {hata}")
    basla = time.perf_counter()
    adet = calistir(arg.veritabani, arg.isletme, arg.tarih)
    print(f"{adet} paket için yenileme riski yazıldı ({time.perf_counter() - basla:.1f} sn).")


if __name__ == "__main__":
    main()
