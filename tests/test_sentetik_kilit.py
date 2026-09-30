"""Sentetik veri yükleyicisinin demo kilidi. Veritabanına BAĞLANMAZ: create_engine çağrılırsa test düşer."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from sentetik import yukleyici
from sentetik.uretici import SentetikVeri, UretimAyarlari
from sentetik.yukleyici import DemoDisiVeritabani, baglanti_adresleri, demo_veritabani_dogrula, temizle, yukle

REDDEDILEN = ["panosu", "panosu_test", "", None, "panosu_demo_eski", "demo"]


@pytest.fixture()
def baglanti_yasak(monkeypatch):
    def _yasak(*a, **k):
        raise AssertionError("Kilit, bağlantı kurulmadan önce devreye girmeliydi")
    monkeypatch.setattr(yukleyici, "create_engine", _yasak)


@pytest.mark.parametrize("ad", REDDEDILEN)
def test_demo_disi_ad_reddedilir(ad):
    with pytest.raises(DemoDisiVeritabani, match="_demo"):
        demo_veritabani_dogrula(ad)


def test_demo_adi_kabul_edilir():
    demo_veritabani_dogrula("panosu_demo")


@pytest.mark.parametrize("ad", ["panosu", "panosu_test"])
def test_yukle_baglanmadan_reddeder(baglanti_yasak, ad):
    veri = SentetikVeri(ayarlar=UretimAyarlari(referans=date(2026, 1, 1)), isletmeler=[])
    with pytest.raises(DemoDisiVeritabani):
        yukle(veri, ad)


def test_temizle_demo_disi_engine_reddeder():
    engine = create_engine("postgresql+psycopg2://x@localhost/panosu")     # engine oluşturmak bağlanmaz
    with pytest.raises(DemoDisiVeritabani):
        temizle(engine)


def test_adresler_yalnizca_veritabani_adi_degisir():
    yonetici, uygulama = baglanti_adresleri("panosu_demo")
    for turetilen, kaynak in ((yonetici, yukleyici.ayarlar.migrasyon_url), (uygulama, yukleyici.ayarlar.veritabani_url)):
        t, k = make_url(turetilen), make_url(kaynak)
        assert t.database == "panosu_demo"
        assert t.set(database=k.database) == k        # rol, parola, sunucu, port, sürücü aynı
