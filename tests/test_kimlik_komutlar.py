"""Kimlik komutları (isletme_ac, demo_kullanici): kilitler ve test veritabanında pilot işletme açma."""

import pytest
from sqlalchemy import text

from kimlik_yardimci import PAROLA, acik_kayit, eposta, giris, istemci, kayit_temizligi  # noqa: F401
from sentetik import demo_kullanici, yukleyici
from sentetik.yukleyici import DemoDisiVeritabani
from servisler import isletme_ac
from servisler.yenileme_calistir import IzinsizVeritabani


def _yasak(*a, **k):
    raise AssertionError("Kilit, bağlantı kurulmadan önce devreye girmeliydi")


@pytest.mark.parametrize("ad", ["panosu", "panosu_canli", ""])
def test_isletme_ac_canli_onaysiz_baglanmadan_reddeder(monkeypatch, ad):
    monkeypatch.setattr(isletme_ac, "create_engine", _yasak)
    with pytest.raises(IzinsizVeritabani):
        isletme_ac.isletme_ac(ad, "x@ornek.com", "X", "X", "spor_salonu", PAROLA)
    with pytest.raises(SystemExit):
        isletme_ac.main(["--veritabani", ad or "x", "--eposta", "x@ornek.com", "--ad-soyad", "X", "--isletme", "X"])


@pytest.mark.parametrize("ad", ["panosu", "panosu_test"])
def test_demo_kullanici_yalniz_demo_veritabani(monkeypatch, ad):
    monkeypatch.setattr(demo_kullanici, "create_engine", _yasak)
    monkeypatch.setattr(yukleyici, "create_engine", _yasak)
    with pytest.raises(DemoDisiVeritabani):
        demo_kullanici.demo_kullanici_kur(ad, PAROLA)
    with pytest.raises(SystemExit):
        demo_kullanici.main(["--veritabani", ad])                  # parola sorulmadan önce durur


def test_isletme_ac_test_veritabaninda_ve_sahip_giris_yapar(istemci, kayit_temizligi, admin_engine):
    e = eposta()
    kayit_temizligi.append(e)
    kullanici_id, isletme_id = isletme_ac.isletme_ac("panosu_test", e, "Pilot Sahip", "Pilot Stüdyo", "spor_salonu", PAROLA)
    with admin_engine.connect() as con:
        assert con.scalar(text("SELECT rol FROM uyelikler WHERE kullanici_id = :k AND isletme_id = :i"),
                          {"k": str(kullanici_id), "i": str(isletme_id)}) == "sahip"
    y = giris(istemci, e)
    assert y.status_code == 200 and y.json()["isletme_id"] == str(isletme_id)


def test_isletme_ac_parola_kurali(monkeypatch):
    monkeypatch.setattr(isletme_ac, "create_engine", _yasak)
    with pytest.raises(ValueError):
        isletme_ac.isletme_ac("panosu_test", "x@ornek.com", "X", "X", None, "kisa")


@pytest.mark.parametrize("kotu", ["kotu@", "@ornek.com", "bosluk var@ornek.com", "noktasiz@alanadi", "a@@b.com"])
def test_gecersiz_eposta_422(istemci, acik_kayit, kotu):
    y = istemci.post("/kayit", json={"eposta": kotu, "ad_soyad": "X", "parola": PAROLA, "isletme_adi": "X"})
    assert y.status_code == 422


def test_demo_eposta_bicimi_kabul(istemci):
    # demo@panosu.local (.local özel alan adı) kabul edilir; hesap yoksa 401 (422 değil)
    assert giris(istemci, "demo@panosu.local", "yanlis-parola-123").status_code == 401
