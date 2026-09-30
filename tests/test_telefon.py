"""telefon_normallestir birim testleri (veritabanı yok)."""

import pytest

from servisler.telefon import telefon_normallestir


@pytest.mark.parametrize("ham", [
    "0532 123 45 67",
    "5321234567",
    "+90 (532) 123-45-67",
    "905321234567",
    "0090 532 123 45 67",
])
def test_turk_cep_numarasi_e164_olur(ham):
    assert telefon_normallestir(ham) == "+905321234567"


@pytest.mark.parametrize("ham, beklenen", [
    ("+4915112345678", "+4915112345678"),
    ("0212 555 11 22", "+902125551122"),
])
def test_diger_bicimler(ham, beklenen):
    assert telefon_normallestir(ham) == beklenen


@pytest.mark.parametrize("ham", [None, "", "   "])
def test_bos_deger_none_olur(ham):
    assert telefon_normallestir(ham) is None


@pytest.mark.parametrize("ham", ["12345", "0532abc", "+0123456789"])
def test_gecersiz_numara_hata_verir(ham):
    with pytest.raises(ValueError):
        telefon_normallestir(ham)
