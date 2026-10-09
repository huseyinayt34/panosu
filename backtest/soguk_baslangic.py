"""Cold start (step 8a, K84-K85; docs/adim-8a-tasarim.md). No database.

    python -m backtest.soguk_baslangic ogren        # learn the prior from the 5 [DEMO] businesses (synthetic)
    python -m backtest.soguk_baslangic degerlendir  # young-studio backtest: weak prior vs learned prior (S6)

`ogren` prints the Onsel to paste into analitik.soguk_baslangic.OGRENILMIS_ONSEL (a test checks they match).
`degerlendir` simulates a studio that opened h days before the cut-off C (S6 generator: only members acquired in
(C - h, C] exist) and scores the packages ending in (C, C + 60] with both priors; results are pooled over seeds.
"""

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np

from analitik import mbgnbd
from analitik.bgnbd import Onsel, parametreden_teta
from analitik.ozellikler import ozellik_cikar
from analitik.riskteki_para import yenileme_riskteki_para
from analitik.soguk_baslangic import OGRENILMIS_ONSEL, onsel_ogren, veri_yeterli
from analitik.yenileme import yenileme_olasiligi
from backtest import metrikler
from backtest.senaryolar import (
    KALIBRASYON_GUN, S6_GIRIS_SON_KULLANMA, S6_PAKETLER, S6_UYE_SAYISI, uret_s6,
)

# Same settings as sentetik.demo_kur.SENTETIK_AYARLARI (test) and the Butik Reformer defaults.
DEMO_REFERANS = date(2026, 10, 1)
DEMO_MUSTERI_SAYISI = 400
DEMO_GECMIS_GUN = 730
DEMO_TOHUMU = 42
_DILIM = ZoneInfo("Europe/Istanbul")
_GUN_SANIYE = 86_400.0

UFUK_GUN = 60                                  # packages ending in (C, C + 60], as in S6
# (label, members over the 730-day S6 window, studio ages in days). 1 500 = S6 default (about 2 new members a day).
DENEMELER = (("S6 hızında", S6_UYE_SAYISI, (20, 40, 60, 90)), ("küçük stüdyo", 300, (30, 60, 90, 180)))
TOHUM_SAYISI = 40


def _gunlere(ziyaretler: list[dict], referans: date) -> list[np.ndarray]:
    """Completed visits per member as days relative to the end of the reference day (as yenileme_servisi does)."""
    son = datetime.combine(referans + timedelta(days=1), time(0), tzinfo=_DILIM)
    uyeler: dict = {}
    for z in ziyaretler:
        if z["durum"] == "tamamlandi" and z["ziyaret_zamani"] < son:
            uyeler.setdefault(z["musteri_id"], []).append((z["ziyaret_zamani"] - son).total_seconds() / _GUN_SANIYE)
    return [np.sort(np.array(v)) for v in uyeler.values()]


def demo_isletmeleri() -> dict[str, list[np.ndarray]]:
    """Visit days of the 5 [DEMO] businesses, generated in memory (nothing is written anywhere)."""
    from sentetik import butik_reformer
    from sentetik.uretici import UretimAyarlari, uret

    veri = uret(UretimAyarlari(referans=DEMO_REFERANS, musteri_sayisi=DEMO_MUSTERI_SAYISI,
                               gecmis_gun=DEMO_GECMIS_GUN, tohum=DEMO_TOHUMU))
    sonuc = {i.profil.isletme_adi: _gunlere(i.ziyaretler, DEMO_REFERANS) for i in veri.isletmeler}
    sonuc[butik_reformer.ISLETME_ADI] = _gunlere(butik_reformer.uret().ziyaretler, butik_reformer.BUGUN)
    return sonuc


def ogren() -> tuple[Onsel, dict[str, np.ndarray]]:
    """Per-business MAP (weak prior) on all history, then the empirical Bayes prior (K84)."""
    tetalar = {}
    for ad, zamanlar in demo_isletmeleri().items():
        oz = ozellik_cikar(zamanlar, zamanlar, 0.0)
        tetalar[ad] = parametreden_teta(mbgnbd.fit(oz.x, oz.t_x, oz.T))
    return onsel_ogren(np.array(list(tetalar.values()))), tetalar


@dataclass
class GencStudyoSonucu:
    etiket: str
    yas_gun: int
    tohum_sayisi: int
    paket: int
    yenileme_orani: float
    on_tahmin_orani: float                     # share of seeds below the data threshold
    tekrarli_uye: float                        # mean members with a repeat visit at C
    auc: dict[str, float | None]               # pooled over seeds; keys "zayıf", "öğrenilmiş"
    brier: dict[str, float]
    rp_hata_yuzde: dict[str, float | None]     # Riskteki Para vs realized loss, pooled


def genc_studyo(etiket: str, uye_sayisi: int, yas_gun: int, tohumlar, onsel: Onsel) -> GencStudyoSonucu:
    """S6 studio that opened yas_gun days before C; both priors on the same data, pooled over seeds."""
    C = KALIBRASYON_GUN
    p = {"zayıf": [], "öğrenilmiş": []}
    y, fiyatlar, on_tahmin, tekrarli = [], [], 0, []
    tohumlar = list(tohumlar)
    for tohum in tohumlar:
        veri = uret_s6(np.random.default_rng([7, uye_sayisi, yas_gun, tohum]), uye_sayisi)
        secim = np.flatnonzero((veri.edinim > C - yas_gun) & (veri.edinim <= C))
        if len(secim) == 0:
            continue
        kal = [veri.zamanlar[i][veri.zamanlar[i] <= C] for i in secim]
        oz = ozellik_cikar(kal, kal, C)
        on_tahmin += not veri_yeterli(oz.x, oz.T)
        tekrarli.append(int(np.sum(oz.x >= 1)))
        uyumlar = {"zayıf": mbgnbd.fit(oz.x, oz.t_x, oz.T), "öğrenilmiş": mbgnbd.fit(oz.x, oz.t_x, oz.T, onsel=onsel)}
        sira = {int(u): k for k, u in enumerate(secim)}
        for pk in veri.paketler:
            if pk.uye not in sira or not (pk.baslangic <= C < pk.bitis <= C + UFUK_GUN):
                continue
            k = sira[pk.uye]
            _, tur, _, _, hak, fiyat = S6_PAKETLER[pk.tur_no]
            if tur == "sure":
                pencere, kalan = pk.bitis - C, None
            else:
                z = kal[k]
                ilk = pk.baslangic == veri.edinim[pk.uye]
                kullanilan = int(np.sum(z >= pk.baslangic)) if ilk else int(np.sum(z > pk.baslangic))
                pencere, kalan = pk.baslangic + S6_GIRIS_SON_KULLANMA - C, hak - kullanilan
            for ad, prm in uyumlar.items():
                p[ad].append(yenileme_olasiligi(prm, oz.x[k], oz.t_x[k], oz.T[k], pencere_gun=pencere,
                                                kalan_hak=kalan).p_yenileme)
            y.append(int(pk.yeniledi))
            fiyatlar.append(Decimal(fiyat))
    y_dizi = np.array(y)
    gercek_kayip = sum((f for f, r in zip(fiyatlar, y) if not r), Decimal(0))

    def rp_hata(olasiliklar):
        rp = sum((yenileme_riskteki_para(Decimal(str(round(q, 4))), f) for q, f in zip(olasiliklar, fiyatlar)),
                 Decimal(0))
        return float((rp - gercek_kayip) / gercek_kayip * 100) if gercek_kayip else None

    return GencStudyoSonucu(
        etiket=etiket, yas_gun=yas_gun, tohum_sayisi=len(tohumlar), paket=len(y),
        yenileme_orani=float(y_dizi.mean()) if len(y) else float("nan"),
        on_tahmin_orani=on_tahmin / len(tohumlar), tekrarli_uye=float(np.mean(tekrarli)) if tekrarli else 0.0,
        auc={ad: metrikler.auc(np.array(q), y_dizi) for ad, q in p.items()},
        brier={ad: metrikler.brier(np.array(q), y_dizi) for ad, q in p.items()},
        rp_hata_yuzde={ad: rp_hata(q) for ad, q in p.items()},
    )


def _onsel_metni(onsel: Onsel) -> str:
    def demet(d):
        return "(" + ", ".join(f"{v:.4f}" for v in d) + ")"
    return f"OGRENILMIS_ONSEL = Onsel(\n    merkez={demet(onsel.merkez)},\n    sapma={demet(onsel.sapma)},\n)"


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(prog="python -m backtest.soguk_baslangic", description=__doc__.splitlines()[0])
    a.add_argument("komut", choices=("ogren", "degerlendir"))
    a.add_argument("--tohum-sayisi", type=int, default=TOHUM_SAYISI)
    arg = a.parse_args(argv)
    if arg.komut == "ogren":
        onsel, tetalar = ogren()
        print("θ = (ln m, ln r, logit μ, ln κ) per business (MAP, weak prior):")
        for ad, t in tetalar.items():
            print(f"  {ad:<34} " + "  ".join(f"{v:8.4f}" for v in t))
        print(_onsel_metni(onsel))
        return
    print("| Stüdyo | Yaş (gün) | Paket | Yenileme oranı | Ön tahmin payı | Tekrarlı üye | AUC zayıf / öğrenilmiş "
          "| Brier zayıf / öğrenilmiş | Riskteki Para hatası % zayıf / öğrenilmiş |")
    print("|---|---|---|---|---|---|---|---|---|")
    for etiket, uye_sayisi, yaslar in DENEMELER:
        for yas in yaslar:
            s = genc_studyo(etiket, uye_sayisi, yas, range(arg.tohum_sayisi), OGRENILMIS_ONSEL)

            def iki(d, bicim):
                return " / ".join("—" if d[k] is None else bicim.format(d[k]) for k in ("zayıf", "öğrenilmiş"))
            print(f"| {s.etiket} | {s.yas_gun} | {s.paket} | {s.yenileme_orani:.2f} | {s.on_tahmin_orani:.0%} | "
                  f"{s.tekrarli_uye:.0f} | {iki(s.auc, '{:.3f}')} | {iki(s.brier, '{:.3f}')} | "
                  f"{iki(s.rp_hata_yuzde, '{:+.0f}')} |", flush=True)


if __name__ == "__main__":
    main()
