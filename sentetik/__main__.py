"""Komut satırı: python -m sentetik [seçenekler]

Örnekler:
  python -m sentetik --sadece-uret                                   # veritabanına dokunmadan üret + V1 değerlendirmesi
  python -m sentetik --veritabani panosu_demo                        # üret ve yükle (demo verisi yoksa)
  python -m sentetik --veritabani panosu_demo --temizle --musteri 600  # eski demo verisini silip yeniden yükle

Yükleme yalnızca adı "_demo" ile biten veritabanına yapılır; başka ad verilirse bağlantı kurulmadan durur.
"""

import argparse
import time
from datetime import date
from pathlib import Path

from sentetik.katalog import PROFILLER
from sentetik.degerlendirme import v1_modelini_degerlendir
from sentetik.uretici import SentetikVeri, UretimAyarlari, uret


def _arguman_ayristir() -> argparse.Namespace:
    a = argparse.ArgumentParser(prog="python -m sentetik", description="Panosu sentetik veri motoru")
    a.add_argument("--musteri", type=int, default=400, help="işletme başına müşteri sayısı (varsayılan 400)")
    a.add_argument("--tohum", type=int, default=42, help="rastgelelik tohumu; aynı tohum = aynı veri")
    a.add_argument("--gecmis-gun", type=int, default=730, help="veri penceresi, gün (varsayılan 730)")
    a.add_argument("--referans", type=date.fromisoformat, default=date.today(), help="verinin bittiği gün (YYYY-AA-GG)")
    a.add_argument("--enflasyon", type=float, default=0.0, help="aylık fiyat artışı, örn. 0.02 = %%2")
    a.add_argument("--sektor", action="append", choices=sorted(PROFILLER), help="yalnız bu sektör(ler)")
    a.add_argument("--temizle", action="store_true", help="varsa eski [DEMO] verisini silip yeniden yükle")
    a.add_argument("--sadece-uret", action="store_true", help="veritabanına yazma")
    a.add_argument("--veritabani", help="hedef veritabanı adı; '_demo' ile bitmeli (yükleme için zorunlu)")
    a.add_argument("--gercek-dosya", type=Path, default=Path("veri/gercek_degerler.csv"))
    arg = a.parse_args()
    if not arg.sadece_uret and not arg.veritabani:
        a.error("yükleme için --veritabani zorunludur (ör. --veritabani panosu_demo); yalnızca üretmek için --sadece-uret")
    return arg


def ozet_yazdir(veri: SentetikVeri) -> None:
    print(f"{'Sektör':<13}{'Müşteri':>8}{'Ziyaret':>9}{'Ort.Ziyaret':>12}{'Ort.Sepet':>11}{'Toplam Ciro':>15}{'Aktif':>8}")
    for i in veri.isletmeler:
        tamam = [z for z in i.ziyaretler if z["durum"] == "tamamlandi"]
        ciro = sum(z["toplam_tutar"] for z in tamam)
        aktif = sum(g.canli_mi for g in i.gercek) / max(1, len(i.gercek))
        print(f"{i.profil.sektor:<13}{len(i.musteriler):>8}{len(tamam):>9}{len(tamam) / max(1, len(i.musteriler)):>12.1f}"
              f"{ciro / max(1, len(tamam)):>9.0f} ₺{ciro:>13,.0f} ₺{aktif:>7.0%}")


def degerlendirme_yazdir(veri: SentetikVeri) -> None:
    print("\nV1 churn modeli (MusteriAnalizi.py) vs. GERÇEK durum")
    print(f"{'Sektör':<13}{'Değerlendirilen':>16}{'Gerçek kayıp':>14}{'ROC AUC':>10}")
    for s in v1_modelini_degerlendir(veri):
        auc = f"{s.auc:.3f}" if s.auc is not None else "-"
        print(f"{s.sektor:<13}{s.degerlendirilen:>16}{s.gercek_kayip_orani:>14.0%}{auc:>10}")


def main() -> None:
    arg = _arguman_ayristir()
    if not arg.sadece_uret:
        from sentetik.yukleyici import DemoDisiVeritabani, demo_veritabani_dogrula
        try:
            demo_veritabani_dogrula(arg.veritabani)      # üretimden ve her bağlantıdan önce
        except DemoDisiVeritabani as hata:
            raise SystemExit(f"HATA: {hata}")
    ayar = UretimAyarlari(
        referans=arg.referans, musteri_sayisi=arg.musteri, gecmis_gun=arg.gecmis_gun, tohum=arg.tohum,
        aylik_enflasyon=arg.enflasyon, sektorler=tuple(arg.sektor) if arg.sektor else tuple(PROFILLER),
    )
    t = time.perf_counter()
    veri = uret(ayar)
    print(f"Üretildi ({time.perf_counter() - t:.1f} sn) | referans {ayar.referans} | tohum {ayar.tohum}\n")
    ozet_yazdir(veri)
    degerlendirme_yazdir(veri)

    if arg.sadece_uret:
        return

    from sentetik.yukleyici import DemoVerisiZatenVar, gercek_degerleri_yaz, yukle   # DB gerekince içe aktar

    print(f"\n{arg.veritabani} veritabanına yükleniyor (panosu_app rolü, RLS altında)...")
    t = time.perf_counter()
    try:
        eslesme = yukle(veri, arg.veritabani, eskiyi_sil=arg.temizle)
    except DemoVerisiZatenVar as hata:
        raise SystemExit(f"HATA: {hata}")
    gercek_degerleri_yaz(veri, eslesme, arg.gercek_dosya)
    print(f"Tamamlandı ({time.perf_counter() - t:.1f} sn). Gerçek değerler: {arg.gercek_dosya}")


if __name__ == "__main__":
    main()
