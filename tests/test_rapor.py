"""Haftalık rapor (GET /rapor/haftalik, komut kilidi) ve Türkçe biçimleme."""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from conftest import basliklar
from servisler import rapor_uret
from servisler.bicim import AYLAR, para, tarih, yuzde
from servisler.yenileme_calistir import IzinsizVeritabani


@pytest.mark.parametrize("tutar,beklenen", [
    (Decimal("1234.56"), "1.234,56 TL"), (Decimal("0"), "0,00 TL"), (Decimal("999.999"), "1.000,00 TL"),
    (Decimal("1234567.8"), "1.234.567,80 TL"), (Decimal("-45000"), "-45.000,00 TL"), (Decimal("12.345"), "12,35 TL"),
    (None, "—"),
])
def test_para_bicimi(tutar, beklenen):
    assert para(tutar) == beklenen


@pytest.mark.parametrize("gun,beklenen", [
    (date(2026, 10, 9), "9 Ekim 2026"), (date(2026, 2, 28), "28 Şubat 2026"), (date(2027, 8, 1), "1 Ağustos 2027"),
    (None, "—"),
])
def test_tarih_bicimi(gun, beklenen):
    assert tarih(gun) == beklenen


def test_yuzde_bicimi():
    assert (yuzde(Decimal("0.1234")), yuzde(Decimal("1")), yuzde(None)) == ("%12", "%100", "—")


@pytest.fixture()
def istemci():
    from main import app
    return TestClient(app)


def test_haftalik_rapor_html(istemci, iki_kiraci):
    a, _ = iki_kiraci
    y = istemci.get("/rapor/haftalik", headers=basliklar(a))
    assert y.status_code == 200 and y.headers["content-type"].startswith("text/html")
    html = y.text
    assert "İşletme A" in html                                               # işletme adı
    for metin in ("Bu ay gerçek gelir", "Gider girilmedi",                   # gösterge 1 (gider yok)
                  "Önümüzdeki 45 günde riskteki para", "Aktif üye / başabaş üye",
                  "Önümüzdeki 45 günde yenilemesi riskli 10 üye", "En değerli 10 sessiz üye",
                  "Olasılıklar model tahminidir; gerçek yenileme verisiyle kalibre edilmemiştir.",
                  "@page { size: A4"):
        assert metin in html, metin


def test_haftalik_rapor_gider_varken_kar_zarar(istemci, iki_kiraci):
    a, _ = iki_kiraci
    bugun = datetime.now(timezone(timedelta(hours=3))).date()
    istemci.put(f"/giderler/{bugun:%Y-%m}", json={"kira": "45000"}, headers=basliklar(a))
    html = istemci.get("/rapor/haftalik", headers=basliklar(a)).text
    assert "Bu ayın kâr/zararı" in html and "Gider girilmedi" not in html
    assert f"{bugun.day} {AYLAR[bugun.month - 1]} {bugun.year}" in html


def test_haftalik_rapor_calisan_403(istemci, iki_kiraci, calisan):
    assert istemci.get("/rapor/haftalik", headers=basliklar(calisan)).status_code == 403


@pytest.mark.parametrize("ad", ["panosu", "panosu_canli"])
def test_rapor_komutu_baglanmadan_reddeder(monkeypatch, tmp_path, ad):
    def _yasak(*a, **k):
        raise AssertionError("Kilit, bağlantı kurulmadan önce devreye girmeliydi")
    monkeypatch.setattr(rapor_uret, "create_engine", _yasak)
    with pytest.raises(IzinsizVeritabani):
        rapor_uret.uret(ad, uuid.uuid4(), tmp_path / "r.html")
    with pytest.raises(SystemExit):
        rapor_uret.main(["--veritabani", ad, "--isletme", str(uuid.uuid4()), "--cikti", str(tmp_path / "r.html")])


def test_rapor_komutu_test_veritabaninda_dosya_yazar(iki_kiraci, tmp_path):
    a, _ = iki_kiraci
    yol = rapor_uret.uret("panosu_test", a.isletme_id, tmp_path / "haftalik.html")
    assert "İşletme A" in yol.read_text(encoding="utf-8")
