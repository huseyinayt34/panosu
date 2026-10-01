"""Komut: python -m servisler.rapor_uret --veritabani <ad> --isletme <uuid> --cikti raporlar/<dosya>.html

Haftalık raporu HTML dosyasına yazar. Kilit: yalnızca adı "_demo" veya "_test" ile biten veritabanları (bağlantı
kurulmadan doğrulanır). Bağlantı panosu_app rolüyle, işletmenin kiracı bağlamında (RLS) yapılır. Çıktı raporlar/
altına yazılmalıdır (git'e girmez).
"""

import argparse
import uuid
from pathlib import Path

from sqlalchemy import create_engine

from database import SessionLocal
from servisler.rapor_servisi import haftalik_rapor
from servisler.yenileme_calistir import IzinsizVeritabani, hedef_dogrula, uygulama_adresi


def uret(veritabani: str, isletme_id: uuid.UUID, cikti: Path) -> Path:
    hedef_dogrula(veritabani)                                # ad doğrulanmadan bağlantı yok
    engine = create_engine(uygulama_adresi(veritabani))
    try:
        with SessionLocal(bind=engine) as db:
            db.info["isletme_id"] = isletme_id
            html = haftalik_rapor(db)
    finally:
        engine.dispose()
    cikti.parent.mkdir(parents=True, exist_ok=True)
    cikti.write_text(html, encoding="utf-8")
    return cikti


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(prog="python -m servisler.rapor_uret", description="Haftalık rapor (HTML)")
    a.add_argument("--veritabani", required=True, help="hedef veritabanı; '_demo' veya '_test' ile bitmeli")
    a.add_argument("--isletme", required=True, type=uuid.UUID)
    a.add_argument("--cikti", required=True, type=Path, help="örn. raporlar/haftalik.html")
    arg = a.parse_args(argv)
    try:
        yol = uret(arg.veritabani, arg.isletme, arg.cikti)
    except IzinsizVeritabani as hata:
        raise SystemExit(f"HATA: {hata}")
    print(f"Rapor yazıldı: {yol}")


if __name__ == "__main__":
    main()
