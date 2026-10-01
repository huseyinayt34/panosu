"""Kimlik ve token testleri (Adım 8): kayıt, giriş, kilit, token doğrulama, yenileme, çıkış, işletme seçimi."""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import text

from conftest import basliklar
from config import ayarlar
from kimlik_yardimci import PAROLA, acik_kayit, bearer, giris, istemci, kayit_ol, kayit_temizligi  # noqa: F401

# ---------------------------------------------------------------- Kayıt


def test_kayit_201_ve_sahip_ucretsiz_abonelik(istemci, acik_kayit, kayit_temizligi, admin_engine):
    k = kayit_ol(istemci, kayit_temizligi)
    assert k["token_turu"] == "bearer" and k["isletme_id"] and k["erisim_tokeni"] and k["yenileme_tokeni"]
    assert k["erisim_bitis_sn"] == ayarlar.erisim_suresi_dk * 60
    with admin_engine.connect() as con:
        rol = con.scalar(text("SELECT u.rol FROM uyelikler u JOIN kullanicilar k USING (kullanici_id) "
                              "WHERE k.eposta = :e AND u.isletme_id = :i"), {"e": k["eposta"], "i": k["isletme_id"]})
        plan = con.scalar(text("SELECT plan_kodu FROM abonelikler WHERE isletme_id = :i AND durum = 'aktif'"),
                          {"i": k["isletme_id"]})
    assert (rol, plan) == ("sahip", "ucretsiz")
    assert istemci.get("/musteriler", headers=bearer(k["erisim_tokeni"])).status_code == 200


def test_ayni_eposta_buyuk_kucuk_harf_409(istemci, acik_kayit, kayit_temizligi):
    k = kayit_ol(istemci, kayit_temizligi)
    y = istemci.post("/kayit", json={"eposta": k["eposta"].upper(), "ad_soyad": "Başka", "parola": PAROLA,
                                     "isletme_adi": "Başka Stüdyo"})
    assert y.status_code == 409


def test_acik_kayit_kapaliyken_404(istemci, monkeypatch, kayit_temizligi):
    monkeypatch.setattr(ayarlar, "acik_kayit", False)
    y = istemci.post("/kayit", json={"eposta": "kapali@test.local", "ad_soyad": "X", "parola": PAROLA,
                                     "isletme_adi": "X"})
    assert y.status_code == 404


def test_kisa_parola_ve_eposta_parola_422(istemci, acik_kayit):
    temel = {"ad_soyad": "X", "isletme_adi": "X"}
    assert istemci.post("/kayit", json={**temel, "eposta": "kisa@test.local", "parola": "123456789"}).status_code == 422
    assert istemci.post("/kayit", json={**temel, "eposta": "uzun@test.local", "parola": "a" * 129}).status_code == 422
    e = "kendisi@test.local"
    assert istemci.post("/kayit", json={**temel, "eposta": e, "parola": e.upper()}).status_code == 422


# ---------------------------------------------------------------- Giriş ve kilit


def test_giris_dogru_200_yanlis_ve_olmayan_ayni_401(istemci, acik_kayit, kayit_temizligi):
    k = kayit_ol(istemci, kayit_temizligi)
    y = giris(istemci, k["eposta"])
    assert y.status_code == 200
    assert y.json()["isletme_id"] == k["isletme_id"] and len(y.json()["uyelikler"]) == 1   # tek üyelik: seçili

    yanlis = giris(istemci, k["eposta"], "yanlis-parola-123")
    olmayan = giris(istemci, "olmayan-kisi@test.local")
    assert yanlis.status_code == olmayan.status_code == 401
    assert yanlis.json() == olmayan.json() == {"detail": "E-posta veya parola hatalı"}
    assert yanlis.headers.get("www-authenticate") == "Bearer"


def test_bes_hatadan_sonra_kilit_ve_kilit_bitince_giris(istemci, acik_kayit, kayit_temizligi, admin_engine):
    k = kayit_ol(istemci, kayit_temizligi)
    for _ in range(5):
        assert giris(istemci, k["eposta"], "yanlis-parola-123").status_code == 401
    kilitli = giris(istemci, k["eposta"])
    assert kilitli.status_code == 401 and kilitli.json() == {"detail": "E-posta veya parola hatalı"}
    with admin_engine.begin() as con:                    # saati ilerletmek yerine kilidi geçmişe çek
        con.execute(text("UPDATE kullanici_kimlik_bilgileri SET kilit_bitis = now() - interval '1 second' "
                         "WHERE kullanici_id = (SELECT kullanici_id FROM kullanicilar WHERE eposta = :e)"),
                    {"e": k["eposta"]})
    assert giris(istemci, k["eposta"]).status_code == 200


# ---------------------------------------------------------------- Token doğrulama


def _jwt(yuk: dict, anahtar: str | None = None, algoritma: str = "HS256") -> str:
    return jwt.encode(yuk, anahtar if anahtar is not None else ayarlar.jwt_gizli.get_secret_value(), algorithm=algoritma)


def test_gecersiz_tokenlar_401(istemci, iki_kiraci):
    a, _ = iki_kiraci
    simdi = datetime.now(timezone.utc)
    temel = {"sub": str(a.kullanici_id), "isl": str(a.isletme_id), "typ": "erisim", "iat": simdi,
             "exp": simdi + timedelta(minutes=15)}
    gecerli = basliklar(a)["Authorization"].split()[1]
    bozuk = gecerli[:-4] + ("AAAA" if not gecerli.endswith("AAAA") else "BBBB")
    tokenlar = {
        "imza bozuk": bozuk,
        "başka anahtar": _jwt(temel, "baska-bir-anahtar-" + "x" * 32),
        "süresi geçmiş": _jwt({**temel, "iat": simdi - timedelta(hours=1), "exp": simdi - timedelta(minutes=1)}),
        "alg=none": jwt.encode(temel, None, algorithm="none"),
        "typ yanlış": _jwt({**temel, "typ": "yenileme"}),
        "typ yok": _jwt({k: v for k, v in temel.items() if k != "typ"}),
        "sub yok": _jwt({k: v for k, v in temel.items() if k != "sub"}),
        "sub uuid değil": _jwt({**temel, "sub": "yonetici"}),
    }
    assert istemci.get("/musteriler", headers=bearer(gecerli)).status_code == 200
    for ad, token in tokenlar.items():
        y = istemci.get("/musteriler", headers=bearer(token))
        assert y.status_code == 401, ad
    assert istemci.get("/musteriler").status_code == 401                                  # başlıksız
    eski = {"X-Kullanici-Id": str(a.kullanici_id), "X-Isletme-Id": str(a.isletme_id)}     # K8: başlık kimliği yok
    assert istemci.get("/musteriler", headers=eski).status_code == 401
    assert istemci.get("/musteriler", headers={"Authorization": f"Basic {gecerli}"}).status_code == 401


def test_tokendaki_isl_uye_olunmayan_isletme_403(istemci, iki_kiraci):
    a, b = iki_kiraci
    from servisler.kimlik import erisim_tokeni_uret
    assert istemci.get("/musteriler", headers=bearer(erisim_tokeni_uret(a.kullanici_id, b.isletme_id))).status_code == 403
    assert istemci.get("/musteriler", headers=bearer(erisim_tokeni_uret(a.kullanici_id, None))).status_code == 403


def test_uyelik_silinince_ayni_token_403(istemci, iki_kiraci, calisan, admin_engine):
    h = basliklar(calisan)
    assert istemci.get("/musteriler", headers=h).status_code == 200
    with admin_engine.begin() as con:
        con.execute(text("DELETE FROM uyelikler WHERE kullanici_id = :k"), {"k": str(calisan.kullanici_id)})
    assert istemci.get("/musteriler", headers=h).status_code == 403                       # rol her istekte DB'den


def test_isletme_pasifse_403(istemci, iki_kiraci, admin_engine):
    a, _ = iki_kiraci
    with admin_engine.begin() as con:
        con.execute(text("UPDATE isletmeler SET durum = 'askida' WHERE isletme_id = :i"), {"i": str(a.isletme_id)})
    assert istemci.get("/musteriler", headers=basliklar(a)).status_code == 403


# ---------------------------------------------------------------- Yenileme, çıkış


def test_yenileme_tek_kullanimlik_ve_tekrar_kullanimda_aile_iptali(istemci, acik_kayit, kayit_temizligi):
    k = kayit_ol(istemci, kayit_temizligi)
    y1 = istemci.post("/oturum/yenile", json={"yenileme_tokeni": k["yenileme_tokeni"]})
    assert y1.status_code == 200
    yeni = y1.json()
    assert yeni["yenileme_tokeni"] != k["yenileme_tokeni"] and yeni["isletme_id"] == k["isletme_id"]
    assert istemci.get("/musteriler", headers=bearer(yeni["erisim_tokeni"])).status_code == 200

    assert istemci.post("/oturum/yenile", json={"yenileme_tokeni": k["yenileme_tokeni"]}).status_code == 401
    assert istemci.post("/oturum/yenile", json={"yenileme_tokeni": yeni["yenileme_tokeni"]}).status_code == 401


def test_cikis_sonrasi_yenileme_401(istemci, acik_kayit, kayit_temizligi):
    k = kayit_ol(istemci, kayit_temizligi)
    assert istemci.post("/oturum/cikis", json={"yenileme_tokeni": k["yenileme_tokeni"]}).status_code == 204
    assert istemci.post("/oturum/yenile", json={"yenileme_tokeni": k["yenileme_tokeni"]}).status_code == 401


def test_bilinmeyen_yenileme_tokeni_401(istemci):
    assert istemci.post("/oturum/yenile", json={"yenileme_tokeni": "uydurma"}).status_code == 401


# ---------------------------------------------------------------- İşletme seçme ve /ben


def _iki_uyelikli_kullanici(istemci, kayit_temizligi, a):
    """Kendi stüdyosunun sahibi + A işletmesine çalışan olarak davetli kullanıcı."""
    k = kayit_ol(istemci, kayit_temizligi)
    kod = istemci.post("/davetler", json={"rol": "calisan"}, headers=basliklar(a)).json()["kod"]
    assert istemci.post("/davetler/kabul", json={"kod": kod}, headers=bearer(k["erisim_tokeni"])).status_code == 200
    return k


def test_isletme_secme(istemci, acik_kayit, kayit_temizligi, iki_kiraci):
    a, b = iki_kiraci
    k = _iki_uyelikli_kullanici(istemci, kayit_temizligi, a)

    g = giris(istemci, k["eposta"]).json()
    assert g["isletme_id"] is None and {u["isletme_id"] for u in g["uyelikler"]} == {k["isletme_id"], str(a.isletme_id)}
    assert istemci.get("/musteriler", headers=bearer(g["erisim_tokeni"])).status_code == 403   # işletme seçilmedi

    sec = istemci.post("/oturum/isletme-sec", json={"isletme_id": str(a.isletme_id), "yenileme_tokeni": g["yenileme_tokeni"]},
                       headers=bearer(g["erisim_tokeni"]))
    assert sec.status_code == 200 and sec.json()["isletme_id"] == str(a.isletme_id)
    musteriler = istemci.get("/musteriler", headers=bearer(sec.json()["erisim_tokeni"])).json()["ogeler"]
    assert [m["musteri_id"] for m in musteriler] == [str(a.musteri_id)]

    # seçim yenileme oturumuna yazıldı: yenilenen token aynı işletmeyle gelir
    yen = istemci.post("/oturum/yenile", json={"yenileme_tokeni": g["yenileme_tokeni"]}).json()
    assert yen["isletme_id"] == str(a.isletme_id)

    red = istemci.post("/oturum/isletme-sec", json={"isletme_id": str(b.isletme_id), "yenileme_tokeni": yen["yenileme_tokeni"]},
                       headers=bearer(yen["erisim_tokeni"]))
    assert red.status_code == 403
    assert istemci.post("/oturum/isletme-sec", json={"isletme_id": str(a.isletme_id)},
                        headers=bearer(yen["erisim_tokeni"])).status_code == 422          # yenileme_tokeni zorunlu
    assert istemci.post("/oturum/isletme-sec", json={"isletme_id": str(a.isletme_id), "yenileme_tokeni": "uydurma"},
                        headers=bearer(yen["erisim_tokeni"])).status_code == 401


def test_ben(istemci, acik_kayit, kayit_temizligi):
    k = kayit_ol(istemci, kayit_temizligi, ad_soyad="Ayşe Stüdyo")
    y = istemci.get("/ben", headers=bearer(k["erisim_tokeni"]))
    assert y.status_code == 200
    b = y.json()
    assert (b["eposta"], b["ad_soyad"]) == (k["eposta"], "Ayşe Stüdyo")
    assert b["uyelikler"] == [{"isletme_id": k["isletme_id"], "isletme_adi": "Test Stüdyo", "rol": "sahip"}]
    assert istemci.get("/ben").status_code == 401


def test_rastgele_kullanici_tokeni_kiraciya_giremez(istemci, iki_kiraci):
    a, _ = iki_kiraci
    from servisler.kimlik import erisim_tokeni_uret
    assert istemci.get("/musteriler", headers=bearer(erisim_tokeni_uret(uuid.uuid4(), a.isletme_id))).status_code == 403
