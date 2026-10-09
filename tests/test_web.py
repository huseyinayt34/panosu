"""Web paneli (Adım 9a, 9b): çerezli oturum, CSRF, giriş / işletme seçimi / çıkış, finans kutuları, riskli ve sessiz
üye tabloları (TestClient + panosu_test)."""

import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from conftest import Kiraci, basliklar
from kimlik_yardimci import PAROLA, acik_kayit, bearer, istemci, kayit_ol, kayit_temizligi  # noqa: F401

ERISIM, YENILEME, CSRF = "panosu_erisim", "panosu_yenileme", "panosu_csrf"


def _cerez(istemci, ad):
    return istemci.cookies.get(ad)


def _cerez_ayarla(istemci, ad, deger):
    """Sunucunun yazdığı çerezi aynı alan adı / yol ile değiştirir (çerez kavanozunda ikinci kopya oluşmasın)."""
    alan = next(c.domain for c in istemci.cookies.jar if c.name == ad)
    istemci.cookies.set(ad, deger, domain=alan, path="/")


def _set_cookie(yanit, ad):
    return [s for s in yanit.headers.get_list("set-cookie") if s.startswith(f"{ad}=")]


def _csrf_al(istemci):
    assert istemci.get("/giris", follow_redirects=False).status_code == 200
    return _cerez(istemci, CSRF)


def _web_giris(istemci, eposta, parola=PAROLA):
    csrf = _csrf_al(istemci)
    return istemci.post("/giris", data={"eposta": eposta, "parola": parola, "csrf": csrf}, follow_redirects=False)


def _iki_uyelikli_kullanici(istemci, kayit_temizligi, a):
    """Kendi stüdyosunun sahibi + A işletmesine çalışan olarak davetli kullanıcı."""
    k = kayit_ol(istemci, kayit_temizligi)
    kod = istemci.post("/davetler", json={"rol": "calisan"}, headers=basliklar(a)).json()["kod"]
    assert istemci.post("/davetler/kabul", json={"kod": kod}, headers=bearer(k["erisim_tokeni"])).status_code == 200
    return k


# ---------------------------------------------------------------- Oturumsuz erişim ve CSRF

def test_cerezsiz_pano_giris_sayfasina(istemci):
    for adres in ("/pano",):
        y = istemci.get(adres, follow_redirects=False)
        assert (y.status_code, y.headers["location"]) == (303, "/giris")


def test_giris_formu_csrf_cerezi_ve_form_alani(istemci):
    y = istemci.get("/giris")
    assert y.status_code == 200
    csrf = _cerez(istemci, CSRF)
    assert csrf and f'name="csrf" value="{csrf}"' in y.text
    assert y.headers["cache-control"] == "no-store"


def test_giris_csrf_eksik_veya_yanlis_403(istemci):
    govde = {"eposta": "x@test.local", "parola": PAROLA}
    from main import app
    assert TestClient(app).post("/giris", data={**govde, "csrf": "herhangi"}).status_code == 403   # çerez yok
    _csrf_al(istemci)
    assert istemci.post("/giris", data=govde).status_code == 403
    assert istemci.post("/giris", data={**govde, "csrf": "yanlis"}).status_code == 403


# ---------------------------------------------------------------- Giriş

def test_yanlis_parola_401_genel_mesaj(istemci, acik_kayit, kayit_temizligi):
    k = kayit_ol(istemci, kayit_temizligi)
    istemci.cookies.clear()
    yanlis = "yanlis-parola-1234"
    for eposta, parola in ((k["eposta"], yanlis), ("gecersiz-eposta", yanlis)):
        y = _web_giris(istemci, eposta, parola)
        assert y.status_code == 401
        assert "E-posta veya parola hatalı" in y.text
        assert yanlis not in y.text and PAROLA not in y.text
        assert not _set_cookie(y, ERISIM) and not _set_cookie(y, YENILEME)
    assert _cerez(istemci, ERISIM) is None


def test_dogru_giris_tek_uyelik(istemci, acik_kayit, kayit_temizligi):
    k = kayit_ol(istemci, kayit_temizligi, isletme_adi="Web Stüdyo")
    istemci.cookies.clear()
    onceki_csrf = _csrf_al(istemci)
    y = istemci.post("/giris", data={"eposta": k["eposta"], "parola": PAROLA, "csrf": onceki_csrf},
                     follow_redirects=False)
    assert (y.status_code, y.headers["location"]) == (303, "/pano")
    for ad in (ERISIM, YENILEME, CSRF):
        [satir] = _set_cookie(y, ad)
        assert "HttpOnly" in satir and "SameSite=lax" in satir and "Path=/" in satir
        assert "Secure" not in satir                                     # ortam=gelistirme
    assert _cerez(istemci, CSRF) != onceki_csrf                          # oturum sabitleme önlemi
    sayfa = istemci.get("/pano")
    assert sayfa.status_code == 200 and "Web Stüdyo" in sayfa.text
    assert "İşletme değiştir" not in sayfa.text                          # tek üyelik


def test_uretimde_cerezler_secure(istemci, acik_kayit, kayit_temizligi, monkeypatch):
    from config import ayarlar
    from main import app
    k = kayit_ol(istemci, kayit_temizligi)
    monkeypatch.setattr(ayarlar, "ortam", "uretim")
    https = TestClient(app, base_url="https://testserver")         # Secure çerezler yalnızca HTTPS'te geri gönderilir
    y = _web_giris(https, k["eposta"])
    assert (y.status_code, y.headers["location"]) == (303, "/pano")
    for ad in (ERISIM, YENILEME, CSRF):
        [satir] = _set_cookie(y, ad)
        assert "Secure" in satir and "HttpOnly" in satir


def test_iki_uyelik_isletme_secimi(istemci, acik_kayit, kayit_temizligi, iki_kiraci):
    a, b = iki_kiraci
    k = _iki_uyelikli_kullanici(istemci, kayit_temizligi, a)
    istemci.cookies.clear()
    y = _web_giris(istemci, k["eposta"])
    assert (y.status_code, y.headers["location"]) == (303, "/isletme")
    assert istemci.get("/pano", follow_redirects=False).headers["location"] == "/isletme"   # işletme seçilmedi

    liste = istemci.get("/isletme")
    assert liste.status_code == 200 and "İşletme A" in liste.text and "Test Stüdyo" in liste.text
    assert "İşletme B" not in liste.text
    csrf = _cerez(istemci, CSRF)

    red = istemci.post("/isletme", data={"isletme_id": str(b.isletme_id), "csrf": csrf}, follow_redirects=False)
    assert red.status_code == 403 and not _set_cookie(red, ERISIM)
    assert istemci.post("/isletme", data={"isletme_id": "uydurma", "csrf": csrf}).status_code == 403
    assert istemci.post("/isletme", data={"isletme_id": str(a.isletme_id)}).status_code == 403   # CSRF yok

    sec = istemci.post("/isletme", data={"isletme_id": str(a.isletme_id), "csrf": csrf}, follow_redirects=False)
    assert (sec.status_code, sec.headers["location"]) == (303, "/pano")
    sayfa = istemci.get("/pano")
    assert sayfa.status_code == 200 and "İşletme A" in sayfa.text and "İşletme değiştir" in sayfa.text


# ---------------------------------------------------------------- Yenileme ve çıkış

def test_bozuk_erisim_tam_sayfa_get_yeniler(istemci, acik_kayit, kayit_temizligi):
    k = kayit_ol(istemci, kayit_temizligi)
    istemci.cookies.clear()
    _web_giris(istemci, k["eposta"])
    eski_yenileme = _cerez(istemci, YENILEME)
    _cerez_ayarla(istemci, ERISIM, "bozuk")

    y = istemci.get("/pano", follow_redirects=False)
    assert y.status_code == 200
    assert _set_cookie(y, ERISIM) and _set_cookie(y, YENILEME)
    assert _cerez(istemci, YENILEME) != eski_yenileme and _cerez(istemci, ERISIM) != "bozuk"
    assert istemci.post("/oturum/yenile", json={"yenileme_tokeni": eski_yenileme}).status_code == 401


def test_bozuk_erisim_htmx_istegi_yenilemez(istemci, acik_kayit, kayit_temizligi):
    k = kayit_ol(istemci, kayit_temizligi)
    istemci.cookies.clear()
    _web_giris(istemci, k["eposta"])
    eski_yenileme = _cerez(istemci, YENILEME)
    _cerez_ayarla(istemci, ERISIM, "bozuk")

    y = istemci.get("/pano", headers={"HX-Request": "true"}, follow_redirects=False)
    assert (y.status_code, y.headers.get("hx-refresh")) == (401, "true")
    assert not _set_cookie(y, YENILEME) and _cerez(istemci, YENILEME) == eski_yenileme
    assert istemci.post("/oturum/yenile", json={"yenileme_tokeni": eski_yenileme}).status_code == 200


def test_cikis_cerezleri_siler_ve_oturumu_kapatir(istemci, acik_kayit, kayit_temizligi):
    k = kayit_ol(istemci, kayit_temizligi)
    istemci.cookies.clear()
    _web_giris(istemci, k["eposta"])
    eski_yenileme = _cerez(istemci, YENILEME)
    assert istemci.post("/cikis", data={}).status_code == 403                       # CSRF yok

    y = istemci.post("/cikis", data={"csrf": _cerez(istemci, CSRF)}, follow_redirects=False)
    assert (y.status_code, y.headers["location"]) == (303, "/giris")
    for ad in (ERISIM, YENILEME, CSRF):
        [satir] = _set_cookie(y, ad)
        assert "Max-Age=0" in satir
    assert all(_cerez(istemci, ad) is None for ad in (ERISIM, YENILEME, CSRF))
    assert istemci.post("/oturum/yenile", json={"yenileme_tokeni": eski_yenileme}).status_code == 401
    assert istemci.get("/pano", follow_redirects=False).headers["location"] == "/giris"


# ---------------------------------------------------------------- Ana sayfa ve finans kutuları (Bölüm 3)

def _kiraci_cerezi(istemci, kiraci):
    """Kiracı için imzalı erişim çerezi (parolası olmayan fixture kullanıcıları için)."""
    from servisler.kimlik import erisim_tokeni_uret
    istemci.cookies.set(ERISIM, erisim_tokeni_uret(kiraci.kullanici_id, kiraci.isletme_id))


def _finans_hazirla(istemci, a):
    """Ağustos–Ekim 2026: iki ardışık 1 aylık paket (3000 TL) + Eylül'de 250 TL ziyaret; Eylül gideri 1500 TL."""
    for govde in ({"baslangic_tarihi": "2026-08-17", "bitis_tarihi": "2026-09-16", "ucret": "3000.00"},
                  {"baslangic_tarihi": "2026-09-16", "bitis_tarihi": "2026-10-16", "ucret": "3000.00"}):
        y = istemci.post(f"/musteriler/{a.musteri_id}/paketler", json={"tur": "sure", "ad": "1 Aylık", **govde},
                         headers=basliklar(a))
        assert y.status_code == 201, y.text
    y = istemci.post(f"/musteriler/{a.musteri_id}/ziyaretler",
                     json={"ziyaret_zamani": "2026-09-10T12:00:00+03:00", "toplam_tutar": "250.00"}, headers=basliklar(a))
    assert y.status_code == 201, y.text
    assert istemci.put("/giderler/2026-09", json={"kira": "1000.00", "personel": "500.00"},
                       headers=basliklar(a)).status_code == 200


def test_pano_sahip_kutular_ve_onbelleksiz(istemci, iki_kiraci):
    a, _ = iki_kiraci
    _kiraci_cerezi(istemci, a)
    y = istemci.get("/pano")
    assert y.status_code == 200
    assert y.headers["cache-control"] == "no-store"
    for metin in ("Kâr / zarar", "Gelir", "Gider", "Aktif üye / başabaş", "Riskteki para (45 gün)", "İşletme A",
                  'hx-get="/pano/finans"', "/statik/htmx.min.js"):
        assert metin in y.text
    csrf = _cerez(istemci, CSRF)
    assert f'hx-headers=\'{{"X-CSRF-Token": "{csrf}"}}\'' in y.text


def test_pano_calisan_finans_gormez(istemci, iki_kiraci, kayit_temizligi):
    a, _ = iki_kiraci
    _finans_hazirla(istemci, a)
    kod = istemci.post("/davetler", json={"rol": "calisan"}, headers=basliklar(a)).json()["kod"]
    e = f"calisan-{a.isletme_id.hex[:8]}@test.local"
    kayit_temizligi.append(e)
    assert istemci.post("/kayit/davet", json={"kod": kod, "eposta": e, "ad_soyad": "Personel",
                                              "parola": PAROLA}).status_code == 201
    istemci.cookies.clear()
    assert _web_giris(istemci, e).headers["location"] == "/pano"
    for adres in ("/pano?ay=2026-09", "/pano/finans?ay=2026-09"):
        y = istemci.get(adres)
        assert y.status_code == 200
        assert "Finans bilgileri yalnızca sahip ve yöneticiye açıktır." in y.text
        # K4 (9b): risk tabloları tüm rollere açık ve TL içerir; " TL" yokluğu finans parçasında denetlenir
        finans = y.text.split('<div id="finans">')[1].split("</div>")[0] if "<html" in y.text else y.text
        assert " TL" not in finans
        assert "Kâr / zarar" not in y.text and "başabaş" not in y.text
        for tutar in ("1.500,00 TL", "1.750,00 TL", "3.250,00 TL"):   # gider, kâr, gerçek gelir / kasaya giren
            assert tutar not in y.text


def test_pano_kiraci_izolasyonu(istemci, iki_kiraci):
    a, b = iki_kiraci
    _finans_hazirla(istemci, a)
    assert istemci.put("/giderler/2026-09", json={"kira": "77777.00"}, headers=basliklar(b)).status_code == 200
    _kiraci_cerezi(istemci, a)
    y = istemci.get("/pano?ay=2026-09")
    assert y.status_code == 200 and "İşletme A" in y.text and "1.500,00 TL" in y.text
    assert "İşletme B" not in y.text and "77.777,00" not in y.text


def test_pano_gecmis_ay_ortalama_cumlesi(istemci, iki_kiraci):
    a, _ = iki_kiraci
    _finans_hazirla(istemci, a)
    _kiraci_cerezi(istemci, a)
    y = istemci.get("/pano?ay=2026-09")
    assert "Eylül 2026 sonucu" in y.text and "1.750,00 TL" in y.text
    assert "Ort. aktif 1,0 / başabaş 1" in y.text
    assert "Başabaşın 0,0 üye üstünde (ay ortalaması)" in y.text
    assert "Ay sonunda 1 aktif üye" in y.text
    assert "üye kaybederseniz" not in y.text
    assert '<option value="2026-09" selected>' in y.text


def test_pano_icinde_bulunulan_ay_kayip_uye_cumlesi(istemci, iki_kiraci, monkeypatch):
    import dataclasses
    from rotalar import web
    a, _ = iki_kiraci
    gercek = web.finans_servisi.finans_ozeti

    def _ozet(db, ay):                                    # aktif 78, başabaş 67 → fark 11 → 12 üye
        return dataclasses.replace(gercek(db, ay), aktif_uye_sayisi=78, basabas_uye_sayisi=67, basabas_farki=11,
                                   zarar_icin_kayip_uye=12)
    monkeypatch.setattr(web.finans_servisi, "finans_ozeti", _ozet)
    _kiraci_cerezi(istemci, a)
    y = istemci.get("/pano")
    assert "Bu ay şimdiye kadar" in y.text and "78 / 67" in y.text
    assert "Başabaşın 11 üye üzerinde." in y.text and "12 üye kaybederseniz zarara geçersiniz." in y.text
    assert "ay ortalaması" not in y.text


@pytest.mark.parametrize("ay", ["2026-13", "abc", "2099-01", "2026-9"])
def test_pano_gecersiz_veya_ileri_ay_icinde_bulunulan_ay(istemci, iki_kiraci, ay):
    a, _ = iki_kiraci
    _kiraci_cerezi(istemci, a)
    y = istemci.get("/pano", params={"ay": ay})
    assert y.status_code == 200 and "Bu ay şimdiye kadar" in y.text
    bugun = datetime.now(timezone(timedelta(hours=3))).date()
    assert f'<option value="{bugun:%Y-%m}" selected>' in y.text


def test_pano_finans_htmx_yalnizca_parca(istemci, iki_kiraci):
    a, _ = iki_kiraci
    _kiraci_cerezi(istemci, a)
    y = istemci.get("/pano/finans?ay=2026-09", headers={"HX-Request": "true"})
    assert y.status_code == 200
    assert "<html" not in y.text and "Kâr / zarar" in y.text
    assert y.headers["hx-push-url"] == "/pano?ay=2026-09"
    assert y.headers["cache-control"] == "no-store"


def test_statik_htmx(istemci):
    y = istemci.get("/statik/htmx.min.js")
    assert y.status_code == 200 and 'version:"2.0.4"' in y.text


# ---------------------------------------------------------------- Riskli ve sessiz üye tabloları (Adım 9b)

BUGUN = datetime.now(timezone(timedelta(hours=3))).date()          # işletme saat dilimi: Europe/Istanbul


def _riskli_uye(admin_engine, kiraci, ad, *, hesaplama=BUGUN, ziyaret_gunleri=(), p_aktif="0.35", p_yen="0.28",
                ucret="6000.00", bitis_gun=20, telefon=None, model="test"):
    """Kiracıda üye + aktif süre paketi + yenileme riski kaydı (olasılıklar elle verilir). Ziyaretler yerel 12:00."""
    i, m, p = str(kiraci.isletme_id), str(uuid.uuid4()), str(uuid.uuid4())
    bitis = BUGUN + timedelta(days=bitis_gun)
    with admin_engine.begin() as con:
        con.execute(text("INSERT INTO musteriler (musteri_id, isletme_id, ad_soyad, telefon_e164) "
                         "VALUES (:m, :i, :a, :t)"), {"m": m, "i": i, "a": ad, "t": telefon})
        for gun in ziyaret_gunleri:
            con.execute(text("INSERT INTO ziyaretler (isletme_id, musteri_id, ziyaret_zamani) VALUES (:i, :m, :z)"),
                        {"i": i, "m": m, "z": f"{gun.isoformat()}T12:00:00+03:00"})
        con.execute(text("INSERT INTO musteri_paketleri (paket_id, isletme_id, musteri_id, tur, ad, baslangic_tarihi, "
                         "bitis_tarihi, ucret) VALUES (:p, :i, :m, 'sure', 'Paket', :b, :e, :u)"),
                    {"p": p, "i": i, "m": m, "b": BUGUN - timedelta(days=60), "e": bitis, "u": ucret})
        con.execute(text("INSERT INTO yenileme_riskleri (isletme_id, musteri_id, paket_id, hesaplama_tarihi, "
                         "model_versiyonu, kalan_gun, p_hayatta_simdi, p_yenileme, yenileme_tutari) "
                         "VALUES (:i, :m, :p, :t, :v, :k, :ph, :py, :u)"),
                    {"i": i, "m": m, "p": p, "t": hesaplama, "v": model, "k": (bitis - hesaplama).days,
                     "ph": p_aktif, "py": p_yen, "u": ucret})


def _sessizlik_gunleri(hesaplama):
    """10 ziyaret, 4 günde bir; sonuncusu hesaplamadan 18 gün önce → "~4 günde bir … 18 gündür … 4,5 katı"."""
    return [hesaplama - timedelta(days=18 + 4 * k) for k in range(10)]


SATIR = '<tr><td class="nowrap" data-etiket="Üye">'          # tablo satırı başı (K19'dan beri etiketli)


def _bolum(metin, kimlik):
    return metin.split(f'<section id="{kimlik}"')[1].split("</section>")[0]


def test_pano_tablolar_sahip(istemci, iki_kiraci, admin_engine):
    a, _ = iki_kiraci
    _riskli_uye(admin_engine, a, "Ayşe Sessiz", ziyaret_gunleri=_sessizlik_gunleri(BUGUN))
    _kiraci_cerezi(istemci, a)
    y = istemci.get("/pano")
    assert y.status_code == 200
    riskli, sessiz = _bolum(y.text, "riskli"), _bolum(y.text, "sessiz")
    assert "Önümüzdeki 45 günde paketi bitenler" in riskli and "Sessiz üyeler" in sessiz
    for parca in (riskli, sessiz):
        assert "Ayşe Sessiz" in parca
        assert "Normalde ~4 günde bir geliyor; 18 gündür gelmiyor (normalin 4,5 katı)." in parca
        assert "Aktif olma %35 · bitişe kadar sürdürme %80 → yenileme %28" in parca
        assert "4.320,00 TL" in parca
    assert "1 paketin yenilemesi riskli (olasılık %80'in altında) · riskteki para 4.320,00 TL · bugün itibarıyla" in riskli
    assert "düşük riskli" not in riskli
    assert "1 üye · toplam riskteki para 4.320,00 TL" in sessiz
    assert "20 gün kaldı" in riskli
    assert "Tümünü göster" not in y.text
    assert "Olasılıklar model tahminidir; gerçek yenileme verisiyle kalibre edilmemiştir." in y.text
    assert "Kâr / zarar" in y.text


def test_pano_on_tahmin_notu(istemci, iki_kiraci, admin_engine):
    """Preliminary-estimate note in both tables and the weekly report only when the latest run used the learned
    prior (K83)."""
    a, _ = iki_kiraci
    _riskli_uye(admin_engine, a, "Ayşe Sessiz", ziyaret_gunleri=_sessizlik_gunleri(BUGUN))
    _kiraci_cerezi(istemci, a)
    assert "Ön tahmin:" not in istemci.get("/pano").text
    _riskli_uye(admin_engine, a, "Ali Yeni", ziyaret_gunleri=_sessizlik_gunleri(BUGUN), model="mbgnbd-onsel-v1")
    y = istemci.get("/pano")
    for bolum in ("riskli", "sessiz"):
        assert "<b>Ön tahmin:</b> işletmenizin verisi henüz az" in _bolum(y.text, bolum)
    assert "<b>Ön tahmin:</b>" in istemci.get("/pano/rapor").text


def test_pano_bos_tablolar(istemci, iki_kiraci):
    a, _ = iki_kiraci
    _kiraci_cerezi(istemci, a)
    y = istemci.get("/pano")
    assert "Önümüzdeki 45 günde biten paket yok." in y.text and "Sessiz üye yok." in y.text


def test_pano_calisan_tablolari_gorur_finansi_gormez(istemci, iki_kiraci, calisan, admin_engine):
    a, _ = iki_kiraci
    _riskli_uye(admin_engine, a, "Ayşe Sessiz", ziyaret_gunleri=_sessizlik_gunleri(BUGUN))
    _kiraci_cerezi(istemci, calisan)
    y = istemci.get("/pano")
    assert y.status_code == 200
    assert "Önümüzdeki 45 günde paketi bitenler" in y.text and "Sessiz üyeler" in y.text and "Ayşe Sessiz" in y.text
    assert "Finans bilgileri yalnızca sahip ve yöneticiye açıktır." in y.text
    assert "Kâr / zarar" not in y.text and "Riskteki para (45 gün)" not in y.text and "başabaş" not in y.text


def test_pano_tablo_satir_siniri_ve_tumunu_goster(istemci, iki_kiraci, admin_engine, monkeypatch):
    from servisler import risk_listeleri
    a, _ = iki_kiraci
    _riskli_uye(admin_engine, a, "Birinci Üye", ziyaret_gunleri=_sessizlik_gunleri(BUGUN))          # 4320 TL
    _riskli_uye(admin_engine, a, "İkinci Üye", ziyaret_gunleri=_sessizlik_gunleri(BUGUN), p_aktif="0.40",
                p_yen="0.50", ucret="3000.00")                                                         # 1500 TL
    monkeypatch.setattr(risk_listeleri, "TABLO_SATIRI", 1)
    _kiraci_cerezi(istemci, a)

    y = istemci.get("/pano")
    for ad in ("riskli", "sessiz"):
        b = _bolum(y.text, ad)
        assert b.count(SATIR) == 1 and "Birinci Üye" in b and "İkinci Üye" not in b
        assert "Tümünü göster (2)" in b
        assert f'hx-get="/pano/{ad}?tumu=1"' in b and f'href="/pano?{ad}=tumu#{ad}"' in b

        p = istemci.get(f"/pano/{ad}?tumu=1", headers={"HX-Request": "true"})
        assert p.status_code == 200 and p.headers["cache-control"] == "no-store"
        assert "<html" not in p.text and "hx-push-url" not in p.headers
        assert p.text.count(SATIR) == 2 and "Tümünü göster" not in p.text

        t = istemci.get(f"/pano?{ad}=tumu")
        assert "<html" in t.text and _bolum(t.text, ad).count(SATIR) == 2

    assert _bolum(istemci.get("/pano?riskli=baska").text, "riskli").count(SATIR) == 1   # yalnızca "tumu"


def test_riskli_tablo_dusuk_riskleri_ayirir(istemci, iki_kiraci, admin_engine, oturum):
    from servisler import risk_listeleri
    a, _ = iki_kiraci
    gunler = _sessizlik_gunleri(BUGUN)
    _riskli_uye(admin_engine, a, "Riskli Bir", ziyaret_gunleri=gunler)                               # 4320 TL
    _riskli_uye(admin_engine, a, "Düşük Bir", ziyaret_gunleri=gunler, p_aktif="0.95", p_yen="0.85",
                ucret="10000.00")                                                                   # 1500 TL
    _riskli_uye(admin_engine, a, "Düşük İki", ziyaret_gunleri=gunler, p_aktif="0.95", p_yen="0.80",
                ucret="2000.00")                                                                    # 400 TL (eşik dahil)
    liste = risk_listeleri.riskli_uyeler(oturum(a))
    assert (liste.riskli_sayisi, liste.riskli_toplam) == (1, Decimal("4320.00"))
    assert (liste.dusuk_sayisi, liste.dusuk_toplam) == (2, Decimal("1900.00"))
    assert liste.riskli_toplam + liste.dusuk_toplam == liste.toplam_riskteki_para
    assert all(o["p_yenileme"] < Decimal("0.80") for o in liste.ogeler)

    _kiraci_cerezi(istemci, a)
    r = _bolum(istemci.get("/pano").text, "riskli")
    assert r.count(SATIR) == 1 and "Riskli Bir" in r and "Düşük" not in r
    assert "1 paketin yenilemesi riskli (olasılık %80'in altında) · riskteki para 4.320,00 TL" in r
    assert "Ayrıca 2 paket düşük riskli (riskteki para 1.900,00 TL)." in r
    assert "Tümünü göster (3)" in r

    t = istemci.get("/pano/riskli?tumu=1", headers={"HX-Request": "true"}).text
    assert t.count(SATIR) == 3 and "Düşük Bir" in t and "Düşük İki" in t
    assert t.index("Riskli Bir") < t.index("Düşük Bir") < t.index("Düşük İki")          # riskteki para azalan
    assert "Düzenli geliyor; belirgin bir risk yok." in t
    assert "Tümünü göster" not in t and "Ayrıca" not in t


def test_riskli_tablo_yalniz_dusuk_risk(istemci, iki_kiraci, admin_engine):
    a, _ = iki_kiraci
    _riskli_uye(admin_engine, a, "Düşük Bir", ziyaret_gunleri=_sessizlik_gunleri(BUGUN), p_aktif="0.95",
                p_yen="0.90")
    _kiraci_cerezi(istemci, a)
    r = _bolum(istemci.get("/pano").text, "riskli")
    assert "Önümüzdeki 45 günde yenilemesi riskli paket yok." in r and "<table>" not in r
    assert "Ayrıca 1 paket düşük riskli (riskteki para 600,00 TL)." in r and "Tümünü göster (1)" in r


def test_gri_satir_kucuk_olasiliklar(istemci, iki_kiraci, admin_engine):
    a, _ = iki_kiraci
    _riskli_uye(admin_engine, a, "Çok Sessiz", ziyaret_gunleri=_sessizlik_gunleri(BUGUN), p_aktif="0.0040",
                p_yen="0.0030")
    _kiraci_cerezi(istemci, a)
    for ad in ("riskli", "sessiz"):
        b = _bolum(istemci.get("/pano").text, ad)
        assert '<div class="kucuk">Aktif olma <%1</div>' in b.replace("&lt;", "<")
        assert "sürdürme" not in b
        assert re.search(r'<td class="sayi" data-etiket="[^"]+">&lt;%1</td>', b)


@pytest.mark.parametrize("p_aktif,p_yen,ayristirma,beklenen", [
    ("0.02", "0.01", False, '<div class="kucuk">Aktif olma %2</div>'),
    ("0.05", "0.04", True, "Aktif olma %5 · bitişe kadar sürdürme %80 → yenileme %4"),
])
def test_gri_satir_ayristirma_esigi(istemci, iki_kiraci, admin_engine, p_aktif, p_yen, ayristirma, beklenen):
    a, _ = iki_kiraci
    _riskli_uye(admin_engine, a, "Eşik Üye", ziyaret_gunleri=_sessizlik_gunleri(BUGUN), p_aktif=p_aktif, p_yen=p_yen)
    _kiraci_cerezi(istemci, a)
    y = istemci.get("/pano").text
    for ad in ("riskli", "sessiz"):
        b = _bolum(y, ad)
        assert beklenen in b
        assert ("sürdürme" in b) is ayristirma


def test_aciklama_hesaplama_sonrasi_ziyareti_saymaz_ve_eskimis_notu(istemci, iki_kiraci, admin_engine, oturum):
    from servisler import risk_listeleri
    from servisler.bicim import tarih
    a, _ = iki_kiraci
    hesap = BUGUN - timedelta(days=5)
    _riskli_uye(admin_engine, a, "Geç Gelen", hesaplama=hesap,
                ziyaret_gunleri=_sessizlik_gunleri(hesap) + [BUGUN - timedelta(days=2)])   # sonraki ziyaret sayılmaz
    _kiraci_cerezi(istemci, a)
    y = istemci.get("/pano")
    assert "18 gündür gelmiyor (normalin 4,5 katı)" in _bolum(y.text, "riskli")
    for ad in ("riskli", "sessiz"):
        assert f"Olasılıklar ve açıklamalar {tarih(hesap)} verisiyle hesaplandı." in _bolum(y.text, ad)

    liste = risk_listeleri.riskli_uyeler(oturum(a))
    [o] = liste.ogeler
    assert (o["aciklama"].ziyaret_sayisi, o["aciklama"].sessiz_gun) == (10, 18)
    assert o["son_ziyaret_gunu"] == BUGUN - timedelta(days=2)
    assert liste.eskimis and liste.en_eski_hesaplama == hesap


def test_eskimis_notu_bugun_hesaplandiysa_yok(istemci, iki_kiraci, admin_engine):
    a, _ = iki_kiraci
    _riskli_uye(admin_engine, a, "Güncel Üye", ziyaret_gunleri=_sessizlik_gunleri(BUGUN))
    _kiraci_cerezi(istemci, a)
    assert "verisiyle hesaplandı" not in istemci.get("/pano").text


def test_pano_tablolari_kiraci_izolasyonu(istemci, iki_kiraci, admin_engine):
    a, b = iki_kiraci
    _riskli_uye(admin_engine, a, "A Üyesi", ziyaret_gunleri=_sessizlik_gunleri(BUGUN))
    _riskli_uye(admin_engine, b, "B Gizli Üye", ziyaret_gunleri=_sessizlik_gunleri(BUGUN))
    _kiraci_cerezi(istemci, a)
    for adres in ("/pano", "/pano/riskli?tumu=1", "/pano/sessiz?tumu=1"):
        y = istemci.get(adres)
        assert "A Üyesi" in y.text and "B Gizli Üye" not in y.text


def test_pano_tablolari_xss_kacisi(istemci, iki_kiraci, admin_engine):
    a, _ = iki_kiraci
    _riskli_uye(admin_engine, a, "<script>x</script>", ziyaret_gunleri=_sessizlik_gunleri(BUGUN))
    _kiraci_cerezi(istemci, a)
    for adres in ("/pano", "/pano/riskli?tumu=1", "/pano/sessiz?tumu=1"):
        y = istemci.get(adres)
        assert "&lt;script&gt;" in y.text and "<script>x" not in y.text


def test_pano_parca_bozuk_erisim_htmx_401(istemci, acik_kayit, kayit_temizligi):
    k = kayit_ol(istemci, kayit_temizligi)
    istemci.cookies.clear()
    _web_giris(istemci, k["eposta"])
    eski_yenileme = _cerez(istemci, YENILEME)
    _cerez_ayarla(istemci, ERISIM, "bozuk")
    for adres in ("/pano/riskli?tumu=1", "/pano/sessiz?tumu=1"):
        y = istemci.get(adres, headers={"HX-Request": "true"}, follow_redirects=False)
        assert (y.status_code, y.headers.get("hx-refresh")) == (401, "true")
        assert y.headers["cache-control"] == "no-store"
        assert not _set_cookie(y, YENILEME) and _cerez(istemci, YENILEME) == eski_yenileme


# ---------------------------------------------------------------- Görünüm (K19) ve haftalık rapor ucu (Adım 9c, K18)

RAPOR_BASLIGI = "Önümüzdeki 45 günde yenilemesi en riskli paketler"


def test_tablolar_telefon_baglantisi_ve_etiketler(istemci, iki_kiraci, admin_engine):
    a, _ = iki_kiraci
    gunler = _sessizlik_gunleri(BUGUN)
    _riskli_uye(admin_engine, a, "Telefonlu Üye", ziyaret_gunleri=gunler, telefon="+905321234567")
    _riskli_uye(admin_engine, a, "Telefonsuz Üye", ziyaret_gunleri=gunler, ucret="3000.00")
    _kiraci_cerezi(istemci, a)
    y = istemci.get("/pano").text
    etiketler = {"riskli": ("Üye", "Telefon", "Paket", "Bitiş", "Yenileme olasılığı", "Riskteki para", "Neden"),
                 "sessiz": ("Üye", "Telefon", "Paket", "Son ziyaret", "Gelmediği gün", "Aktif olma olasılığı",
                            "Riskteki para", "Neden")}
    for ad, adlar in etiketler.items():
        b = _bolum(y, ad)
        assert '<a href="tel:+905321234567">+90 532 123 45 67</a>' in b
        assert '<td class="tel" data-etiket="Telefon">—</td>' in b                     # telefonsuz: bağlantı yok
        assert b.count('href="tel:') == 1
        govde = b.split("<tbody>")[1].split("</tbody>")[0]
        assert govde.count("<td") == govde.count("data-etiket=") == 2 * len(adlar)      # her td etiketli
        for etiket in adlar:
            assert govde.count(f'data-etiket="{etiket}"') == 2
        for etiket in ("Üye", "Paket", ("Bitiş" if ad == "riskli" else "Son ziyaret")):
            assert f'<td class="nowrap" data-etiket="{etiket}">' in govde


def test_panel_css_kart_gorunumu(istemci):
    css = istemci.get("/statik/panel.css").text
    dar = css.split("@media (max-width: 600px)")[1]
    for kural in (".tablo-kap thead { display: none; }", "content: attr(data-etiket);",
                  ".tablo-kap td.sayi { text-align: left; }", "grid-template-columns: 9.5em minmax(0, 1fr);",
                  ".tablo-kap td > * { grid-column: 2; }", ".tablo-kap td.neden { display: block;"):
        assert kural in dar
    assert "td.tel, td.nowrap { white-space: nowrap; }" in css.split("@media")[0]


def test_pano_rapor_sahip(istemci, iki_kiraci, admin_engine):
    a, b = iki_kiraci
    _riskli_uye(admin_engine, a, "Ayşe Sessiz", ziyaret_gunleri=_sessizlik_gunleri(BUGUN), telefon="+905321234567")
    _riskli_uye(admin_engine, b, "B Gizli Üye", ziyaret_gunleri=_sessizlik_gunleri(BUGUN))
    _kiraci_cerezi(istemci, a)
    y = istemci.get("/pano/rapor")
    assert y.status_code == 200 and y.headers["content-type"].startswith("text/html")
    assert y.headers["cache-control"] == "no-store"
    assert RAPOR_BASLIGI in y.text and "İşletme A" in y.text and "Ayşe Sessiz" in y.text
    assert "+90 532 123 45 67" in y.text and "Yazdır / PDF" in y.text
    assert "B Gizli Üye" not in y.text and "İşletme B" not in y.text                     # kiracı izolasyonu


@pytest.fixture()
def yonetici(admin_engine, iki_kiraci):
    """A işletmesinde 'yonetici' rolünde kullanıcı (calisan fixture'ı kalıbı). Test sonunda silinir."""
    a, _ = iki_kiraci
    k = str(uuid.uuid4())
    with admin_engine.begin() as con:
        con.execute(text("INSERT INTO kullanicilar (kullanici_id, eposta, ad_soyad) VALUES (:u, :e, 'Yönetici')"),
                    {"u": k, "e": f"{k}@test.local"})
        con.execute(text("INSERT INTO uyelikler (isletme_id, kullanici_id, rol) VALUES (:i, :u, 'yonetici')"),
                    {"i": str(a.isletme_id), "u": k})
    try:
        yield Kiraci(a.isletme_id, uuid.UUID(k), a.musteri_id, a.musteri_adi)
    finally:
        with admin_engine.begin() as con:
            con.execute(text("DELETE FROM uyelikler WHERE kullanici_id = :u"), {"u": k})
            con.execute(text("DELETE FROM denetim_kayitlari WHERE kullanici_id = :u"), {"u": k})
            con.execute(text("DELETE FROM kullanicilar WHERE kullanici_id = :u"), {"u": k})


def test_pano_rapor_yonetici(istemci, yonetici):
    _kiraci_cerezi(istemci, yonetici)
    y = istemci.get("/pano/rapor")
    assert y.status_code == 200 and RAPOR_BASLIGI in y.text
    assert 'href="/pano/rapor"' in istemci.get("/pano").text


def test_pano_rapor_calisan_403(istemci, iki_kiraci, calisan):
    _kiraci_cerezi(istemci, calisan)
    y = istemci.get("/pano/rapor")
    assert y.status_code == 403 and y.headers["cache-control"] == "no-store"
    assert "Haftalık rapor yalnızca işletme sahibi ve yöneticiye açıktır." in y.text
    assert RAPOR_BASLIGI not in y.text and " TL" not in y.text
    assert "Haftalık rapor</a>" not in istemci.get("/pano").text                         # bağlantı çalışana yok


def test_pano_rapor_baglantisi_sahipte(istemci, iki_kiraci):
    a, _ = iki_kiraci
    _kiraci_cerezi(istemci, a)
    assert '<a href="/pano/rapor" target="_blank" rel="noopener">Haftalık rapor</a>' in istemci.get("/pano").text


def test_pano_rapor_oturumsuz_ve_isletmesiz(istemci, iki_kiraci):
    from servisler.kimlik import erisim_tokeni_uret
    a, _ = iki_kiraci
    y = istemci.get("/pano/rapor", follow_redirects=False)
    assert (y.status_code, y.headers["location"]) == (303, "/giris")
    istemci.cookies.set(ERISIM, erisim_tokeni_uret(a.kullanici_id, None))
    y = istemci.get("/pano/rapor", follow_redirects=False)
    assert (y.status_code, y.headers["location"]) == (303, "/isletme")
    y = istemci.get("/pano/rapor", headers={"HX-Request": "true"}, follow_redirects=False)
    assert (y.status_code, y.headers.get("hx-refresh")) == (401, "true")


def test_pano_rapor_xss_kacisi(istemci, iki_kiraci, admin_engine):
    a, _ = iki_kiraci
    _riskli_uye(admin_engine, a, "<script>x</script>", ziyaret_gunleri=_sessizlik_gunleri(BUGUN))
    _kiraci_cerezi(istemci, a)
    y = istemci.get("/pano/rapor")
    assert "&lt;script&gt;x&lt;/script&gt;" in y.text and "<script>x" not in y.text
