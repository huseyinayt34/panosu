"""Mevcut V1 churn modelini (MusteriAnalizi.py) sentetik verinin GERÇEK durumuyla karşılaştırır.

Gerçek dünyada bir müşterinin gerçekten kaybedilip kaybedilmediğini bilemeyiz. Sentetik veride ise
biliyoruz; bu yüzden modelin ne kadar iyi ayırt ettiğini ölçebiliriz.

Ölçüt: ROC AUC = rastgele seçilen bir "kaybedilmiş" müşterinin risk puanının, rastgele seçilen bir
"aktif" müşterinin puanından yüksek olma olasılığı. 0.5 = yazı tura, 1.0 = kusursuz.
"""

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, stdev

import numpy as np

from MusteriAnalizi import MIN_ZIYARET_SAYISI, churn_riski, ziyaret_araliklari
from sentetik.uretici import SentetikVeri


@dataclass(frozen=True)
class SektorSonucu:
    sektor: str
    musteri: int
    degerlendirilen: int      # en az MIN_ZIYARET_SAYISI ziyareti olanlar
    gercek_kayip_orani: float
    auc: float | None


def roc_auc(puanlar: np.ndarray, etiketler: np.ndarray) -> float | None:
    """Mann-Whitney U istatistiği ile AUC (eşit puanlar yarım sayılır)."""
    poz, neg = puanlar[etiketler == 1], puanlar[etiketler == 0]
    if len(poz) == 0 or len(neg) == 0:
        return None
    siralar = _ortalama_sira(np.concatenate([poz, neg]))
    u = siralar[: len(poz)].sum() - len(poz) * (len(poz) + 1) / 2
    return float(u / (len(poz) * len(neg)))


def _ortalama_sira(x: np.ndarray) -> np.ndarray:
    sira = np.empty(len(x))
    sira[np.argsort(x, kind="mergesort")] = np.arange(1, len(x) + 1)
    for deger in np.unique(x):                    # eşit değerlere ortalama sıra
        maske = x == deger
        if maske.sum() > 1:
            sira[maske] = sira[maske].mean()
    return sira


def v1_modelini_degerlendir(veri: SentetikVeri) -> list[SektorSonucu]:
    referans = veri.ayarlar.referans
    sonuclar = []
    for isletme in veri.isletmeler:
        tarihler: dict = defaultdict(list)
        for z in isletme.ziyaretler:
            if z["durum"] == "tamamlandi":
                tarihler[z["musteri_id"]].append(z["ziyaret_zamani"].date())

        puanlar, etiketler = [], []
        for g in isletme.gercek:
            t = sorted(tarihler[g.musteri_id])
            if len(t) < MIN_ZIYARET_SAYISI:
                continue
            araliklar = ziyaret_araliklari(t)
            risk = churn_riski((referans - t[-1]).days, mean(araliklar), stdev(araliklar))
            puanlar.append(risk)
            etiketler.append(0 if g.canli_mi else 1)

        tum_kayip = [0 if g.canli_mi else 1 for g in isletme.gercek]
        sonuclar.append(SektorSonucu(
            sektor=isletme.profil.sektor,
            musteri=len(isletme.gercek),
            degerlendirilen=len(puanlar),
            gercek_kayip_orani=float(np.mean(tum_kayip)) if tum_kayip else 0.0,
            auc=roc_auc(np.array(puanlar), np.array(etiketler)),
        ))
    return sonuclar
