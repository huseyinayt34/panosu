"""Web paneli (Adım 9a): çerezli oturum, CSRF, giriş / işletme seçimi / çıkış (TestClient + panosu_test)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from conftest import basliklar
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

def test_cerezsiz_pano_ve_kok_giris_sayfasina(istemci):
    for adres in ("/pano", "/"):
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
        assert " TL" not in y.text and "Kâr / zarar" not in y.text and "başabaş" not in y.text


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
