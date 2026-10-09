"""Ritmeva landing page at / (`docs/adim-ritmeva-tasarim.md`, K53-K59, K72-K74): no session and no cookie, no request
to another host, every static reference resolves, the calendar setting (K56), the visible rename (K57), founder
contact (K72), the share card (K73) and the self-hosted promo video (K74)."""

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
LINKEDIN_ADRESI = "https://www.linkedin.com/in/huseyinaytekin/"
ILETISIM_EPOSTASI = "ritmeva.iletisim@gmail.com"
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
    """Every src, href and poster value on the page."""
    return [deger for _, nitelikler in _etiketler(sayfa) for ad, deger in nitelikler.items()
            if ad in ("src", "href", "poster") and deger is not None]


def _meta(sayfa: str) -> dict[str, str | None]:
    """Meta values by key: `property` (og:*) or `name` (description, twitter:*)."""
    return {n.get("property") or n.get("name"): n.get("content") for e, n in _etiketler(sayfa)
            if e == "meta" and (n.get("property") or n.get("name"))}


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
    """K55: no third-party request; the GitHub repository and the LinkedIn profile are the only absolute addresses.
    Both are links that open on click, not requests the page makes; mailto: links are allowed."""
    sayfa = TestClient(app).get("/").text
    adresler = _adresler(sayfa)
    assert adresler
    dis = {a for a in adresler if a.lower().startswith(("http://", "https://", "//"))}
    assert dis <= {GITHUB_DEPOSU, LINKEDIN_ADRESI}
    # Everything the browser loads by itself (src, video poster) is same-origin or inline.
    yuklenen = [d for _, n in _etiketler(sayfa) for ad, d in n.items() if ad in ("src", "poster") and d is not None]
    assert yuklenen
    for deger in yuklenen:
        assert (deger.startswith("/") and not deger.startswith("//")) or deger.startswith("data:"), deger


def test_yeni_sekme_baglantilari_noopener(takvimsiz):
    etiketler = _etiketler(TestClient(app).get("/").text)
    yeni_sekme = [n for e, n in etiketler if e == "a" and n.get("target") == "_blank"]
    assert {n.get("href") for n in yeni_sekme} >= {GITHUB_DEPOSU, LINKEDIN_ADRESI}
    for n in yeni_sekme:
        assert "noopener" in (n.get("rel") or "").split(), n.get("href")


def test_paylasim_karti_mutlak_ve_sunuluyor(takvimsiz):
    """K73: og:url and og:image are absolute (crawlers need it); the share image is served from this site."""
    istemci = TestClient(app)
    sayfa = istemci.get("/").text
    meta = _meta(sayfa)
    assert meta["og:url"].startswith("http")
    assert meta["og:image"].startswith("http")
    assert meta["og:image"].endswith("/statik/medya/ritmeva-paylasim.jpg")
    gorsel = istemci.get(meta["og:image"])
    assert gorsel.status_code == 200
    assert gorsel.headers["content-type"] == "image/jpeg"
    baslik = re.search(r"<title>(.*?)</title>", sayfa, re.S)
    assert baslik is not None
    assert meta["og:title"] == baslik.group(1) and meta["og:description"] == meta["description"]
    assert (meta["og:image:width"], meta["og:image:height"]) == ("1200", "630")
    assert meta["twitter:card"] == "summary_large_image"


def test_tanitim_videosu_tembel_ve_parcali(takvimsiz):
    """K74: one self-hosted video that downloads nothing before play and answers Range requests (Safari/iPhone)."""
    istemci = TestClient(app)
    etiketler = _etiketler(istemci.get("/").text)
    videolar = [n for e, n in etiketler if e == "video"]
    assert len(videolar) == 1
    video = videolar[0]
    assert video.get("preload") == "none"
    assert "autoplay" not in video
    kaynaklar = [n.get("src") for e, n in etiketler if e == "source"]
    assert len(kaynaklar) == 1
    for adres in (video.get("poster"), kaynaklar[0]):
        assert adres is not None and adres.startswith("/statik/medya/"), adres
        assert istemci.get(adres).status_code == 200, adres
    parca = istemci.get(kaynaklar[0], headers={"Range": "bytes=0-99"})
    assert parca.status_code == 206
    assert len(parca.content) == 100


@pytest.mark.parametrize("takvim", [None, "https://calendar.app.google/test"], ids=["takvimsiz", "takvimli"])
def test_kurucu_ve_iletisim(monkeypatch, takvim):
    """K72: founder name and contact address are on the page, with or without the calendar setting; the pilot box
    offers the e-mail as a fallback next to the calendar, or as the way to book when there is no calendar."""
    monkeypatch.setattr(ayarlar, "pilot_takvim_adresi", takvim)
    sayfa = TestClient(app).get("/").text
    assert "Hüseyin Aytekin" in sayfa
    assert f"mailto:{ILETISIM_EPOSTASI}" in sayfa
    if takvim:
        assert "Takvim uymuyorsa" in sayfa
    else:
        assert "Görüşme için bize yazın" in sayfa
        assert "Takvim uymuyorsa" not in sayfa
    kucuk = sayfa.lower()
    assert "öğrenci" not in kucuk
    assert "yapay zekâ destekli" not in kucuk


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
