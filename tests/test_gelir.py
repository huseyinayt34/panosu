"""Gelir tanıma kuralları (servisler/gelir.py) ve başabaş: saf Decimal, veritabanı yok."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from servisler.finans_servisi import basabas_uye_sayisi
from servisler.gelir import PaketGeliri, hak_edilen, kasaya_giren, paket_aktif_mi, paylastir, ziyaret_geliri

D = Decimal
BUGUN = date(2026, 10, 1)


def _sure(bas, bit, ucret, iptal=None):
    return PaketGeliri(tur="sure", baslangic=bas, bitis=bit, giris_hakki=None, ucret=D(ucret), iptal_tarihi=iptal)


def _giris(bas, bit, ucret, hak, kullanim, iptal=None):
    return PaketGeliri(tur="giris", baslangic=bas, bitis=bit, giris_hakki=hak, ucret=D(ucret), iptal_tarihi=iptal,
                       kullanim_gunleri=tuple(kullanim))


def _ay_toplami(gelir: dict, yil: int, ay: int) -> Decimal:
    return sum((t for g, t in gelir.items() if (g.year, g.month) == (yil, ay)), D("0"))


@pytest.mark.parametrize("tutar,adet", [("10000.00", 181), ("2500.00", 30), ("0.05", 10), ("800.00", 12), ("1", 3)])
def test_paylastir_toplam_tam_ve_negatif_yok(tutar, adet):
    paylar = paylastir(D(tutar), adet)
    assert len(paylar) == adet and sum(paylar) == D(tutar)
    assert all(p >= 0 for p in paylar) and all(p == paylar[0] for p in paylar[:-1])


def test_alti_aylik_paket_omru_boyunca_toplam_ucret():
    paket = _sure(date(2026, 1, 15), date(2026, 7, 15), "10000.00")
    gelir = hak_edilen(paket, BUGUN)
    assert len(gelir) == 181                                         # [15 Ocak, 15 Temmuz)
    assert sum(gelir.values()) == D("10000.00")                      # tam eşitlik
    assert date(2026, 7, 15) not in gelir and min(gelir) == date(2026, 1, 15)


def test_ay_siniri_gecen_paketin_iki_ay_payi():
    paket = _sure(date(2026, 1, 20), date(2026, 2, 19), "2500.00")  # 30 gün: Ocak 12, Şubat 18
    gelir = hak_edilen(paket, BUGUN)
    assert _ay_toplami(gelir, 2026, 1) == D("83.33") * 12 == D("999.96")
    assert _ay_toplami(gelir, 2026, 2) == D("1500.04")              # 17 × 83.33 + son gün farkı (83.43)
    assert gelir[date(2026, 2, 18)] == D("2500.00") - D("83.33") * 29


def test_kasaya_giren_baslangic_gununde():
    assert kasaya_giren(_sure(date(2026, 1, 20), date(2026, 2, 19), "2500.00")) == {date(2026, 1, 20): D("2500.00")}


def test_giris_kullanim_basina_pay_ve_son_kullanmada_kalan_haklar():
    kullanim = [date(2026, 8, 3), date(2026, 8, 3), date(2026, 8, 10)]                 # aynı gün iki giriş
    paket = _giris(date(2026, 8, 1), date(2026, 9, 30), "800.00", 12, kullanim)
    gelir = hak_edilen(paket, BUGUN)                                                   # bitiş (30 Eylül) geçti
    assert gelir[date(2026, 8, 3)] == D("133.32") and gelir[date(2026, 8, 10)] == D("66.66")
    assert gelir[date(2026, 9, 30)] == D("800.00") - D("66.66") * 3                     # kullanılmayan 9 hak
    assert sum(gelir.values()) == D("800.00")


def test_giris_son_kullanma_gunu_bugunse_henuz_tanimaz():
    paket = _giris(date(2026, 8, 1), BUGUN, "800.00", 12, [date(2026, 8, 3)])
    assert hak_edilen(paket, BUGUN) == {date(2026, 8, 3): D("66.66")}


def test_giris_son_kullanmasiz_kullanilmayan_hak_tanimaz_ve_fazla_giris_sayilmaz():
    paket = _giris(date(2026, 1, 1), None, "800.00", 12, [date(2026, 1, 1) + timedelta(days=i) for i in range(14)])
    gelir = hak_edilen(paket, BUGUN)
    assert len(gelir) == 12 and sum(gelir.values()) == D("800.00")                     # son girişe fark eklendi
    assert gelir[date(2026, 1, 12)] == D("800.00") - D("66.66") * 11
    yarim = _giris(date(2026, 1, 1), None, "800.00", 12, [date(2026, 1, 5)])
    assert sum(hak_edilen(yarim, BUGUN).values()) == D("66.66")


def test_iptal_sonrasi_tanima_yok():
    sure = _sure(date(2026, 9, 1), date(2026, 10, 1), "3000.00", iptal=date(2026, 9, 10))
    gelir = hak_edilen(sure, BUGUN)
    assert max(gelir) == date(2026, 9, 10) and sum(gelir.values()) == D("1000.00")    # 10 gün × 100

    giris = _giris(date(2026, 8, 1), date(2026, 9, 1), "800.00", 12,
                   [date(2026, 8, 5), date(2026, 8, 20)], iptal=date(2026, 8, 10))
    assert hak_edilen(giris, BUGUN) == {date(2026, 8, 5): D("66.66")}                  # iptal sonrası giriş ve
                                                                                       # kullanılmayan hak yok


def test_ziyaret_geliri_gununde():
    assert ziyaret_geliri([(date(2026, 9, 1), D("150")), (date(2026, 9, 1), D("50.50"))]) == {date(2026, 9, 1): D("200.50")}


def test_paket_aktif_mi():
    sure = _sure(date(2026, 9, 1), date(2026, 10, 1), "3000.00")
    assert paket_aktif_mi(sure, date(2026, 9, 30)) and not paket_aktif_mi(sure, date(2026, 10, 1))
    giris = _giris(date(2026, 9, 1), None, "800.00", 2, [date(2026, 9, 2), date(2026, 9, 5)])
    assert paket_aktif_mi(giris, date(2026, 9, 5))                                    # son hak o gün kullanılıyor
    assert not paket_aktif_mi(giris, date(2026, 9, 6))


def test_basabas_tavan_ve_null():
    assert basabas_uye_sayisi(D("118000.00"), D("1500.00")) == 79                     # 78.67 → 79
    assert basabas_uye_sayisi(D("3000.00"), D("1500.00")) == 2                        # tam bölünür
    assert basabas_uye_sayisi(None, D("1500.00")) is None
    assert basabas_uye_sayisi(D("3000.00"), None) is None
    assert basabas_uye_sayisi(D("3000.00"), D("0")) is None
