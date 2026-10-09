"""Command: today's risk list (skorlar.csv) from a firm's files, without a database or a validation report
(score command, K76-K80, `docs/adim-skor-tasarim.md`).

    python -m servisler.skor --kaynak <name> --paketler p.csv --girisler g.csv [g2.csv ...]
           [--esleme esleme.json] [--saat-dilimi Europe/Istanbul] [--cikti skorlar.csv]

Same input rules as `servisler.pilot_dogrula` (package and check-in files only, K30-K38 reading, mapping, whitelist
and sensitive columns) and the same computation (`pilot.guncel`, K68). Writes only skorlar.csv, with the data day
and model version on every row (K78). The file is replaced atomically, so a reader never sees a half-written list,
and on any error the previous list is left untouched (K79). Meant for a nightly run on the firm's own machine; the
Docker license package will wrap this command.
Does not import database/config, so it runs without .env and without PostgreSQL.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from analitik.soguk_baslangic import ASGARI_GECMIS_GUN, ASGARI_TEKRARLI_UYE
from servisler import pilot
from servisler.ice_aktarma import dis_kaynak_olustur
from servisler.pilot_dogrula import VARSAYILAN_DILIM, _hazirla, skorlar_csv


def _yaz(yol: Path, icerik: str) -> None:
    """Atomic replace: write a temporary file next to the target, then rename over it."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(yol.name + ".yaziliyor")
    gecici.write_text(icerik, encoding="utf-8-sig", newline="")   # rows already end in CRLF
    os.replace(gecici, yol)


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(prog="python -m servisler.skor",
                                description="Güncel risk listesi (skorlar.csv); veritabanı yok, rapor yok")
    a.add_argument("--kaynak", required=True, help="kısa ad (a-z, 0-9, _ -); pilotta kullanılanla aynı olmalı")
    a.add_argument("--paketler", required=True, metavar="DOSYA", help="paket dosyası (.csv veya .xlsx)")
    a.add_argument("--girisler", required=True, nargs="+", metavar="DOSYA",
                   help="giriş dosyası; 50.000 satırı aşıyorsa yıllara bölünmüş birden çok dosya")
    a.add_argument("--esleme", metavar="JSON", help='düzeltilmiş eşleştirme: {"paketler": {"alan": "Başlık"}}')
    a.add_argument("--saat-dilimi", default=VARSAYILAN_DILIM)
    a.add_argument("--cikti", type=Path, default=Path("skorlar.csv"), help="çıktı dosyası (varsayılan: skorlar.csv)")
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

    # Same order as the pilot command: check-ins first, the data day L is the "today" of the package status rule.
    girisler, _ = _hazirla("girisler", [Path(y) for y in arg.girisler], kullanici_esleme, arg.saat_dilimi,
                           datetime.now(dilim).date(), dis_kaynak)
    ziyaretler = pilot.ziyaret_gunleri(girisler, dilim)
    try:
        L = pilot.veri_gunu(ziyaretler, dilim)
        paketler, _ = _hazirla("paketler", [Path(arg.paketler)], kullanici_esleme, arg.saat_dilimi, L, dis_kaynak)
        g = pilot.guncel(ziyaretler, paketler, dilim)
    except (pilot.YetersizVeri, RuntimeError) as hata:              # RuntimeError: the fit did not converge
        raise SystemExit(f"HATA: {hata}")

    _yaz(arg.cikti, skorlar_csv(g))
    gecikme = (datetime.now(dilim).date() - L).days
    print(f"\nVeri günü {L:%d.%m.%Y}; model {g.model_versiyonu}; {len(g.skorlar)} aktif paket skorlandı, "
          f"{g.donduruldu} dondurulmuş paket atlandı. Çıktı: {arg.cikti}")
    if g.on_tahmin:
        print(f"NOT: veri az (en az {ASGARI_TEKRARLI_UYE} tekrar gelen üye ve {ASGARI_GECMIS_GUN} günlük geçmiş "
              "gerekir); liste diğer işletmelerden öğrenilmiş başlangıç bilgisiyle yapılmış bir ön tahmindir.")
    if gecikme > 2:
        print(f"UYARI: son giriş {gecikme} gün önce; dışa aktarma güncel mi?")


if __name__ == "__main__":
    main()
