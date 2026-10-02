"""Komut: CSV/Excel içe aktarma (Adım 4b-1, `docs/adim-4b-tasarim.md`).

    python -m servisler.ice_aktar --veritabani <ad> --isletme <uuid> --kaynak <ad>
           [--uyeler DOSYA] [--paketler DOSYA] [--girisler DOSYA] [--esleme esleme.json] [--anonim] [--onayla]

Varsayılan ÖNİZLEME: veritabanına hiçbir şey yazılmaz (yalnızca işletmenin saat dilimi ve aynı kaynaktan gelmiş üye
kimlikleri okunur). --onayla ile üç dosya tek işlemde yazılır (K32). Önerilen eşleştirme
raporlar/ice_aktarma_esleme.json'a yazılır; düzenlenip --esleme ile geri verilebilir ({tür: {alan: başlık|null}}).
Hiçbir çıktıda kişisel veri değeri yoktur (K34): yalnızca başlık adları, sayılar ve satır no + alan + sebep.

Kilit (yenileme_calistir kalıbı): yalnızca adı "_demo" veya "_test" ile biten veritabanına bağlanır; adres .env'deki
PANOSU_VERITABANI_URL'den (panosu_app, RLS) yalnızca veritabanı adı değiştirilerek türetilir.
"""

import argparse
import json
import uuid
from pathlib import Path

from sqlalchemy import create_engine

from database import SessionLocal
from servisler.ice_aktarma import (
    AZAMI_BAYT,
    ESANLAMLILAR,
    TURLER,
    UYARI_ACIKLAMALARI,
    DosyaHatasi,
    EslemeHatasi,
    IceAktarmaHatasi,
    Tablo,
    ciro_cift_sayim_uyarisi,
    dis_kaynak_olustur,
    dosya_oku,
    esleme_dogrula,
    esleme_tahmin_et,
)
from servisler.ice_aktarma_yaz import EsikAsildi, hazirliklari_olustur, yaz
from servisler.yenileme_calistir import IzinsizVeritabani, hedef_dogrula, uygulama_adresi

ESLEME_CIKTI = Path("raporlar") / "ice_aktarma_esleme.json"
ILK_HATALAR = 20


def _ayirici_adi(ayirici: str | None) -> str:
    return {"\t": "sekme", None: "-"}.get(ayirici, repr(ayirici))


def _esleme_oku(yol: str) -> dict[str, dict[str, str | None]]:
    try:
        veri = json.loads(Path(yol).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SystemExit("HATA: eşleştirme dosyası okunamadı (JSON bekleniyor)") from None
    if not isinstance(veri, dict) or not all(
        isinstance(e, dict) and all(isinstance(b, (str, type(None))) for b in e.values()) for e in veri.values()
    ):
        raise SystemExit('HATA: eşleştirme biçimi {"uyeler": {"alan": "Başlık" | null}, ...} olmalı')
    return veri


def _tablolari_oku(dosyalar: dict[str, Path]) -> dict[str, Tablo]:
    tablolar = {}
    for tur, yol in dosyalar.items():
        try:
            if yol.stat().st_size > AZAMI_BAYT:           # K39: okumadan reddet
                raise DosyaHatasi(f"Dosya {AZAMI_BAYT // (1024 * 1024)} MB sınırını aşıyor")
            tablolar[tur] = dosya_oku(yol.read_bytes(), yol.name)
        except OSError:
            raise SystemExit(f"HATA: {tur} dosyası açılamadı") from None
        except DosyaHatasi as hata:
            raise SystemExit(f"HATA: {tur} ({yol.name}): {hata}") from None
    return tablolar


def _eslemeyi_yazdir(tur: str, alanlar: dict[str, str | None], tahmin) -> None:
    print("  Eşleştirme (alan ← başlık):")
    for alan in ESANLAMLILAR[tur]:
        print(f"    {alan:<13}← {alanlar.get(alan) or '— (eşleşmedi)'}")
    if tahmin is not None:
        for etiket, liste in (("Belirsiz", tahmin.belirsizler), ("Eşleşmeyen", tahmin.eslesmeyenler),
                              ("Hassas (okunmadı)", tahmin.hassaslar)):
            if liste:
                print(f"  {etiket} başlıklar: {', '.join(liste)}")


def calistir(db, dosyalar: dict[str, Path], kullanici_esleme: dict, dis_kaynak: str, anonim: bool,
             onayla: bool) -> int:
    """Önizleme (ve --onayla ile yazma). Çıkış kodu: 0 tamam, 1 onay reddedildi, 2 eşleştirme hatası."""
    tablolar = _tablolari_oku(dosyalar)
    eslemeler: dict[str, dict[str, str | None]] = {}
    sorunlu = False
    for tur, tablo in tablolar.items():
        tahmin = esleme_tahmin_et(tur, tablo.basliklar)
        eslemeler[tur] = kullanici_esleme.get(tur, tahmin.alanlar)
        kaynak_adi = "--esleme" if tur in kullanici_esleme else "tahmin"
        print(f"\n== {tur}: {dosyalar[tur].name} ({tablo.bicim}"
              + (f", {tablo.kodlama}, ayırıcı {_ayirici_adi(tablo.ayirici)}" if tablo.bicim == "csv" else "")
              + f"; eşleştirme: {kaynak_adi}) ==")
        _eslemeyi_yazdir(tur, eslemeler[tur], tahmin)
        try:
            esleme_dogrula(tur, eslemeler[tur], tablo.basliklar, anonim)
        except EslemeHatasi as hata:
            sorunlu = True
            print("  EŞLEŞTİRME HATASI:")
            for sorun in hata.sorunlar:
                print(f"    - {sorun}")

    ESLEME_CIKTI.parent.mkdir(parents=True, exist_ok=True)
    ESLEME_CIKTI.write_text(json.dumps(
        {tur: {alan: e.get(alan) for alan in ESANLAMLILAR[tur]} for tur, e in eslemeler.items()},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nEşleştirme {ESLEME_CIKTI} dosyasına yazıldı (düzenleyip --esleme ile verebilirsiniz).")
    if sorunlu:
        print("Eşleştirme düzeltilmeden satırlar hazırlanmaz; hiçbir şey yazılmadı.")
        return 2

    hazirliklar = hazirliklari_olustur(db, tablolar, eslemeler, dis_kaynak, anonim)
    for tur, h in hazirliklar.items():
        print(f"\n-- {tur}: okunan {h.okunan}, geçerli {h.gecerli}, hatalı {h.hatali}"
              + (" (hatalı oranı %10'un ÜZERİNDE)" if h.esik_asildi else ""))
        if h.hatalar:
            print(f"  Hatalar (ilk {ILK_HATALAR}):")
            for hata in h.hatalar[:ILK_HATALAR]:
                print(f"    {hata}")
        for anahtar, adet in sorted(h.uyarilar.items()):
            print(f"  Uyarı: {adet} × {UYARI_ACIKLAMALARI.get(anahtar, anahtar)}")
    if uyari := ciro_cift_sayim_uyarisi(eslemeler.get("girisler"), "paketler" in tablolar):
        print(f"\nUYARI: {uyari}")

    if not onayla:
        print("\nÖnizleme: veritabanına hiçbir şey yazılmadı. Yazmak için --onayla ekleyin.")
        return 0
    try:
        sonuc = yaz(db, list(hazirliklar.values()), dis_kaynak)
    except EsikAsildi as hata:
        print(f"\nONAY REDDEDİLDİ: {hata}. Hiçbir şey yazılmadı.")
        return 1
    print(f"\n{'Sonuç':<10}{'eklenen':>10}{'güncellenen':>13}{'atlanan':>10}")
    for tur, s in sonuc.turler.items():
        print(f"{tur:<10}{s.eklenen:>10}{s.guncellenen:>13}{s.atlanan:>10}")
    for anahtar, adet in sorted(sonuc.uyarilar.items()):
        print(f"Uyarı: {adet} × {UYARI_ACIKLAMALARI.get(anahtar, anahtar)}")
    if sonuc.yenileme_uyarisi:
        print(f"UYARI: {sonuc.yenileme_uyarisi}")
    else:
        print(f"Yenileme riski {sonuc.yenilenen} aktif paket için yeniden hesaplandı.")
    return 0


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(prog="python -m servisler.ice_aktar", description="CSV/Excel içe aktarma")
    a.add_argument("--veritabani", required=True, help="hedef veritabanı; '_demo' veya '_test' ile bitmeli")
    a.add_argument("--isletme", required=True, type=uuid.UUID, help="işletme kimliği (uuid)")
    a.add_argument("--kaynak", required=True, help="kaynak adı (a-z, 0-9, _ -; ör. stuvio); dis_kaynak = csv:<ad>")
    for tur in TURLER:
        a.add_argument(f"--{tur}", metavar="DOSYA", help=f"{tur} dosyası (.csv veya .xlsx)")
    a.add_argument("--esleme", metavar="JSON", help="düzeltilmiş eşleştirme dosyası")
    a.add_argument("--anonim", action="store_true", help="ad 'Üye xxxxxx' olur; telefon ve e-posta okunmaz")
    a.add_argument("--onayla", action="store_true", help="önizleme yerine veritabanına yaz")
    arg = a.parse_args(argv)
    dosyalar = {tur: Path(getattr(arg, tur)) for tur in TURLER if getattr(arg, tur)}
    if not dosyalar:
        a.error("en az bir dosya gerekli (--uyeler, --paketler, --girisler)")
    try:
        hedef_dogrula(arg.veritabani)
        dis_kaynak = dis_kaynak_olustur(arg.kaynak)
    except (IzinsizVeritabani, ValueError) as hata:
        raise SystemExit(f"HATA: {hata}")
    kullanici_esleme = _esleme_oku(arg.esleme) if arg.esleme else {}

    engine = create_engine(uygulama_adresi(arg.veritabani))
    try:
        with SessionLocal(bind=engine) as db:          # after_begin olayı kiracı bağlamını ayarlar
            db.info["isletme_id"] = arg.isletme
            kod = calistir(db, dosyalar, kullanici_esleme, dis_kaynak, arg.anonim, arg.onayla)
    except IceAktarmaHatasi as hata:
        raise SystemExit(f"HATA: {hata}")
    finally:
        engine.dispose()
    if kod:
        raise SystemExit(kod)


if __name__ == "__main__":
    main()
