"""[DEMO] Butik Reformer üreticisi: veri kuralları, kâr hedefi ve kilit. Veritabanına BAĞLANMAZ."""

import statistics

import pytest

from sentetik import butik_reformer, yukleyici
from sentetik.butik_reformer import BUGUN, PENCERE_BAS, ButikVerisi, aylik_ozet, uret
from sentetik.yukleyici import DemoDisiVeritabani


@pytest.fixture(scope="module")
def veri():
    return uret()


def test_giris_ziyaretleri_tutarsiz_ve_pencere_icinde(veri):
    assert veri.ziyaretler and all(z["toplam_tutar"] == 0 for z in veri.ziyaretler)        # çift sayım yok
    assert all(PENCERE_BAS <= z["ziyaret_zamani"].date() < BUGUN for z in veri.ziyaretler)


def test_paket_zinciri_ve_durumlar(veri):
    paketler = {p["paket_id"]: p for p in veri.paketler}
    for p in veri.paketler:
        assert p["bitis_tarihi"] >= PENCERE_BAS
        if p["onceki_paket_id"] is not None:
            onceki = paketler[p["onceki_paket_id"]]
            assert onceki["musteri_id"] == p["musteri_id"] and onceki["durum"] == "bitti"
            assert onceki["tur"] == p["tur"]                                                  # aynı türü yeniler
        if p["durum"] == "aktif":
            assert p["bitis_tarihi"] >= BUGUN
    aktif_uyeler = [p["musteri_id"] for p in veri.paketler if p["durum"] == "aktif"]
    assert len(aktif_uyeler) == len(set(aktif_uyeler))                                        # üye başına ≤ 1 aktif


def test_kar_hedefi_tipik_ayda_yuzde_10_25(veri):
    ozet = aylik_ozet(veri)
    assert len(ozet) == 18
    oranlar = [o.kar_orani for o in ozet]
    assert 0.10 <= statistics.median(oranlar) <= 0.25
    assert sum(0.10 <= r <= 0.25 for r in oranlar) >= 12                                     # ayların çoğu hedefte
    assert 65 <= statistics.mean(o.ort_aktif for o in ozet) <= 90                              # ~75 aktif üye


@pytest.mark.parametrize("ad", ["panosu", "panosu_test", "", None])
def test_kilit_baglanmadan_reddeder(monkeypatch, ad):
    def _yasak(*a, **k):
        raise AssertionError("Kilit, bağlantı kurulmadan önce devreye girmeliydi")
    monkeypatch.setattr(butik_reformer, "create_engine", _yasak)
    monkeypatch.setattr(yukleyici, "create_engine", _yasak)
    with pytest.raises(DemoDisiVeritabani):
        butik_reformer.yukle(ButikVerisi(), ad)


@pytest.mark.parametrize("ad", ["panosu", "panosu_test", "", None])
def test_yeniden_kilidi_baglanmadan_reddeder(monkeypatch, ad):
    def _yasak(*a, **k):
        raise AssertionError("Kilit, bağlantı kurulmadan önce devreye girmeliydi")
    monkeypatch.setattr(butik_reformer, "create_engine", _yasak)
    monkeypatch.setattr(yukleyici, "create_engine", _yasak)
    with pytest.raises(DemoDisiVeritabani):
        butik_reformer.yukle(ButikVerisi(), ad, yeniden=True)
