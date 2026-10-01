"""analitik.v1: toplu P(hayatta) tekil churn_riski ile tutarlı; MusteriAnalizi.py kabuğu aynı fonksiyonları verir."""

import numpy as np
import pytest

import MusteriAnalizi
from analitik import v1


def test_kabuk_ayni_fonksiyonlari_verir():
    assert MusteriAnalizi.churn_riski is v1.churn_riski
    assert MusteriAnalizi.MIN_ZIYARET_SAYISI == v1.MIN_ZIYARET_SAYISI


def test_toplu_p_hayatta_tekil_riskle_eslesir():
    z = np.array([0.0, 30.0, 58.0, 91.0])
    araliklar = np.diff(z)
    beklenen = 1 - v1.churn_riski(120.0 - 91.0, araliklar.mean(), araliklar.std(ddof=1))
    assert v1.p_hayatta_toplu([z], 120.0)[0] == pytest.approx(beklenen)


def test_yetersiz_ziyarette_ortanca_kullanilir():
    yeterli = [np.array([0.0, 10.0, 20.0]), np.array([0.0, 30.0, 60.0])]
    tek = np.array([100.0])
    p = v1.p_hayatta_toplu(yeterli + [tek], 110.0)
    # ortanca μ = 20, ortanca σ = 0 → σ_etkin = 5; geçen 10 gün → 1 − Φ((10 − 20) / 5)
    assert p[2] == pytest.approx(1 - v1.normal_cdf(-2.0))
