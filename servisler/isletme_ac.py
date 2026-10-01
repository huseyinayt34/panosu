"""Komut: python -m servisler.isletme_ac --veritabani <ad> --eposta <e> --ad-soyad <a> --isletme <ad> [--sektor spor_salonu]

Pilot işletmeyi ve sahibini açar (açık kayıt kapalıyken; K5). Parola getpass ile iki kez sorulur ve hiçbir çıktıya
yazılmaz. Kilit: yalnızca adı "_demo" veya "_test" ile biten veritabanları; başka bir veritabanı (canlı panosu) için
--canli-onay bayrağı gerekir (proje sahibinin ayrı onayıyla). Ad doğrulanmadan bağlantı kurulmaz.
Yazma panosu_app rolüyle, kayıt ucuyla aynı servis fonksiyonu üzerinden yapılır.
"""

import argparse
import getpass
import uuid

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from config import ayarlar
from database import SessionLocal
from servisler.kimlik import EpostaKayitli, erisim_tokeni_coz, kayit, parola_kurali_hatasi
from servisler.yenileme_calistir import IZINLI_SONEKLER, IzinsizVeritabani


def hedef_dogrula(veritabani: str | None, canli_onay: bool) -> None:
    if not veritabani:
        raise IzinsizVeritabani("Veritabanı adı verilmedi")
    if not veritabani.endswith(IZINLI_SONEKLER) and not canli_onay:
        raise IzinsizVeritabani(
            f"Güvenlik: {veritabani!r} '_demo'/'_test' ile bitmiyor; canlı veritabanı için --canli-onay gerekir."
        )


def isletme_ac(veritabani: str, eposta: str, ad_soyad: str, isletme_adi: str, sektor: str | None, parola: str,
               canli_onay: bool = False) -> tuple[uuid.UUID, uuid.UUID]:
    """(kullanici_id, isletme_id). Oturum açılır ama tokenlar kullanılmaz (sahip kendisi giriş yapar)."""
    hedef_dogrula(veritabani, canli_onay)
    hata = parola_kurali_hatasi(parola, eposta)
    if hata:
        raise ValueError(hata)
    engine = create_engine(make_url(ayarlar.veritabani_url).set(database=veritabani))
    try:
        with SessionLocal(bind=engine) as db:
            cift = kayit(db, eposta, ad_soyad, parola, isletme_adi, sektor)
            kullanici_id, isletme_id = erisim_tokeni_coz(cift.erisim_tokeni)
            return kullanici_id, isletme_id
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(prog="python -m servisler.isletme_ac", description="Pilot işletme ve sahibini aç")
    a.add_argument("--veritabani", required=True)
    a.add_argument("--eposta", required=True)
    a.add_argument("--ad-soyad", required=True)
    a.add_argument("--isletme", required=True, help="işletme adı")
    a.add_argument("--sektor", default="spor_salonu")
    a.add_argument("--canli-onay", action="store_true", help="yalnızca proje sahibinin ayrı onayıyla")
    arg = a.parse_args(argv)
    try:
        hedef_dogrula(arg.veritabani, arg.canli_onay)
    except IzinsizVeritabani as hata:
        raise SystemExit(f"HATA: {hata}")
    parola = getpass.getpass("Sahibin parolası: ")
    if getpass.getpass("Parola (tekrar): ") != parola:
        raise SystemExit("HATA: Parolalar eşleşmiyor")
    try:
        kullanici_id, isletme_id = isletme_ac(arg.veritabani, arg.eposta, arg.ad_soyad, arg.isletme, arg.sektor,
                                              parola, arg.canli_onay)
    except (ValueError, EpostaKayitli) as hata:
        raise SystemExit(f"HATA: {hata if isinstance(hata, ValueError) else 'Bu e-posta ile kayıtlı hesap var'}")
    print(f"İşletme açıldı: {arg.isletme} ({isletme_id}); sahip: {arg.eposta} ({kullanici_id})")


if __name__ == "__main__":
    main()
