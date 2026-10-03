"""Ritmeva landing page at / (`docs/adim-ritmeva-tasarim.md`, K53-K59): no session and no cookie, no request to
another host, every static reference resolves, the calendar setting (K56) and the visible rename (K57)."""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from config import Ayarlar, ayarlar
from main import app
from rotalar.web import ERISIM_CEREZI

GITHUB_DEPOSU = "https://github.com/huseyinayt34/panosu"
CSS_URL = re.compile(r"""url\(\s*(["']?)(.*?)\1\s*\)""")


class _Etiketler(HTMLParser):
    """Collects every start tag of a page as (tag, attributes)."""

    def __init__(self) -> None:
        super().__init__()
        self.etiketler: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, etiket, nitelikler):
        self.etiketler.append((etiket, dict(nitelikler)))


def _etiketler(sayfa: str) -> list[tuple[str, dict[str, str | None]]]:
    ayristirici = _Etiketler()
    ayristirici.feed(sayfa)
    return ayristirici.etiketler


def _adresler(sayfa: str) -> list[str]:
    """Every src and href value on the page."""
    return [deger for _, nitelikler in _etiketler(sayfa) for ad, deger in nitelikler.items()
            if ad in ("src", "href") and deger is not None]


@pytest.fixture()
def takvimsiz(monkeypatch):
    """Pins the calendar setting to unset, so a local .env value cannot change the page under test."""
    monkeypatch.setattr(ayarlar, "pilot_takvim_adresi", None)


def test_kok_tanitim_sayfasi_cerezsiz(takvimsiz):
    y = TestClient(app).get("/", follow_redirects=False)
    assert y.status_code == 200
    assert y.headers["content-type"].startswith("text/html")
    assert "ritmeva" in y.text and "Panosu" not in y.text
    assert "set-cookie" not in y.headers


def test_kok_bozuk_oturum_cereziyle_de_200_ve_cerezsiz(takvimsiz):
    istemci = TestClient(app, cookies={ERISIM_CEREZI: "bozuk"})
    y = istemci.get("/", follow_redirects=False)
    assert y.status_code == 200
    assert "set-cookie" not in y.headers


def test_baska_sunucuya_tek_baglanti_github(takvimsiz):
    """K55: no third-party request; the GitHub repository link is the only absolute address."""
    adresler = _adresler(TestClient(app).get("/").text)
    assert adresler
    dis = {a for a in adresler if a.lower().startswith(("http://", "https://", "//"))}
    assert dis <= {GITHUB_DEPOSU}


def test_statik_referanslar_200(takvimsiz):
    """Every /statik/ src or href on the page and every url(...) in tanitim.css is served."""
    istemci = TestClient(app)
    hedefler = {a for a in _adresler(istemci.get("/").text) if a.startswith("/statik/")}
    css = istemci.get("/statik/tanitim.css")
    assert css.status_code == 200
    for _, deger in CSS_URL.findall(css.text):
        if not deger.startswith("data:"):
            hedefler.add(urljoin("/statik/tanitim.css", deger))
    hedefler.add("/statik/panel.css")
    # Guard against a vacuous pass: the page, its scripts and the fonts must all have been found.
    assert {"/statik/tanitim.css", "/statik/tanitim.js", "/statik/vendor/three.min.js"} <= hedefler
    assert any(h.startswith("/statik/yazitipi/") and h.endswith(".woff2") for h in hedefler)
    for hedef in sorted(hedefler):
        assert istemci.get(hedef).status_code == 200, hedef


def test_takvim_adresi_tanimliysa_yeni_sekmede_acilir(monkeypatch):
    adres = "https://calendar.app.google/test"
    monkeypatch.setattr(ayarlar, "pilot_takvim_adresi", adres)
    etiketler = _etiketler(TestClient(app).get("/").text)
    baglantilar = [n for e, n in etiketler if e == "a" and n.get("href") == adres]
    assert baglantilar
    for n in baglantilar:
        assert n.get("target") == "_blank"
        assert "noopener" in (n.get("rel") or "").split()


def test_takvim_adresi_yoksa_demo_baglantisi(takvimsiz):
    sayfa = TestClient(app).get("/").text
    assert "Takvimden saat seç" not in sayfa
    assert "/giris" in _adresler(sayfa)


def _ayarlar(pilot_takvim_adresi):
    return Ayarlar(_env_file=None, veritabani_url="postgresql+psycopg2://panosu_app:x@localhost:5432/panosu_test",
                   jwt_gizli="x" * 40, pilot_takvim_adresi=pilot_takvim_adresi)


@pytest.mark.parametrize("deger", ["http://x.example", "javascript:alert(1)"], ids=["http", "javascript"])
def test_takvim_ayari_https_disini_reddeder(deger):
    with pytest.raises(ValidationError) as hata:
        _ayarlar(deger)
    assert deger not in str(hata.value)


def test_takvim_ayari_https_kabul_bos_none():
    assert _ayarlar("https://x.example").pilot_takvim_adresi == "https://x.example"
    assert _ayarlar("").pilot_takvim_adresi is None


def test_giris_basligi_ritmeva():
    sayfa = TestClient(app).get("/giris").text
    baslik = re.search(r"<title>(.*?)</title>", sayfa, re.S)
    assert baslik is not None
    assert "Ritmeva" in baslik.group(1) and "Panosu" not in baslik.group(1)
    # K57: signed out, the header brand links to the landing page.
    assert ("a", {"class": "marka", "href": "/"}) in _etiketler(sayfa)
