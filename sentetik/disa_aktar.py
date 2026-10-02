"""Komut: python -m sentetik.disa_aktar --veritabani <ad>_demo --isletme <uuid> --cikti raporlar/disa_aktarma/

Bir işletmenin üyelerini, paketlerini ve tamamlanmış girişlerini Türkçe Excel biçiminde (cp1254, ";" ayırıcı,
gg.aa.yyyy SS:DD, "1.250,00") üç CSV'ye yazar: K41 gidiş-dönüş kabul testi ve elle deneme için. Başlıklar içe aktarma
sözlüğünde karşılığı olan doğal Türkçe başlıklardır. Kimlik sütunu: mevcut dis_kimlik, yoksa musteri_id/paket_id.
Giriş dosyasında kimlik sütunu yoktur (içe aktarmada türetilir). Giderler, hizmetler ve ziyaret tutarları aktarılmaz.

Kilit komut seviyesindedir: yalnızca adı "_demo" ile biten veritabanı (sentetik veri; dosyalar kişisel veri içerir ve
raporlar/ altına yazılır, git'e girmez). csv_uret() herhangi bir kiracı bağlamlı oturumla çağrılabilir (testler).
"""

import argparse
import csv
import io
import uuid
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from config import ayarlar
from database import SessionLocal
from models import Musteri, MusteriPaketi, Ziyaret
from sentetik.yukleyici import DemoDisiVeritabani, demo_veritabani_dogrula
from servisler.ice_aktarma_yaz import isletme_saat_dilimi

KODLAMA = "cp1254"
DURUM_ADLARI = {"aktif": "Aktif", "bitti": "Bitti", "iptal": "İptal", "donduruldu": "Donduruldu"}


def tutar_bicimle(tutar: Decimal) -> str:
    """Decimal → "1.250,00" (Türkçe Excel)."""
    return f"{tutar:,.2f}".replace(",", "\0").replace(".", ",").replace("\0", ".")


def _csv(basliklar: list[str], satirlar: list[list[str]]) -> bytes:
    tampon = io.StringIO(newline="")
    yazici = csv.writer(tampon, delimiter=";")
    yazici.writerow(basliklar)
    yazici.writerows(satirlar)
    return tampon.getvalue().encode(KODLAMA)


def csv_uret(db: Session) -> dict[str, bytes]:
    """{"uyeler.csv", "paketler.csv", "girisler.csv"} → içerik. Silinmiş üyeler ve onların kayıtları dahil edilmez."""
    dilim = ZoneInfo(isletme_saat_dilimi(db))
    uyeler = db.execute(
        select(Musteri.musteri_id, Musteri.dis_kimlik, Musteri.ad_soyad, Musteri.telefon_e164, Musteri.eposta)
        .where(Musteri.silindi_at.is_(None))
        .order_by(Musteri.olusturma_zamani, Musteri.musteri_id)
    ).all()
    uye_no = {u.musteri_id: u.dis_kimlik or str(u.musteri_id) for u in uyeler}
    if len(set(uye_no.values())) != len(uye_no):
        raise ValueError("Üye No tekrar ediyor (farklı kaynaklardan aynı dis_kimlik)")

    paketler = db.execute(
        select(MusteriPaketi).join(Musteri, Musteri.musteri_id == MusteriPaketi.musteri_id)
        .where(Musteri.silindi_at.is_(None))
        .order_by(MusteriPaketi.musteri_id, MusteriPaketi.baslangic_tarihi, MusteriPaketi.paket_id)
    ).scalars().all()
    girisler = db.execute(
        select(Ziyaret.musteri_id, Ziyaret.ziyaret_zamani).join(Musteri, Musteri.musteri_id == Ziyaret.musteri_id)
        .where(Ziyaret.durum == "tamamlandi", Musteri.silindi_at.is_(None))
        .order_by(Ziyaret.musteri_id, Ziyaret.ziyaret_zamani)
    ).all()

    return {
        "uyeler.csv": _csv(
            ["Üye No", "Adı Soyadı", "Telefon", "E-posta"],
            [[uye_no[u.musteri_id], u.ad_soyad, u.telefon_e164 or "", u.eposta or ""] for u in uyeler],
        ),
        "paketler.csv": _csv(
            ["Üye No", "Paket No", "Paket Adı", "Başlangıç Tarihi", "Bitiş Tarihi", "Seans Sayısı", "Ücret", "Durum"],
            [[uye_no[p.musteri_id], p.dis_kimlik or str(p.paket_id), p.ad, p.baslangic_tarihi.strftime("%d.%m.%Y"),
              p.bitis_tarihi.strftime("%d.%m.%Y") if p.bitis_tarihi else "",
              str(p.giris_hakki) if p.giris_hakki is not None else "", tutar_bicimle(p.ucret),
              DURUM_ADLARI[p.durum]] for p in paketler],
        ),
        "girisler.csv": _csv(
            ["Üye No", "Giriş Tarihi"],
            [[uye_no[g.musteri_id], g.ziyaret_zamani.astimezone(dilim).strftime("%d.%m.%Y %H:%M")] for g in girisler],
        ),
    }


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(prog="python -m sentetik.disa_aktar", description="İşletme verisini CSV'ye aktar")
    a.add_argument("--veritabani", required=True, help="'_demo' ile biten veritabanı")
    a.add_argument("--isletme", required=True, type=uuid.UUID)
    a.add_argument("--cikti", required=True, type=Path, help="çıktı klasörü (ör. raporlar/disa_aktarma/)")
    arg = a.parse_args(argv)
    try:
        demo_veritabani_dogrula(arg.veritabani)
    except DemoDisiVeritabani as hata:
        raise SystemExit(f"HATA: {hata}")
    engine = create_engine(make_url(ayarlar.veritabani_url).set(database=arg.veritabani))
    try:
        with SessionLocal(bind=engine) as db:
            db.info["isletme_id"] = arg.isletme
            if isletme_saat_dilimi(db) is None:
                raise SystemExit("HATA: işletme bulunamadı")
            dosyalar = csv_uret(db)
    finally:
        engine.dispose()
    arg.cikti.mkdir(parents=True, exist_ok=True)
    for ad, icerik in dosyalar.items():
        (arg.cikti / ad).write_bytes(icerik)
        print(f"{arg.cikti / ad}: {icerik.count(b'\n') - 1} satır")


if __name__ == "__main__":
    main()
