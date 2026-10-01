"""Backtest: tüm senaryolar × tohumlar; M0 (V1), M1 (BG/NBD) ve M3 (MBG/NBD) karşılaştırması, ciro için M2 (Gamma-Gamma).

    python -m backtest                       # S0–S5 × 20 tohum × 2 000 müşteri, S6 × 20 tohum × 1 500 üye
    python -m backtest --tohum-sayisi 2      # hızlı deneme

Çıktı: docs/backtest-sonuclari.md (tablolar) ve raporlar/backtest/*.csv (ham sonuçlar, commit'lenmez).
Veritabanına dokunmaz.
"""

import argparse
import csv
import time
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np

from decimal import Decimal

from analitik import bgnbd, gamma_gamma, mbgnbd, v1
from analitik.riskteki_para import yenileme_riskteki_para
from analitik.yenileme import tohum_turet, yenileme_olasiligi
from analitik.ozellikler import ozellik_cikar
from backtest import metrikler
from backtest.senaryolar import (
    GERCEK_BGNBD, GERCEK_GG, GOZLEM_GUN, GRUPLU_SENARYOLAR, KALIBRASYON_GUN, MUSTERI_SAYISI, S1_ARALIK_SEKLI,
    S1_MU_ORTALAMA, S1_MU_SEKLI, S2_GRUPLARI, S3_OMUR_ORTALAMA, S4_SEPET_CARPANI, S5_MU_ORTALAMA, S5_ORTALAMA_SEPET,
    S5_TEK_SEFERLIK_ORANI, S6_GIRIS_SON_KULLANMA, S6_MU_ORTALAMA, S6_PAKETLER, S6_UYE_SAYISI, S6_YENILEME_ORANI,
    SENARYO_ACIKLAMA, SENARYOLAR, TEK_SEFERLIK, uret, uret_s6,
)

TOHUM_SAYISI = 20
BEKLEME_GUN = GOZLEM_GUN - KALIBRASYON_GUN
MD_YOLU = Path("docs/backtest-sonuclari.md")
HAM_DIZIN = Path("raporlar/backtest")
TUMU = "tumu"
OLASILIK_MODELLERI = ("M0", "M1", "M3")
SAYIM_MODELLERI = ("M1", "M3")          # bekleme dönemi ziyaret tahmini üreten modeller; ciro = model + M2
_SENARYO_NO = {kod: i for i, kod in enumerate(SENARYOLAR)}
S6 = "S6"
S6_UFUK_GUN = 60                        # kalibrasyon tarihinde aktif ve 60 gün içinde biten paketler
S6_KURAL_PENCERE_GUN = 21               # kural tabanı: son 21 günde en fazla 1 giriş → yenilemez
S6_MODELLER = ("M3-sim", "kural")


@dataclass
class KosuSonucu:
    metrikler: list[dict] = field(default_factory=list)       # senaryo, tohum, segment, model, metrik, deger
    guvenilirlik: list[dict] = field(default_factory=list)    # senaryo, tohum, model, kutu, n, toplam_tahmin, toplam_gercek


def kos(kod: str, tohum: int, musteri_sayisi: int = MUSTERI_SAYISI) -> KosuSonucu:
    """Tek senaryo × tek tohum."""
    rng = np.random.default_rng([_SENARYO_NO[kod], tohum])
    veri = uret(kod, rng, musteri_sayisi)

    # Değerlendirmeye kalibrasyon sonundan önce edinilmiş müşteriler girer.
    secim = np.flatnonzero(veri.edinim <= KALIBRASYON_GUN)
    zam = [veri.zamanlar[i] for i in secim]
    tut = [veri.tutarlar[i] for i in secim]
    kal_zam = [z[z <= KALIBRASYON_GUN] for z in zam]
    kal_tut = [t[z <= KALIBRASYON_GUN] for z, t in zip(zam, tut)]
    hayatta = (veri.olum[secim] > KALIBRASYON_GUN).astype(int)
    grup = veri.grup[secim]
    gercek_ziyaret = np.array([np.sum(z > KALIBRASYON_GUN) for z in zam], dtype=float)
    gercek_ciro = np.array([t[z > KALIBRASYON_GUN].sum() for z, t in zip(zam, tut)])

    # Modeller yalnızca kalibrasyon verisiyle eğitilir.
    oz = ozellik_cikar(kal_zam, kal_tut, KALIBRASYON_GUN)
    bg = bgnbd.fit(oz.x, oz.t_x, oz.T)
    mbg = mbgnbd.fit(oz.x, oz.t_x, oz.T)
    gg = gamma_gamma.fit(oz.x, oz.m)
    sepet = gamma_gamma.beklenen_sepet(gg, oz.x, oz.m)
    p_hayatta = {
        "M0": v1.p_hayatta_toplu(kal_zam, KALIBRASYON_GUN),
        "M1": bgnbd.p_hayatta(bg, oz.x, oz.t_x, oz.T),
        "M3": mbgnbd.p_hayatta(mbg, oz.x, oz.t_x, oz.T),
    }
    tahmin_ziyaret = {
        "M1": bgnbd.beklenen_ziyaret(bg, BEKLEME_GUN, oz.x, oz.t_x, oz.T),
        "M3": mbgnbd.beklenen_ziyaret(mbg, BEKLEME_GUN, oz.x, oz.t_x, oz.T),
    }

    s = KosuSonucu()

    def ekle(segment, model, metrik, deger):
        s.metrikler.append({"senaryo": kod, "tohum": tohum, "segment": segment, "model": model,
                            "metrik": metrik, "deger": deger})

    segmentler = [TUMU] + (sorted(set(grup)) if kod in GRUPLU_SENARYOLAR else [])
    for seg in segmentler:
        m = np.ones(len(grup), bool) if seg == TUMU else grup == seg
        ekle(seg, "veri", "musteri", int(m.sum()))
        ekle(seg, "veri", "olu_orani", float(1 - hayatta[m].mean()))
        for model in OLASILIK_MODELLERI:
            p = p_hayatta[model]
            ekle(seg, model, "auc", metrikler.auc(p[m], hayatta[m]))
            ekle(seg, model, "brier", metrikler.brier(p[m], hayatta[m]))
            ekle(seg, model, "ort_p_hayatta", float(p[m].mean()))
        for model in SAYIM_MODELLERI:
            ziyaret, ciro = tahmin_ziyaret[model][m], tahmin_ziyaret[model][m] * sepet[m]
            ekle(seg, model, "ziyaret_mae", metrikler.mae(ziyaret, gercek_ziyaret[m]))
            ekle(seg, model, "ziyaret_toplam_hata_yuzde", metrikler.toplam_hata_yuzde(ziyaret, gercek_ziyaret[m]))
            ekle(seg, f"{model}+M2", "ciro_mae", metrikler.mae(ciro, gercek_ciro[m]))
            ekle(seg, f"{model}+M2", "ciro_toplam_hata_yuzde", metrikler.toplam_hata_yuzde(ciro, gercek_ciro[m]))

    ekle(TUMU, "M2", "bagimsizlik_korelasyonu", gamma_gamma.bagimsizlik_tanisi(oz.x, oz.m))
    # Ek bilgi: x edinim süresiyle karışır; günlük sıklık x/T ile de raporlanır.
    ekle(TUMU, "M2", "bagimsizlik_korelasyonu_x_T", gamma_gamma.bagimsizlik_tanisi(oz.x / oz.T, oz.m))
    for model, prm in (("M1", bg), ("M3", mbg)):
        for ad, deger in zip(("r", "alfa", "a", "b"), prm.dizi()):
            ekle(TUMU, model, f"param_{ad}", float(deger))
        ekle(TUMU, model, "param_a_oran", prm.a / (prm.a + prm.b))      # E[p] = a/(a+b)
    for ad, deger in zip(("p", "q", "gamma"), gg.dizi()):
        ekle(TUMU, "M2", f"param_{ad}", float(deger))

    for model in OLASILIK_MODELLERI:
        p = p_hayatta[model]
        for k, kutu in enumerate(metrikler.guvenilirlik_tablosu(p, hayatta)):
            secili = np.minimum((p * metrikler.KUTU_SAYISI).astype(int), metrikler.KUTU_SAYISI - 1) == k
            s.guvenilirlik.append({"senaryo": kod, "tohum": tohum, "model": model, "kutu": k, "n": kutu.n,
                                   "toplam_tahmin": float(p[secili].sum()), "toplam_gercek": int(hayatta[secili].sum())})
    return s


def kos_s6(tohum: int, uye_sayisi: int = S6_UYE_SAYISI) -> KosuSonucu:
    """S6 "Stüdyo": kalibrasyon tarihinde (C) aktif ve 60 gün içinde biten paketlerin yenilenip yenilenmediği.

    Model (M3-sim): C'ye kadarki ziyaretlerle MBG/NBD tahmini + analitik.yenileme simülasyonu.
    Kural tabanı: (C − 21, C] içinde en fazla 1 giriş → yenilemez (skor 0), aksi hâlde yeniler (skor 1).
    """
    rng = np.random.default_rng([_SENARYO_NO.get(S6, len(SENARYOLAR)), tohum])
    veri = uret_s6(rng, uye_sayisi)
    C = KALIBRASYON_GUN

    secim = np.flatnonzero(veri.edinim <= C)
    kal_zam = [veri.zamanlar[i][veri.zamanlar[i] <= C] for i in secim]
    oz = ozellik_cikar(kal_zam, kal_zam, C)
    prm = mbgnbd.fit(oz.x, oz.t_x, oz.T)
    sira = {int(u): k for k, u in enumerate(secim)}

    satirlar = []
    for no, pk in enumerate(veri.paketler):
        if not (pk.baslangic <= C < pk.bitis <= C + S6_UFUK_GUN):
            continue
        k = sira[pk.uye]
        ad, tur, _, _, hak, fiyat = S6_PAKETLER[pk.tur_no]
        if tur == "sure":
            pencere, kalan = pk.bitis - C, None
        else:
            z = kal_zam[k]
            kullanilan = int(np.sum(z >= pk.baslangic)) if pk.baslangic == veri.edinim[pk.uye] else int(np.sum(z > pk.baslangic))
            pencere, kalan = pk.baslangic + S6_GIRIS_SON_KULLANMA - C, hak - kullanilan
        sonuc = yenileme_olasiligi(prm, oz.x[k], oz.t_x[k], oz.T[k], pencere_gun=pencere, kalan_hak=kalan,
                                   tohum=tohum_turet(_s6_paket_kimligi(tohum, no), _S6_HESAPLAMA_TARIHI))
        son_21 = int(np.sum(kal_zam[k] > C - S6_KURAL_PENCERE_GUN))
        satirlar.append((ad, sonuc.p_yenileme, 0.0 if son_21 <= 1 else 1.0, int(pk.yeniledi), Decimal(fiyat)))

    s = KosuSonucu()

    def ekle(segment, model, metrik, deger):
        s.metrikler.append({"senaryo": S6, "tohum": tohum, "segment": segment, "model": model,
                            "metrik": metrik, "deger": deger})

    for seg in [TUMU] + [pk[0] for pk in S6_PAKETLER]:
        sec = [r for r in satirlar if seg == TUMU or r[0] == seg]
        if not sec:
            continue
        y = np.array([r[3] for r in sec])
        gercek_kayip = sum((r[4] for r in sec if not r[3]), Decimal(0))
        ekle(seg, "veri", "paket", len(sec))
        ekle(seg, "veri", "yenileme_orani", float(y.mean()))
        ekle(seg, "veri", "gercek_kayip_ciro", float(gercek_kayip))
        for model, sutun in zip(S6_MODELLER, (1, 2)):
            skor = np.array([r[sutun] for r in sec])
            ekle(seg, model, "auc", metrikler.auc(skor, y))
            ekle(seg, model, "brier", metrikler.brier(skor, y))
            rp = sum((yenileme_riskteki_para(Decimal(str(round(r[sutun], 4))), r[4]) for r in sec), Decimal(0))
            ekle(seg, model, "riskteki_para", float(rp))
            ekle(seg, model, "rp_hata_yuzde",
                 float((rp - gercek_kayip) / gercek_kayip * 100) if gercek_kayip else None)
    return s


_S6_HESAPLAMA_TARIHI = date(2026, 1, 1)      # tohum türetimi için sabit yer tutucu (sentetik zaman takvimsizdir)


def _s6_paket_kimligi(tohum: int, no: int) -> uuid.UUID:
    return uuid.UUID(int=(tohum << 32) | no)


def calistir(
    tohumlar: Iterable[int] = range(TOHUM_SAYISI),
    musteri_sayisi: int = MUSTERI_SAYISI,
    senaryolar: Iterable[str] = (*SENARYOLAR, "S6"),
    ilerleme: bool = False,
    s6_uye_sayisi: int = S6_UYE_SAYISI,
) -> KosuSonucu:
    toplam = KosuSonucu()
    tohumlar = list(tohumlar)
    for kod in senaryolar:
        basla = time.perf_counter()
        for tohum in tohumlar:
            s = kos_s6(tohum, s6_uye_sayisi) if kod == S6 else kos(kod, tohum, musteri_sayisi)
            toplam.metrikler += s.metrikler
            toplam.guvenilirlik += s.guvenilirlik
        if ilerleme:
            print(f"{kod}: {len(tohumlar)} tohum, {time.perf_counter() - basla:.1f} sn")
    return toplam


# ---------------------------------------------------------------------------------------------
# Çıktılar
# ---------------------------------------------------------------------------------------------
def ham_csv_yaz(sonuc: KosuSonucu, dizin: Path) -> None:
    dizin.mkdir(parents=True, exist_ok=True)
    for ad, satirlar in (("metrikler.csv", sonuc.metrikler), ("guvenilirlik.csv", sonuc.guvenilirlik)):
        if not satirlar:                       # ör. yalnız S6 koşusunda güvenilirlik tablosu yok
            continue
        with open(dizin / ad, "w", newline="", encoding="utf-8") as f:
            yazici = csv.DictWriter(f, fieldnames=list(satirlar[0]))
            yazici.writeheader()
            yazici.writerows(satirlar)


def ozetle(sonuc: KosuSonucu) -> dict[tuple[str, str, str, str], tuple[float, float, int]]:
    """(senaryo, segment, model, metrik) → (ortalama, standart sapma, geçerli tohum sayısı). None'lar atlanır."""
    degerler: dict[tuple, list[float]] = defaultdict(list)
    for m in sonuc.metrikler:
        if m["deger"] is not None:
            degerler[(m["senaryo"], m["segment"], m["model"], m["metrik"])].append(float(m["deger"]))
    return {k: (float(np.mean(v)), float(np.std(v, ddof=1)) if len(v) > 1 else 0.0, len(v)) for k, v in degerler.items()}


def _ort_sd(ozet, anahtar, bicim="{:.3f}") -> str:
    if anahtar not in ozet:
        return "—"
    ort, sd, _ = ozet[anahtar]
    return f"{bicim.format(ort)} ± {bicim.replace('+', '').format(sd)}"


def _segmentler(kod: str) -> list[str]:
    if kod in ("S2", "S4"):
        return [g[0] for g in S2_GRUPLARI]
    if kod == "S5":
        return ["duzenli", TEK_SEFERLIK]
    return []


def markdown_uret(sonuc: KosuSonucu, tohum_sayisi: int, musteri_sayisi: int) -> str:
    ozet = ozetle(sonuc)
    senaryolar = [k for k in SENARYOLAR if any(m["senaryo"] == k for m in sonuc.metrikler)]
    s6_var = any(m["senaryo"] == S6 for m in sonuc.metrikler)
    gruplu = [k for k in senaryolar if k in GRUPLU_SENARYOLAR]
    y = []
    y.append("# Backtest sonuçları (Adım 6)\n")
    y.append("`python -m backtest` tarafından üretilir; elle düzenlenmez. Tasarım: `docs/adim-5-6-tasarim.md`.\n")
    y.append("Modeller: M0 = V1 (aralık ~ Normal), M1 = BG/NBD, M3 = MBG/NBD; ciro tahmininde sepet M2 (Gamma-Gamma).\n")
    y.append(f"- Senaryo başına {tohum_sayisi} tohum × {musteri_sayisi} müşteri; gözlem {GOZLEM_GUN:.0f} gün, "
             f"kalibrasyon ilk {KALIBRASYON_GUN:.1f} gün (18 ay), bekleme son {BEKLEME_GUN:.1f} gün (6 ay).")
    y.append("- Değerlendirmeye kalibrasyon sonundan önce edinilmiş müşteriler girer. Etiket: kalibrasyon sonunda "
             "gerçekten hayatta mı.")
    y.append("- Değerler tohumlar üzerinden ortalama ± standart sapma.\n")

    y.append("## Varsayımlar (belgede sayısı verilmeyen değerler)\n")
    y.append(f"- BG/NBD gerçek parametreleri (S0; S1/S2/S4/S5'te bırakma Beta'sı, S3'te λ Gamma'sı): katalogdaki berber "
             f"profili, r = {GERCEK_BGNBD.r:g}, α = {GERCEK_BGNBD.alfa:g}, a = {GERCEK_BGNBD.a:g}, b = {GERCEK_BGNBD.b:g}.")
    y.append(f"- Harcama (tüm senaryolar): Gamma-Gamma, p = {GERCEK_GG.p:g}, q = {GERCEK_GG.q:g}, "
             f"γ = {GERCEK_GG.gamma:g} (ortalama sepet {GERCEK_GG.populasyon_ortalamasi:.0f} TL; S5'te "
             f"{S5_ORTALAMA_SEPET:.0f} TL'ye ölçeklenir).")
    y.append(f"- S1: μ_i ~ Gamma(şekil {S1_MU_SEKLI:g}, ortalama {S1_MU_ORTALAMA:g} g); aralık ~ Gamma(k = {S1_ARALIK_SEKLI:g}).")
    y.append("- S2/S4: grup içinde μ sabit (" + ", ".join(
        f"{g} %{o * 100:.0f}" + (f" μ={mu:g} g" if mu else "") for g, o, mu in S2_GRUPLARI)
             + "); bırakma S1'deki gibi (her tekrar ziyaretten sonra p ~ Beta(a, b)); tek seferlik müşteri ilk "
               "ziyaret anında kaybolur.")
    y.append(f"- S3: ömür ~ Üstel(ortalama {S3_OMUR_ORTALAMA:g} g), edinimden itibaren.")
    y.append("- S4 sepet çarpanları: " + ", ".join(f"{g} ×{c:g}" for g, c in S4_SEPET_CARPANI.items()) + ".")
    y.append(f"- S5 (HİPOTEZ): %{S5_TEK_SEFERLIK_ORANI * 100:.0f} tek seferlik (ilk ziyaret anında kaybolur); kalanlar "
             f"S1'deki gibi düzenli, μ_i ~ Gamma(şekil {S1_MU_SEKLI:g}, ortalama {S5_MU_ORTALAMA:g} g), bırakma S1'deki gibi.")
    y.append("- Bağımsızlık tanısı: tekrar ziyaretli müşterilerde x (tekrar ziyaret sayısı) ile m̄ arasında Pearson.\n")

    y.append("## Senaryolar\n")
    y.append("| Kod | Ne bozulur | Değerlendirilen müşteri | Gerçek ölü oranı |")
    y.append("|---|---|---|---|")
    for k in senaryolar:
        y.append(f"| {k} | {SENARYO_ACIKLAMA[k]} | {_ort_sd(ozet, (k, TUMU, 'veri', 'musteri'), '{:.0f}')} "
                 f"| {_ort_sd(ozet, (k, TUMU, 'veri', 'olu_orani'))} |")

    y.append("\n## Ayrım gücü ve kalibrasyon: M0, M1, M3\n")
    y.append("Tek seferlik satırları yalnızca o grubun müşterileridir; grubun hepsi ölü olduğundan AUC tanımsızdır (—), "
             "Brier = ortalama P(hayatta)².\n")
    y.append("| Senaryo | M0 AUC | M1 AUC | M3 AUC | M0 Brier | M1 Brier | M3 Brier |")
    y.append("|---|---|---|---|---|---|---|")

    def satir(etiket, k, seg):
        return (f"| {etiket} | " + " | ".join(_ort_sd(ozet, (k, seg, mo, "auc")) for mo in OLASILIK_MODELLERI)
                + " | " + " | ".join(_ort_sd(ozet, (k, seg, mo, "brier")) for mo in OLASILIK_MODELLERI) + " |")

    for k in senaryolar:
        y.append(satir(k, k, TUMU))
    for k in gruplu:
        y.append(satir(f"{k} · tek seferlik", k, TEK_SEFERLIK))

    y.append("\n## Bekleme dönemi tahmini: ziyaret (M1, M3) ve ciro (+ M2)\n")
    y.append("M0 ziyaret/ciro tahmini üretmez (belgede tanımı yok).\n")
    y.append("| Senaryo | M1 ziyaret MAE | M3 ziyaret MAE | M1 ziyaret toplam hata % | M3 ziyaret toplam hata % "
             "| M1+M2 ciro MAE (TL) | M3+M2 ciro MAE (TL) | M1+M2 ciro toplam hata % | M3+M2 ciro toplam hata % |")
    y.append("|---|---|---|---|---|---|---|---|---|")
    for k in senaryolar:
        y.append(f"| {k} | " + " | ".join([
            _ort_sd(ozet, (k, TUMU, "M1", "ziyaret_mae"), "{:.2f}"),
            _ort_sd(ozet, (k, TUMU, "M3", "ziyaret_mae"), "{:.2f}"),
            _ort_sd(ozet, (k, TUMU, "M1", "ziyaret_toplam_hata_yuzde"), "{:+.1f}"),
            _ort_sd(ozet, (k, TUMU, "M3", "ziyaret_toplam_hata_yuzde"), "{:+.1f}"),
            _ort_sd(ozet, (k, TUMU, "M1+M2", "ciro_mae"), "{:.0f}"),
            _ort_sd(ozet, (k, TUMU, "M3+M2", "ciro_mae"), "{:.0f}"),
            _ort_sd(ozet, (k, TUMU, "M1+M2", "ciro_toplam_hata_yuzde"), "{:+.1f}"),
            _ort_sd(ozet, (k, TUMU, "M3+M2", "ciro_toplam_hata_yuzde"), "{:+.1f}"),
        ]) + " |")

    if "S0" in senaryolar:
        y.append("\n## Parametre geri kazanımı (S0)\n")
        y.append("S0 BG/NBD ile üretilir; M3 (MBG/NBD) burada yanlış belirlenmiş modeldir (ilk ziyaret sonrası bırakma "
                 "fırsatı sayar), bu yüzden a/(a+b) sistematik olarak düşük çıkması beklenir.\n")
        y.append("| Parametre | Gerçek | Tahmin | Ortalama göreli hata |")
        y.append("|---|---|---|---|")
        a_oran = GERCEK_BGNBD.a / (GERCEK_BGNBD.a + GERCEK_BGNBD.b)
        kaynaklar = [("M1", ad, deger) for ad, deger in zip(("r", "alfa", "a", "b"), GERCEK_BGNBD.dizi())]
        kaynaklar += [("M1", "a_oran", a_oran)]
        kaynaklar += [("M3", ad, deger) for ad, deger in (("r", GERCEK_BGNBD.r), ("alfa", GERCEK_BGNBD.alfa),
                                                          ("a_oran", a_oran))]
        kaynaklar += [("M2", ad, deger) for ad, deger in zip(("p", "q", "gamma"), GERCEK_GG.dizi())]
        for model, ad, gercek in kaynaklar:
            tahminler = [float(m["deger"]) for m in sonuc.metrikler
                         if m["senaryo"] == "S0" and m["model"] == model and m["metrik"] == f"param_{ad}"]
            hata = np.mean([metrikler.goreli_hata(t, gercek) for t in tahminler])
            etiket = "a/(a+b)" if ad == "a_oran" else ad
            y.append(f"| {model} {etiket} | {gercek:g} | {_ort_sd(ozet, ('S0', TUMU, model, f'param_{ad}'))} "
                     f"| %{hata * 100:.1f} |")

    y.append("\n## Gamma-Gamma bağımsızlık tanısı (Pearson, tekrar ziyaretli müşteriler)\n")
    y.append("Tanı fonksiyonu x ile m̄ arasındadır; x/T sütunu ek bilgidir (x edinim süresiyle karışır).\n")
    y.append("| Senaryo | x ile m̄ | x/T ile m̄ |")
    y.append("|---|---|---|")
    for k in senaryolar:
        y.append(f"| {k} | {_ort_sd(ozet, (k, TUMU, 'M2', 'bagimsizlik_korelasyonu'))} "
                 f"| {_ort_sd(ozet, (k, TUMU, 'M2', 'bagimsizlik_korelasyonu_x_T'))} |")

    for k in gruplu:
        y.append(f"\n## Segment kırılımı ({k})\n")
        y.append("AUC, tek sınıflı segmentte (ör. tek seferlik müşterilerin hepsi ölü) tanımsızdır: —.\n")
        y.append("| Segment | Müşteri | Ölü oranı | Ort. P(hayatta) M0 / M1 / M3 | M0 AUC | M1 AUC | M3 AUC "
                 "| M0 Brier | M1 Brier | M3 Brier | Ziyaret toplam hata % M1 / M3 | Ciro toplam hata % M1 / M3 |")
        y.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for g in _segmentler(k):
            ort_p = " / ".join(f"{ozet[(k, g, mo, 'ort_p_hayatta')][0]:.3f}" if (k, g, mo, "ort_p_hayatta") in ozet
                               else "—" for mo in OLASILIK_MODELLERI)
            y.append(f"| {g} | {_ort_sd(ozet, (k, g, 'veri', 'musteri'), '{:.0f}')} "
                     f"| {_ort_sd(ozet, (k, g, 'veri', 'olu_orani'))} | {ort_p} | "
                     + " | ".join(_ort_sd(ozet, (k, g, mo, "auc")) for mo in OLASILIK_MODELLERI) + " | "
                     + " | ".join(_ort_sd(ozet, (k, g, mo, "brier")) for mo in OLASILIK_MODELLERI)
                     + f" | {_ort_sd(ozet, (k, g, 'M1', 'ziyaret_toplam_hata_yuzde'), '{:+.1f}')} / "
                       f"{_ort_sd(ozet, (k, g, 'M3', 'ziyaret_toplam_hata_yuzde'), '{:+.1f}')} "
                       f"| {_ort_sd(ozet, (k, g, 'M1+M2', 'ciro_toplam_hata_yuzde'), '{:+.1f}')} / "
                       f"{_ort_sd(ozet, (k, g, 'M3+M2', 'ciro_toplam_hata_yuzde'), '{:+.1f}')} |")

    y.append("\n## Güvenilirlik tabloları (tüm tohumlar birleştirilmiş)\n")
    y.append("Her kutu: müşteri sayısı, tahmin edilen ortalama P(hayatta), gerçek hayatta oranı.\n")
    birikim: dict[tuple, list[float]] = defaultdict(lambda: [0, 0.0, 0])
    for g in sonuc.guvenilirlik:
        b = birikim[(g["senaryo"], g["model"], g["kutu"])]
        b[0] += g["n"]
        b[1] += g["toplam_tahmin"]
        b[2] += g["toplam_gercek"]
    for k in senaryolar:
        y.append(f"\n### {k}\n")
        y.append("| Kutu | " + " | ".join(f"{mo} n | {mo} tahmin | {mo} gerçek" for mo in OLASILIK_MODELLERI) + " |")
        y.append("|---|" + "---|---|---|" * len(OLASILIK_MODELLERI))
        for kutu in range(metrikler.KUTU_SAYISI):
            hucreler = []
            for model in OLASILIK_MODELLERI:
                n, tahmin, gercek = birikim[(k, model, kutu)]
                hucreler += [str(n), f"{tahmin / n:.3f}" if n else "—", f"{gercek / n:.3f}" if n else "—"]
            y.append(f"| [{kutu / 10:.1f}, {(kutu + 1) / 10:.1f}) | " + " | ".join(hucreler) + " |")
    if s6_var:
        y += _s6_markdown(ozet, tohum_sayisi)
    return "\n".join(y) + "\n"


def _s6_markdown(ozet, tohum_sayisi: int) -> list[str]:
    y = ["\n## S6 \"Stüdyo\": yenileme riski (Adım 5b)\n"]
    y.append(f"- {tohum_sayisi} tohum × {S6_UYE_SAYISI} üye, 2 yıl. Değerlendirme: kalibrasyon tarihinde "
             f"({KALIBRASYON_GUN:.1f}. gün) aktif olan ve {S6_UFUK_GUN} gün içinde biten paketler.")
    y.append("- Paket karışımı (HİPOTEZ): " + ", ".join(
        f"{ad} %{oran * 100:.0f} ({fiyat} TL)" for ad, _, oran, _, _, fiyat in S6_PAKETLER)
             + f"; giriş paketi {S6_GIRIS_SON_KULLANMA:g} gün sonra biter (hak kalsa da).")
    y.append(f"- Katılım: düzenli aralıklar (Gamma k = {S1_ARALIK_SEKLI:g}), μ_i ~ Gamma(şekil {S1_MU_SEKLI:g}, ortalama "
             f"{S6_MU_ORTALAMA:g} g); bırakma MBG/NBD tarzı, ilk ziyaret dahil her ziyaretten sonra p ~ Beta("
             f"{GERCEK_BGNBD.a:g}, {GERCEK_BGNBD.b:g}).")
    y.append(f"- Gerçek yenileme: paket bittiğinde hayatta olan üye %{S6_YENILEME_ORANI * 100:.0f} olasılıkla aynı türü "
             "yeniler; hayatta olmayan yenilemez.")
    y.append("- M3-sim = MBG/NBD + sonsal simülasyon (`analitik/yenileme.py`, N = 2 000). Kural = son 21 günde en fazla "
             "1 giriş → yenilemez (0/1 skor).")
    y.append("- Riskteki Para hata % = (Σ (1 − P(yenileme)) × fiyat − gerçekleşen kayıp ciro) / gerçekleşen kayıp ciro; "
             "gerçekleşen kayıp = yenilenmeyen paketlerin fiyat toplamı.")
    y.append("- Bilinen sınırlamalar: M3, S5'te gelecekteki ziyaretleri ~%11 fazla tahmin etti, simülasyon aynı eğilimi "
             "taşıyabilir. Fiyat, kampanya, taşınma gibi davranış dışı yenileme nedenleri modelde yok (S6'da %10 olarak "
             "üretilir). Model gerçek yenileme verisiyle kalibre edilmedi (5c).\n")
    y.append("| Segment | Paket | Yenileme oranı | M3-sim AUC | Kural AUC | M3-sim Brier | Kural Brier "
             "| Gerçek kayıp (TL) | M3-sim Riskteki Para hata % | Kural Riskteki Para hata % |")
    y.append("|---|---|---|---|---|---|---|---|---|---|")
    for seg in [TUMU] + [pk[0] for pk in S6_PAKETLER]:
        etiket = "Tümü" if seg == TUMU else seg
        y.append(f"| {etiket} | {_ort_sd(ozet, (S6, seg, 'veri', 'paket'), '{:.0f}')} "
                 f"| {_ort_sd(ozet, (S6, seg, 'veri', 'yenileme_orani'))} "
                 f"| {_ort_sd(ozet, (S6, seg, 'M3-sim', 'auc'))} | {_ort_sd(ozet, (S6, seg, 'kural', 'auc'))} "
                 f"| {_ort_sd(ozet, (S6, seg, 'M3-sim', 'brier'))} | {_ort_sd(ozet, (S6, seg, 'kural', 'brier'))} "
                 f"| {_ort_sd(ozet, (S6, seg, 'veri', 'gercek_kayip_ciro'), '{:.0f}')} "
                 f"| {_ort_sd(ozet, (S6, seg, 'M3-sim', 'rp_hata_yuzde'), '{:+.1f}')} "
                 f"| {_ort_sd(ozet, (S6, seg, 'kural', 'rp_hata_yuzde'), '{:+.1f}')} |")
    return y


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(prog="python -m backtest", description="M0 / M1 / M3 ve S6 yenileme backtest'i (sentetik)")
    a.add_argument("--tohum-sayisi", type=int, default=TOHUM_SAYISI)
    a.add_argument("--musteri", type=int, default=MUSTERI_SAYISI)
    a.add_argument("--senaryo", action="append", choices=(*SENARYOLAR, S6), help="yalnız bu senaryo(lar)")
    a.add_argument("--md", type=Path, default=MD_YOLU)
    a.add_argument("--ham-dizin", type=Path, default=HAM_DIZIN)
    arg = a.parse_args(argv)

    sonuc = calistir(range(arg.tohum_sayisi), arg.musteri, arg.senaryo or (*SENARYOLAR, S6), ilerleme=True)
    ham_csv_yaz(sonuc, arg.ham_dizin)
    arg.md.parent.mkdir(parents=True, exist_ok=True)
    arg.md.write_text(markdown_uret(sonuc, arg.tohum_sayisi, arg.musteri), encoding="utf-8")
    print(f"Yazıldı: {arg.md}, {arg.ham_dizin}/")
