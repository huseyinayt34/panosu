"""analitik.ozellikler: elle hesaplanmış küçük örnekler."""

import numpy as np
import pytest

from analitik.ozellikler import ozellik_cikar


def test_elle_hesaplanan_ornek():
    zamanlar = [np.array([10.0, 40.0, 25.0]), np.array([5.0]), np.array([0.0, 50.0, 120.0])]
    tutarlar = [np.array([100.0, 300.0, 200.0]), np.array([80.0]), np.array([10.0, 20.0, 999.0])]
    oz = ozellik_cikar(zamanlar, tutarlar, gozlem_sonu=100.0)

    # 1. müşteri: sıralı 10, 25, 40 → x=2, t_x=30, T=90, m̄ = (200 + 300) / 2 (ilk ziyaret hariç)
    # 2. müşteri: tek ziyaret → x=0, t_x=0, T=95, m̄ tanımsız
    # 3. müşteri: 120 gözlem sonundan sonra, yok sayılır → x=1, t_x=50, T=100, m̄=20
    np.testing.assert_array_equal(oz.x, [2, 0, 1])
    np.testing.assert_array_equal(oz.t_x, [30, 0, 50])
    np.testing.assert_array_equal(oz.T, [90, 95, 100])
    assert oz.m[0] == 250 and np.isnan(oz.m[1]) and oz.m[2] == 20


def test_tek_ziyaretli_musteride_x_sifir():
    oz = ozellik_cikar([np.array([7.0])], [np.array([50.0])], gozlem_sonu=30.0)
    assert oz.x[0] == 0 and oz.t_x[0] == 0 and oz.T[0] == 23


def test_gozlem_sonundan_once_ziyaret_yoksa_hata():
    with pytest.raises(ValueError):
        ozellik_cikar([np.array([40.0])], [np.array([1.0])], gozlem_sonu=30.0)
