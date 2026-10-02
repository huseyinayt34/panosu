"""Haftalık rapor (GET /rapor/haftalik, komut kilidi) ve Türkçe biçimleme."""

import dataclasses
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from conftest import basliklar
from test_web import BUGUN, _riskli_uye, _sessizlik_gunleri
from servisler import rapor_servisi, rapor_uret, risk_listeleri
from servisler.bicim import AYLAR, ay_adi, olasilik, ondalik, para, tarih, telefon, yuzde
from servisler.yenileme_calistir import IzinsizVeritabani


@pytest.mark.parametrize("tutar,beklenen", [
    (Decimal("1234.56"), "1.234,56 TL"), (Decimal("0"), "0,00 TL"), (Decimal("999.999"), "1.000,00 TL"),
    (Decimal("1234567.8"), "1.234.567,80 TL"), (Decimal("-45000"), "-45.000,00 TL"), (Decimal("12.345"), "12,35 TL"),
    (None, "—"),
])
def test_para_bicimi(tutar, beklenen):
    assert para(tutar) == beklenen


@pytest.mark.parametrize("deger,hane,beklenen", [
    (Decimal("13.45"), 1, "13,5"), (Decimal("13.44"), 1, "13,4"), (Decimal("-1.25"), 1, "-1,3"), (0, 1, "0,0"),
    (Decimal("-0.04"), 1, "0,0"), (Decimal("2.5"), 2, "2,50"), (Decimal("1234.5"), 1, "1234,5"), (None, 1, "—"),
])
def test_ondalik_bicimi(deger, hane, beklenen):
    assert ondalik(deger, hane) == beklenen


@pytest.mark.parametrize("gun,beklenen", [
    (date(2026, 10, 9), "9 Ekim 2026"), (date(2026, 2, 28), "28 Şubat 2026"), (date(2027, 8, 1), "1 Ağustos 2027"),
    (None, "—"),
])
def test_tarih_bicimi(gun, beklenen):
    assert tarih(gun) == beklenen


def test_ay_adi_bicimi():
    assert (ay_adi(date(2026, 9, 1)), ay_adi(date(2027, 1, 15)), ay_adi(None)) == ("Eylül 2026", "Ocak 2027", "—")


def test_yuzde_bicimi():
    assert (yuzde(Decimal("0.1234")), yuzde(Decimal("1")), yuzde(None)) == ("%12", "%100", "—")


@pytest.mark.parametrize("p,beklenen", [
    (None, "—"), (Decimal("0"), "%0"), (Decimal("0.0001"), "<%1"), (Decimal("0.0099"), "<%1"), (Decimal("0.01"), "%1"),
    (Decimal("0.28"), "%28"), (Decimal("0.99"), "%99"), (Decimal("0.9950"), ">%99"), (Decimal("0.9999"), ">%99"),
    (Decimal("1"), "%100"), (0.005, "<%1"),
])
def test_olasilik_bicimi(p, beklenen):
    assert olasilik(p) == beklenen


@pytest.mark.parametrize("e164,beklenen", [
    ("+905321234567", "+90 532 123 45 67"), ("+902121234567", "+90 212 123 45 67"),
    ("+90532123456", "+90532123456"), ("+9053212345678", "+9053212345678"),      # uzunluk uymuyor
    ("+4915112345678", "+4915112345678"), ("05321234567", "05321234567"),      # +90 değil
    ("", ""), (None, "—"),
])
def test_telefon_bicimi(e164, beklenen):
    assert telefon(e164) == beklenen


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
    for metin in ("Geçen ay (tamamlanmış):", "Bu ay şimdiye kadar:",           # gösterge 1: iki satır
                  "gider girilmedi", "verisiyle hesaplandı",
                  "Önümüzdeki 45 günde riskteki para", "Aktif üye / başabaş üye",
                  "Önümüzdeki 45 günde yenilemesi en riskli paketler", "En değerli sessiz üyeler",
                  "Olasılıklar model tahminidir; gerçek yenileme verisiyle kalibre edilmemiştir.",
                  "@page { size: A4", "Önümüzdeki 45 günde biten paket yok.", "Sessiz üye yok.",
                  '<button class="yazdir" onclick="window.print()">Yazdır / PDF</button>',
                  "@media print { .yazdir { display: none; } }"):
        assert metin in html, metin


def test_haftalik_rapor_gider_varken_kar_zarar(istemci, iki_kiraci):
    a, _ = iki_kiraci
    bugun = datetime.now(timezone(timedelta(hours=3))).date()
    gecen_ay = (bugun.replace(day=1) - timedelta(days=1)).replace(day=1)
    for ay in (bugun, gecen_ay):
        istemci.put(f"/giderler/{ay:%Y-%m}", json={"kira": "45000"}, headers=basliklar(a))
    html = istemci.get("/rapor/haftalik", headers=basliklar(a)).text
    assert "gider girilmedi" not in html
    assert f"({bugun.day} gün)" in html                                       # bu ay kaç gün sayıldı
    assert f"{bugun.day} {AYLAR[bugun.month - 1]} {bugun.year}" in html
    kaynak = gecen_ay if bugun.day <= 7 else bugun.replace(day=1)
    assert f"Başabaş {ay_adi(kaynak)} verisiyle hesaplandı." in html


def test_haftalik_rapor_zarar_icin_kayip_uye_cumlesi(istemci, iki_kiraci, monkeypatch):
    a, _ = iki_kiraci
    gercek = rapor_servisi.finans_ozeti

    def _ozet(db, ay):                                    # aktif 78, başabaş 67 → fark 11 → 12 üye
        f = gercek(db, ay)
        return dataclasses.replace(f, aktif_uye_sayisi=78, basabas_uye_sayisi=67, basabas_farki=11,
                                   zarar_icin_kayip_uye=12)
    monkeypatch.setattr(rapor_servisi, "finans_ozeti", _ozet)
    html = istemci.get("/rapor/haftalik", headers=basliklar(a)).text
    assert "Başabaşın 11 üye üzerinde." in html
    assert "12 üye kaybederseniz zarara geçersiniz." in html


def test_haftalik_rapor_basabas_yokken_zarar_cumlesi_yok(istemci, iki_kiraci):
    a, _ = iki_kiraci
    html = istemci.get("/rapor/haftalik", headers=basliklar(a)).text
    assert "Başabaş için gider ve gelir gerekir." in html
    assert "zarara geçersiniz" not in html


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


# ---------------------------------------------------------------- Rapor = panelin yazdırılabilir hâli (Adım 9c, K17)

def _rapor_bolumleri(html):
    """(riskli bölüm, sessiz bölüm): başlıktan bir sonraki başlığa / alt bilgiye."""
    riskli = html.split("en riskli paketler</h2>")[1].split("<h2>")[0]
    return riskli, html.split("En değerli sessiz üyeler</h2>")[1].split("<footer>")[0]


def _uye_adlari(bolum):
    return re.findall(r'<tbody class="uye">\s*<tr><td class="nowrap">([^<]*)</td>', bolum)


def test_rapor_riskli_tablo_panelle_ayni(istemci, iki_kiraci, admin_engine, oturum):
    a, _ = iki_kiraci
    gunler = _sessizlik_gunleri(BUGUN)
    _riskli_uye(admin_engine, a, "Orta Risk", ziyaret_gunleri=gunler, p_yen="0.50", ucret="3000.00")   # 1500 TL
    _riskli_uye(admin_engine, a, "Büyük Risk", ziyaret_gunleri=gunler)                                 # 4320 TL
    _riskli_uye(admin_engine, a, "Küçük Risk", ziyaret_gunleri=gunler, p_yen="0.70", ucret="1000.00")  # 300 TL
    _riskli_uye(admin_engine, a, "Düşük Risk", ziyaret_gunleri=gunler, p_aktif="0.95", p_yen="0.80",
                ucret="5000.00")                                                                     # eşik dahil
    panel = risk_listeleri.riskli_uyeler(oturum(a))

    html = istemci.get("/rapor/haftalik", headers=basliklar(a)).text
    riskli, sessiz = _rapor_bolumleri(html)
    assert _uye_adlari(riskli) == [o["ad_soyad"] for o in panel.ogeler] == ["Büyük Risk", "Orta Risk", "Küçük Risk"]
    assert "Düşük Risk" not in html                                    # P ≥ %80: tabloda yok, sessiz de değil
    assert "Ayrıca 1 paket düşük riskli (riskteki para 1.000,00 TL)." in riskli
    assert "3 paketin yenilemesi riskli (olasılık %80'in altında) · riskteki para 6.120,00 TL" in riskli
    for bolum in (riskli, sessiz):                                     # neden satırı: cümle + gri ayrıştırma
        assert bolum.count('<tr class="neden"><td colspan="7">') == 3
        assert "Normalde ~4 günde bir geliyor; 18 gündür gelmiyor (normalin 4,5 katı)." in bolum
        assert "Aktif olma %35 · bitişe kadar sürdürme %80 → yenileme %28" in bolum
    assert "verisiyle hesaplandı" not in riskli
    assert "gösteriliyor" not in html                                  # 3 ≤ TABLO_SATIRI


def test_rapor_eskimis_notu(istemci, iki_kiraci, admin_engine):
    a, _ = iki_kiraci
    hesap = BUGUN - timedelta(days=5)
    _riskli_uye(admin_engine, a, "Eski Hesap", hesaplama=hesap, ziyaret_gunleri=_sessizlik_gunleri(hesap))
    for bolum in _rapor_bolumleri(istemci.get("/rapor/haftalik", headers=basliklar(a)).text):
        assert f"Olasılıklar ve açıklamalar {tarih(hesap)} verisiyle hesaplandı." in bolum


def test_rapor_ilk_n_gosteriliyor(istemci, iki_kiraci, admin_engine, monkeypatch):
    a, _ = iki_kiraci
    _riskli_uye(admin_engine, a, "Birinci Üye", ziyaret_gunleri=_sessizlik_gunleri(BUGUN))                  # 4320 TL
    _riskli_uye(admin_engine, a, "İkinci Üye", ziyaret_gunleri=_sessizlik_gunleri(BUGUN), p_yen="0.50",
                ucret="3000.00")                                                                             # 1500 TL
    monkeypatch.setattr(risk_listeleri, "TABLO_SATIRI", 1)
    riskli, sessiz = _rapor_bolumleri(istemci.get("/rapor/haftalik", headers=basliklar(a)).text)
    for bolum in (riskli, sessiz):
        assert "(ilk 1 gösteriliyor)</p>" in bolum
        assert _uye_adlari(bolum) == ["Birinci Üye"]
