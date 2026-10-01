"""Demo paket üreticisi: zincir kuralları ve kilit. Veritabanına BAĞLANMAZ."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from sentetik import paket_uretici, yukleyici
from sentetik.paket_uretici import paket_doneminde_mi, paket_zinciri, paketleri_yukle
from sentetik.yukleyici import DemoDisiVeritabani

BUGUN = date(2026, 10, 1)
AYLIK, GIRIS = 0, 3                                     # S6_PAKETLER indeksleri


def _gunler(baslangic: date, *farklar: int) -> list[date]:
    return [baslangic + timedelta(days=f) for f in farklar]


def test_sure_bazli_zincir_ve_aktif_son_paket():
    tarihler = _gunler(date(2026, 7, 1), 0, 10, 25, 33, 50, 70, 85)
    zincir = paket_zinciri(tarihler, AYLIK, BUGUN)
    assert [p["baslangic_tarihi"] for p in zincir] == _gunler(date(2026, 7, 1), 0, 33, 70)
    assert all(p["bitis_tarihi"] == p["baslangic_tarihi"] + timedelta(days=30) for p in zincir)
    assert [p["durum"] for p in zincir] == ["bitti", "bitti", "aktif"]           # 70+30 = 2026-10-08 ≥ bugün
    assert all(p["ucret"] == Decimal(2500) and p["giris_hakki"] is None for p in zincir)


def test_gelmeyen_uyenin_son_paketi_bitti():
    zincir = paket_zinciri(_gunler(date(2026, 1, 1), 0, 7, 14), AYLIK, BUGUN)
    assert len(zincir) == 1 and zincir[0]["durum"] == "bitti"


def test_giris_paketi_12_giriste_biter_ve_yenilenir():
    tarihler = _gunler(date(2026, 8, 1), *range(0, 52, 4))                      # 13 ziyaret, 4 günde bir
    zincir = paket_zinciri(tarihler, GIRIS, BUGUN)
    assert len(zincir) == 2
    assert zincir[0]["bitis_tarihi"] == date(2026, 8, 1) + timedelta(days=60)   # son kullanma
    assert zincir[0]["durum"] == "bitti" and zincir[0]["giris_hakki"] == 12
    assert zincir[1]["baslangic_tarihi"] == tarihler[12] and zincir[1]["durum"] == "aktif"


@pytest.mark.parametrize("ad", ["panosu", "panosu_test", "", None])
def test_kilit_baglanmadan_reddeder(monkeypatch, ad):
    def _yasak(*a, **k):
        raise AssertionError("Kilit, bağlantı kurulmadan önce devreye girmeliydi")
    monkeypatch.setattr(paket_uretici, "create_engine", _yasak)
    monkeypatch.setattr(yukleyici, "create_engine", _yasak)
    with pytest.raises(DemoDisiVeritabani):
        paketleri_yukle(ad)


# ---------------------------------------------------------------- Çift sayım (Adım 7)

def test_paket_doneminde_mi_sure_yari_acik_giris_kapali():
    paketler = [("sure", date(2026, 9, 1), date(2026, 10, 1)), ("giris", date(2026, 10, 5), date(2026, 12, 4))]
    assert paket_doneminde_mi(date(2026, 9, 1), paketler)
    assert paket_doneminde_mi(date(2026, 9, 30), paketler)
    assert not paket_doneminde_mi(date(2026, 10, 1), paketler)            # süre bitiş günü dönem dışı
    assert not paket_doneminde_mi(date(2026, 10, 3), paketler)            # paketler arası boşluk: ek satış
    assert paket_doneminde_mi(date(2026, 12, 4), paketler)                # giriş son kullanma günü dahil
    assert not paket_doneminde_mi(date(2026, 8, 31), paketler)
    assert paket_doneminde_mi(date(2030, 1, 1), [("giris", date(2026, 1, 1), None)])   # son kullanmasız
    assert not paket_doneminde_mi(date(2026, 9, 1), [])


@pytest.mark.parametrize("islev", ["cift_sayimi_duzelt", "demo_giderleri_ekle"])
@pytest.mark.parametrize("ad", ["panosu", "panosu_test"])
def test_cift_sayim_ve_giderler_kilidi(monkeypatch, islev, ad):
    def _yasak(*a, **k):
        raise AssertionError("Kilit, bağlantı kurulmadan önce devreye girmeliydi")
    monkeypatch.setattr(paket_uretici, "create_engine", _yasak)
    args = (ad,) if islev == "cift_sayimi_duzelt" else (ad, date(2026, 10, 1))
    with pytest.raises(DemoDisiVeritabani):
        getattr(paket_uretici, islev)(*args)
