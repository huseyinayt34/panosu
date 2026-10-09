"""Command: pilot validation report and today's risk list from a firm's files, without a database
(pilot step, `docs/adim-pilot-tasarim.md`).

    python -m servisler.pilot_dogrula --kaynak <name> --paketler p.csv --girisler g.csv [g2.csv ...]
           [--esleme esleme.json] [--ad "Studio name"] [--saat-dilimi Europe/Istanbul] [--cikti DIR]

Reads only package and check-in files (no member file: names, phones and e-mails are never needed, K64). Same
reading, mapping, whitelist and sensitive-column rules as `servisler.ice_aktar` (K30-K38); nothing is written to
any database and the input files are not copied. Outputs (default raporlar/pilot/<name>/, gitignored):
pilot-raporu.html, dogrulama.csv (scored packages at the cut-offs with the real outcome), skorlar.csv (today's list),
esleme.json (the mapping used; edit and pass back with --esleme). Several check-in files are allowed because one
file is limited to 50,000 rows (K71).
Does not import database/config, so it runs without .env and without PostgreSQL.
"""

import argparse
import csv
import io
import json
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jinja2 import Environment, FileSystemLoader, select_autoescape

from servisler import bicim, pilot
from servisler.ice_aktarma import (
    AZAMI_BAYT,
    ESANLAMLILAR,
    UYARI_ACIKLAMALARI,
    DosyaHatasi,
    EslemeHatasi,
    Tablo,
    dis_kaynak_olustur,
    dosya_oku,
    esleme_tahmin_et,
    satirlari_hazirla,
)

SABLON_DIZINI = Path(__file__).resolve().parent.parent / "sablonlar"
VARSAYILAN_DILIM = "Europe/Istanbul"
ILK_HATALAR = 20

_ortam = Environment(loader=FileSystemLoader(SABLON_DIZINI), autoescape=select_autoescape(["html"]))
_ortam.globals.update(para=bicim.para, tarih=bicim.tarih, olasilik=bicim.olasilik, ondalik=bicim.ondalik)


def _oku(yol: Path, tur: str) -> Tablo:
    try:
        if yol.stat().st_size > AZAMI_BAYT:                       # K39: reject before reading
            raise DosyaHatasi(f"Dosya {AZAMI_BAYT // (1024 * 1024)} MB sınırını aşıyor")
        return dosya_oku(yol.read_bytes(), yol.name)
    except OSError:
        raise SystemExit(f"HATA: {tur} dosyası açılamadı: {yol.name}") from None
    except DosyaHatasi as hata:
        raise SystemExit(f"HATA: {tur} ({yol.name}): {hata}") from None


def _hazirla(tur: str, yollar: list[Path], kullanici_esleme: dict, dilim: str, bugun: date, dis_kaynak: str):
    """Prepared records of one file type (several check-in files are concatenated). Exit 2 on a mapping error,
    exit 1 if more than 10% of the rows of a file are invalid (K38)."""
    kayitlar, gorulen, esleme_ciktisi = [], set(), {}
    for yol in yollar:
        tablo = _oku(yol, tur)
        tahmin = esleme_tahmin_et(tur, tablo.basliklar)
        alanlar = kullanici_esleme.get(tur, tahmin.alanlar)
        esleme_ciktisi = {alan: alanlar.get(alan) for alan in ESANLAMLILAR[tur]}
        print(f"\n== {tur}: {yol.name} ==")
        for alan in ESANLAMLILAR[tur]:
            print(f"    {alan:<13}← {alanlar.get(alan) or '— (eşleşmedi)'}")
        if tahmin.hassaslar:
            print(f"  Hassas başlıklar (okunmadı): {', '.join(tahmin.hassaslar)}")
        try:
            h = satirlari_hazirla(tur, tablo, alanlar, dilim, bugun, True, dis_kaynak)
        except EslemeHatasi as hata:
            print("  EŞLEŞTİRME HATASI:\n" + "\n".join(f"    - {s}" for s in hata.sorunlar))
            raise SystemExit(2) from None
        print(f"  okunan {h.okunan}, geçerli {h.gecerli}, hatalı {h.hatali}")
        for satir in h.hatalar[:ILK_HATALAR]:
            print(f"    {satir}")
        for anahtar, adet in sorted(h.uyarilar.items()):
            print(f"  Uyarı: {adet} × {UYARI_ACIKLAMALARI.get(anahtar, anahtar)}")
        if h.esik_asildi:
            print(f"\nDURDU: {yol.name} satırlarının %10'undan fazlası hatalı; eşleştirmeyi ve biçimi kontrol edin.")
            raise SystemExit(1)
        for k in h.kayitlar:                                       # same derived id across files -> one record
            if k.dis_kimlik not in gorulen:
                gorulen.add(k.dis_kimlik)
                kayitlar.append(k)
    return kayitlar, esleme_ciktisi


def _csv(satirlar: list[list], basliklar: list[str]) -> str:
    """Turkish Excel CSV (';' separator); written with utf-8-sig so Excel shows Turkish letters."""
    tampon = io.StringIO()
    w = csv.writer(tampon, delimiter=";", lineterminator="\r\n")
    w.writerow(basliklar)
    w.writerows(satirlar)
    return tampon.getvalue()


def _sayi(deger) -> str:
    return "" if deger is None else str(deger).replace(".", ",")


def _yorum(d: pilot.Dogrulama) -> list[str]:
    """Plain-language reading of the result (K70); written the same way whether the result is good or bad.
    Bands use the values shown in the report (2 decimals)."""
    if d.auc is None:
        return ["Bu veride değerlendirilecek yeterli paket yok (yenileyen ya da yenilemeyen üye çıkmadı); "
                "doğruluk ölçülemedi."]
    auc, alt, ust = round(d.auc, 2), round(d.auc_alt, 2), round(d.auc_ust, 2)
    if alt <= 0.50:
        return ["Sonuç belirsiz: %95 aralığı 0,50'yi (yazı-tura) içeriyor. Bu dönemde modelin işe yaradığını ya da "
                "yaramadığını söyleyecek kadar yenilemeyen paket yok; daha uzun bir dönemle tekrar ölçmek gerekir."]
    if auc >= 0.80:
        satirlar = ["Model, paketini yenileyecek ve yenilemeyecek üyeleri güçlü biçimde ayırdı."]
    elif auc >= 0.70:
        satirlar = ["Model, yenileyecek ve yenilemeyecek üyeleri iyi ayırdı."]
    elif auc >= 0.60:
        satirlar = ["Model orta düzeyde ayırdı: listeyi kesin bir tahmin olarak değil, kimi önce arayacağınızı "
                    "sıralamak için kullanmak doğru olur."]
    else:
        satirlar = ["Bu veride model yenilemeyi ayırt edemedi. Bunu gizlemiyoruz; nedenini (veri biçimi, paket "
                    "türleri, dönem) sizinle birlikte inceleyeceğiz."]
    kural = f"(kuralın AUC'si {bicim.ondalik(d.kural_auc, 2)})"
    if d.auc > d.kural_auc + 0.02:
        satirlar.append(f"Basit \"son 21 günde en fazla 1 kez geldi\" kuralından daha iyi {kural}.")
    elif d.auc >= d.kural_auc - 0.02:
        satirlar.append(f"Basit \"son 21 günde en fazla 1 kez geldi\" kuralıyla benzer {kural}.")
    else:
        satirlar.append(f"Bu veride basit \"son 21 günde en fazla 1 kez geldi\" kuralı daha iyi sonuç verdi {kural}.")
    if ust - alt > 0.20:
        satirlar.append("Değerlendirilen paket sayısı az olduğu için aralık geniş; birkaç ay sonra tekrar ölçmek "
                        "sonucu netleştirir.")
    return satirlar


def rapor_html(d: pilot.Dogrulama, g: pilot.GuncelListe, ad: str) -> str:
    bekl = None if d.yenileme_orani is None else (1 - d.yenileme_orani) * d.ilk_sira_n
    fark = None
    if d.gercek_kayip:
        fark = (d.tahmini_kayip - d.gercek_kayip) / d.gercek_kayip
    return _ortam.get_template("pilot_raporu.html").render(
        ad=ad, d=d, g=g, yorum=_yorum(d), beklenen_birakan=bekl, rp_fark=fark,
        ilk_sira=list(zip(d.skorlar, d.yeniledi))[: d.ilk_sira_n],
        sabit=pilot, uretim=datetime.now(UTC).date())


def dogrulama_csv(d: pilot.Dogrulama) -> str:
    return _csv([[s.gun.strftime("%d.%m.%Y"), s.paket.uye_kimlik, s.paket.dis_kimlik, s.paket.ad,
                  s.paket.bitis_tarihi.strftime("%d.%m.%Y"), _sayi(s.p_yenileme), _sayi(s.riskteki_para),
                  s.aciklama.cumle, "evet" if r else "hayır"] for s, r in zip(d.skorlar, d.yeniledi)],
                ["Tahmin Günü", "Üye No", "Paket No", "Paket Adı", "Bitiş Tarihi", "Yenileme Olasılığı",
                 "Riskteki Para", "Neden", "Yeniledi mi"])


def skorlar_csv(g: pilot.GuncelListe) -> str:
    """Today's list; also the output of `servisler.skor`. Data day and model version on every row (K78)."""
    return _csv([[s.paket.uye_kimlik, s.paket.dis_kimlik, s.paket.ad,
                  s.paket.bitis_tarihi.strftime("%d.%m.%Y") if s.paket.bitis_tarihi else "",
                  _sayi(s.kalan_gun), _sayi(s.kalan_giris), _sayi(s.p_hayatta_simdi), _sayi(s.p_yenileme),
                  _sayi(s.riskteki_para), s.aciklama.cumle, g.gun.strftime("%d.%m.%Y"), s.model_versiyonu]
                 for s in g.skorlar],
                ["Üye No", "Paket No", "Paket Adı", "Bitiş Tarihi", "Kalan Gün", "Kalan Giriş", "Aktif Olasılığı",
                 "Yenileme Olasılığı", "Riskteki Para", "Neden", "Veri Günü", "Model Sürümü"])


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(prog="python -m servisler.pilot_dogrula",
                                description="Pilot doğrulama raporu ve güncel risk listesi (veritabanı yok)")
    a.add_argument("--kaynak", required=True, help="kısa ad (a-z, 0-9, _ -); çıktı klasörü bu adla açılır")
    a.add_argument("--paketler", required=True, metavar="DOSYA", help="paket dosyası (.csv veya .xlsx)")
    a.add_argument("--girisler", required=True, nargs="+", metavar="DOSYA",
                   help="giriş dosyası; 50.000 satırı aşıyorsa yıllara bölünmüş birden çok dosya")
    a.add_argument("--esleme", metavar="JSON", help='düzeltilmiş eşleştirme: {"paketler": {"alan": "Başlık"}}')
    a.add_argument("--ad", help="raporda görünecek stüdyo adı (varsayılan: --kaynak)")
    a.add_argument("--saat-dilimi", default=VARSAYILAN_DILIM)
    a.add_argument("--cikti", type=Path, help="çıktı klasörü (varsayılan: raporlar/pilot/<kaynak>)")
    arg = a.parse_args(argv)
    try:
        dis_kaynak = dis_kaynak_olustur(arg.kaynak)
        dilim = ZoneInfo(arg.saat_dilimi)
    except (ValueError, ZoneInfoNotFoundError) as hata:
        raise SystemExit(f"HATA: {hata}")
    kullanici_esleme = {}
    if arg.esleme:
        try:
            kullanici_esleme = json.loads(Path(arg.esleme).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise SystemExit("HATA: eşleştirme dosyası okunamadı (JSON bekleniyor)") from None
    cikti = arg.cikti or Path("raporlar") / "pilot" / arg.kaynak

    # Check-ins first: the data day L (latest check-in) is the "today" of the package status rule (K65), so a firm
    # that shifted all dates back still gets correct statuses.
    girisler, es_g = _hazirla("girisler", [Path(y) for y in arg.girisler], kullanici_esleme, arg.saat_dilimi,
                              datetime.now(dilim).date(), dis_kaynak)
    ziyaretler = pilot.ziyaret_gunleri(girisler, dilim)
    try:
        L = pilot.veri_gunu(ziyaretler, dilim)
    except pilot.YetersizVeri as hata:
        raise SystemExit(f"HATA: {hata}")
    paketler, es_p = _hazirla("paketler", [Path(arg.paketler)], kullanici_esleme, arg.saat_dilimi, L, dis_kaynak)

    try:
        d = pilot.dogrula(ziyaretler, paketler, dilim)
        g = pilot.guncel(ziyaretler, paketler, dilim)
    except (pilot.YetersizVeri, RuntimeError) as hata:              # RuntimeError: the fit did not converge
        raise SystemExit(f"HATA: {hata}")

    cikti.mkdir(parents=True, exist_ok=True)
    (cikti / "pilot-raporu.html").write_text(rapor_html(d, g, arg.ad or arg.kaynak), encoding="utf-8")
    (cikti / "dogrulama.csv").write_text(dogrulama_csv(d), encoding="utf-8-sig", newline="")
    (cikti / "skorlar.csv").write_text(skorlar_csv(g), encoding="utf-8-sig", newline="")
    (cikti / "esleme.json").write_text(json.dumps({"paketler": es_p, "girisler": es_g}, ensure_ascii=False,
                                                  indent=2), encoding="utf-8")

    print(f"\nVeri günü {L:%d.%m.%Y}; kesimler {', '.join(f'{c:%d.%m.%Y}' for c in d.kesimler)}; "
          f"değerlendirilen paket {len(d.skorlar)} ({len(d.skorlar) - sum(d.yeniledi)} yenilemedi).")
    if d.auc is not None:
        print(f"AUC {d.auc:.3f} (%95 aralık {d.auc_alt:.3f}-{d.auc_ust:.3f}); kural {d.kural_auc:.3f}; "
              f"en riskli {d.ilk_sira_n} paketten yenilemeyen: {d.ilk_sira_birakan}.")
    print(f"Riskteki Para tahmini {bicim.para(d.tahmini_kayip)}, gerçekleşen kayıp {bicim.para(d.gercek_kayip)}.")
    for u in d.uyarilar:
        print(f"UYARI: {u}")
    print(f"Güncel liste: {len(g.skorlar)} aktif paket. Çıktılar: {cikti}")


if __name__ == "__main__":
    main()
