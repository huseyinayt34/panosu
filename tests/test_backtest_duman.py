"""Backtest duman testi: 1 tohum × 200 müşteri (S6: 400 üye), tüm senaryolar. Dosya yazmaz, veritabanına dokunmaz."""

import numpy as np

from backtest.calistir import calistir, markdown_uret, ozetle
from backtest.senaryolar import SENARYOLAR


def test_tum_senaryolar_1_tohum_200_musteri():
    sonuc = calistir(tohumlar=[0], musteri_sayisi=200, s6_uye_sayisi=400)
    ozet = ozetle(sonuc)
    for kod in SENARYOLAR:
        for model in ("M0", "M1", "M3"):
            auc = ozet[(kod, "tumu", model, "auc")][0]
            brier = ozet[(kod, "tumu", model, "brier")][0]
            assert 0.0 <= auc <= 1.0 and 0.0 <= brier <= 1.0
        for model in ("M1+M2", "M3+M2"):
            assert np.isfinite(ozet[(kod, "tumu", model, "ciro_mae")][0])

    md = markdown_uret(sonuc, tohum_sayisi=1, musteri_sayisi=200)
    assert "# Backtest sonuçları" in md and "Segment kırılımı (S4)" in md and "Segment kırılımı (S5)" in md
    assert "S5 · tek seferlik" in md

    # S6 "Stüdyo": model ve kural tabanı için AUC/Brier, Riskteki Para hatası
    for model in ("M3-sim", "kural"):
        assert 0.0 <= ozet[("S6", "tumu", model, "auc")][0] <= 1.0
        assert 0.0 <= ozet[("S6", "tumu", model, "brier")][0] <= 1.0
        assert np.isfinite(ozet[("S6", "tumu", model, "rp_hata_yuzde")][0])
    assert 'S6 "Stüdyo"' in md
