"""analitik.riskteki_para: uç durumlar ve Decimal dönüşümü."""

from decimal import Decimal

import numpy as np
import pytest

from analitik.riskteki_para import beklenen_aylik_ciro, para_decimal, riskteki_para


def test_hayatta_kesinse_risk_sifir():
    assert riskteki_para(1.0, 0.05, 400.0) == 0.0


def test_olu_kesinse_risk_beklenen_aylik_ciro():
    assert riskteki_para(0.0, 0.05, 400.0) == pytest.approx(beklenen_aylik_ciro(0.05, 400.0))
    assert beklenen_aylik_ciro(0.05, 400.0) == pytest.approx(30 * 0.05 * 400.0)


def test_vektorel():
    np.testing.assert_allclose(riskteki_para([1.0, 0.5, 0.0], [0.1, 0.1, 0.1], [100.0, 100.0, 100.0]),
                               [0.0, 150.0, 300.0])


def test_para_decimal_kurusa_yuvarlar():
    assert para_decimal(123.455) == Decimal("123.46")
    assert para_decimal(0.1 + 0.2) == Decimal("0.30")
