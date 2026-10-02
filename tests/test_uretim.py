"""Adım 11 üretim modu (`docs/adim-11-tasarim.md`): ayar doğrulaması (K22), salt okunur demo (K25), demo giriş formu
(K26), üretim başlıkları (K27)."""

import secrets

import pytest
from pydantic import SecretStr, ValidationError

from conftest import basliklar
from kimlik_yardimci import PAROLA, acik_kayit, giris, istemci, kayit_ol, kayit_temizligi  # noqa: F401

SALT_OKUNUR_MESAJI = "Bu demo salt okunur; veri değiştirilemez."
URETIM_BASLIKLARI = {
    "strict-transport-security": "max-age=31536000",
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
    "x-frame-options": "DENY",
}


# ---------------------------------------------------------------- Ayarlar doğrulayıcısı (K22)

def _ayarlar(**alanlar):
    from config import Ayarlar
    degerler = {"veritabani_url": "postgresql+psycopg2://panosu_app:x@localhost:5432/panosu_demo",
                "jwt_gizli": secrets.token_urlsafe(32), "ortam": "uretim", "migrasyon_url": None,
                "acik_kayit": False, **alanlar}
    return Ayarlar(_env_file=None, **degerler)


def test_uretim_ayarlari_gecerli():
    a = _ayarlar()
    assert a.ortam == "uretim" and a.salt_okunur is False
    assert a.demo_giris_eposta is None and a.demo_giris_parola is None


@pytest.mark.parametrize("ihlal", [
    {"veritabani_url": "postgresql+psycopg2://postgres:{p}@localhost:5432/panosu_demo"},
    {"migrasyon_url": "postgresql+psycopg2://postgres:{p}@localhost:5432/panosu_demo"},
    {"acik_kayit": True},
], ids=["kullanici-panosu_app-degil", "migrasyon-tanimli", "acik-kayit"])
def test_uretim_ihlali_hata_ve_parola_yok(ihlal):
    parola = secrets.token_urlsafe(16)
    alanlar = {k: v.format(p=parola) if isinstance(v, str) else v for k, v in ihlal.items()}
    with pytest.raises(ValidationError) as hata:
        _ayarlar(**alanlar)
    assert parola not in str(hata.value) and parola not in repr(hata.value)


def test_gelistirmede_kisit_yok():
    a = _ayarlar(ortam="gelistirme", acik_kayit=True,
                 veritabani_url="postgresql+psycopg2://postgres:x@localhost:5432/panosu",
                 migrasyon_url="postgresql+psycopg2://postgres:x@localhost:5432/panosu")
    assert a.ortam == "gelistirme"


def test_bilinmeyen_ortam_hata():
    with pytest.raises(ValidationError):
        _ayarlar(ortam="prod")


# ---------------------------------------------------------------- Salt okunur (K25)

@pytest.fixture()
def salt_okunur(monkeypatch):
    from config import ayarlar
    monkeypatch.setattr(ayarlar, "salt_okunur", True)


def test_salt_okunur_yazma_403(istemci, iki_kiraci, salt_okunur):
    a, _ = iki_kiraci
    b = basliklar(a)
    istekler = [
        istemci.post("/musteriler", json={"ad_soyad": "Yeni Müşteri"}, headers=b),
        istemci.put("/giderler/2026-10", json={"kalemler": []}, headers=b),
        istemci.patch(f"/musteriler/{a.musteri_id}", json={"ad_soyad": "Değişti"}, headers=b),
        istemci.delete(f"/musteriler/{a.musteri_id}", headers=b),
        istemci.post("/kayit", json={}),
        istemci.post("/giris/", data={}),                     # sondaki "/" serbest değil
    ]
    for y in istekler:
        assert y.status_code == 403, y.request.url
        assert y.json() == {"detail": SALT_OKUNUR_MESAJI}
    musteri = istemci.get(f"/musteriler/{a.musteri_id}", headers=b)
    assert musteri.status_code == 200 and musteri.json()["ad_soyad"] == a.musteri_adi


def test_salt_okunur_okuma_serbest(istemci, salt_okunur):
    assert istemci.get("/saglik").status_code == 200
    y = istemci.get("/pano", follow_redirects=False)
    assert (y.status_code, y.headers["location"]) == (303, "/giris")
    assert istemci.head("/statik/panel.css").status_code == 200


def test_salt_okunur_giris_uclari_calisir(istemci, acik_kayit, kayit_temizligi, monkeypatch):
    k = kayit_ol(istemci, kayit_temizligi)                   # kayıt salt okunur açılmadan önce
    from config import ayarlar
    monkeypatch.setattr(ayarlar, "salt_okunur", True)

    api = giris(istemci, k["eposta"])
    assert api.status_code == 200
    istemci.cookies.clear()
    istemci.get("/giris")
    web = istemci.post("/giris", data={"eposta": k["eposta"], "parola": PAROLA,
                                       "csrf": istemci.cookies.get("panosu_csrf")}, follow_redirects=False)
    assert (web.status_code, web.headers["location"]) == (303, "/pano")
    assert istemci.get("/pano").status_code == 200
    cikis = istemci.post("/cikis", data={"csrf": istemci.cookies.get("panosu_csrf")}, follow_redirects=False)
    assert (cikis.status_code, cikis.headers["location"]) == (303, "/giris")


def test_salt_okunur_kapaliyken_yazma_calisir(istemci, iki_kiraci):
    a, _ = iki_kiraci
    y = istemci.post("/musteriler", json={"ad_soyad": "Yeni Müşteri"}, headers=basliklar(a))
    assert y.status_code == 201


# ---------------------------------------------------------------- Üretim başlıkları (K27)

def test_uretimde_guvenlik_basliklari(istemci, monkeypatch):
    from config import ayarlar
    monkeypatch.setattr(ayarlar, "ortam", "uretim")
    for adres in ("/statik/panel.css", "/giris", "/saglik"):
        y = istemci.get(adres, follow_redirects=False)
        for ad, deger in URETIM_BASLIKLARI.items():
            assert y.headers.get(ad) == deger, (adres, ad)


def test_gelistirmede_hsts_yok(istemci):
    y = istemci.get("/statik/panel.css")
    assert y.status_code == 200 and "strict-transport-security" not in y.headers


# ---------------------------------------------------------------- Demo giriş formu (K26)

@pytest.fixture()
def demo_girisi(monkeypatch):
    from config import ayarlar
    eposta, parola = f"demo-{secrets.token_hex(4)}@test.local", secrets.token_urlsafe(18)
    monkeypatch.setattr(ayarlar, "demo_giris_eposta", eposta)
    monkeypatch.setattr(ayarlar, "demo_giris_parola", SecretStr(parola))
    return eposta, parola


def test_demo_girisi_form_dolu(istemci, demo_girisi):
    eposta, parola = demo_girisi
    y = istemci.get("/giris")
    assert y.status_code == 200
    assert f'value="{eposta}"' in y.text and f'value="{parola}"' in y.text
    assert "Bu bir demo; Giriş'e basmanız yeterli." in y.text


@pytest.mark.parametrize("eksik", ["demo_giris_eposta", "demo_giris_parola"])
def test_demo_girisi_biri_eksikse_bos(istemci, demo_girisi, monkeypatch, eksik):
    from config import ayarlar
    eposta, parola = demo_girisi
    monkeypatch.setattr(ayarlar, eksik, None)
    y = istemci.get("/giris")
    assert eposta not in y.text and parola not in y.text and "Bu bir demo" not in y.text
    assert 'name="parola" autocomplete' in y.text


def test_basarisiz_giriste_yazilan_parola_yok(istemci, demo_girisi):
    _, demo_parola = demo_girisi
    yazilan = secrets.token_urlsafe(18)
    istemci.get("/giris")
    y = istemci.post("/giris", data={"eposta": "yok@test.local", "parola": yazilan,
                                     "csrf": istemci.cookies.get("panosu_csrf")})
    assert y.status_code == 401
    assert yazilan not in y.text
    assert f'value="{demo_parola}"' in y.text                 # parola alanı yalnızca demo parolasıyla dolar


# ---------------------------------------------------------------- Demo kurulumu (K24; ağır kurulum burada çalışmaz)

@pytest.fixture()
def baglanti_yasak(monkeypatch):
    """demo_kur'un veritabanına bağlanmaya çalışması testi düşürür."""
    from sentetik import demo_kur

    def _yasak(*_a, **_k):
        raise AssertionError("bağlantı kurulmamalıydı")
    monkeypatch.setattr(demo_kur, "create_engine", _yasak)
    monkeypatch.setattr(demo_kur, "kur", _yasak)


def test_demo_kur_demo_disi_ad_baglantisiz_reddedilir(baglanti_yasak, monkeypatch, capsys):
    from sentetik import demo_kur
    monkeypatch.setenv("PANOSU_DEMO_PAROLA", secrets.token_urlsafe(18))
    for ad in ("panosu", "panosu_test", "panosu_demo_x"):
        with pytest.raises(SystemExit) as hata:
            demo_kur.main(["--veritabani", ad])
        assert "_demo" in str(hata.value.code)


def test_demo_kur_parola_degiskeni_yoksa_acik_hata(baglanti_yasak, monkeypatch):
    from sentetik import demo_kur
    monkeypatch.delenv("PANOSU_DEMO_PAROLA", raising=False)
    with pytest.raises(SystemExit) as hata:
        demo_kur.main(["--veritabani", "panosu_demo"])
    assert "PANOSU_DEMO_PAROLA" in str(hata.value.code)


def test_demo_kur_parola_kurala_uymuyorsa_hata_ve_parola_yok(baglanti_yasak, monkeypatch):
    from sentetik import demo_kur
    kisa = secrets.token_hex(3)
    monkeypatch.setenv("PANOSU_DEMO_PAROLA", kisa)
    with pytest.raises(SystemExit) as hata:
        demo_kur.main(["--veritabani", "panosu_demo"])
    assert "PANOSU_DEMO_PAROLA" in str(hata.value.code) and kisa not in str(hata.value.code)


def test_uygulama_parolasi_panosu_app_disinda_reddedilir(baglanti_yasak):
    from sentetik.demo_kur import KurulumHatasi, uygulama_parolasi_ayarla
    parola = secrets.token_urlsafe(16)
    with pytest.raises(KurulumHatasi) as hata:
        uygulama_parolasi_ayarla(f"postgresql+psycopg2://postgres:{parola}@h/panosu_demo",
                                 f"postgresql+psycopg2://postgres:{parola}@h/panosu_demo")
    assert "panosu_app" in str(hata.value) and parola not in str(hata.value)


def test_uygulama_parolasi_hata_metninde_parola_yok(monkeypatch, capsys):
    """Bağlantı hatası parolayı içerse bile çıktıya yalnızca istisna türü yazılır."""
    from sentetik import demo_kur
    parola, yonetici_parolasi = secrets.token_urlsafe(16), secrets.token_urlsafe(16)

    class Patlayan:
        def begin(self):
            raise RuntimeError(f"bağlantı hatası {parola} {yonetici_parolasi}")

        def dispose(self):
            pass

    monkeypatch.setattr(demo_kur, "create_engine", lambda _url: Patlayan())
    monkeypatch.setattr(demo_kur, "kur", lambda *_a, **_k: pytest.fail("kurulum çalışmamalıydı"))
    monkeypatch.setenv("PANOSU_DEMO_PAROLA", secrets.token_urlsafe(18))
    monkeypatch.setattr(demo_kur, "baglanti_adresleri", lambda _v: (
        f"postgresql+psycopg2://postgres:{yonetici_parolasi}@h/panosu_demo",
        f"postgresql+psycopg2://panosu_app:{parola}@h/panosu_demo"))
    with pytest.raises(SystemExit) as hata:
        demo_kur.main(["--veritabani", "panosu_demo", "--uygulama-parolasi-ayarla"])
    metin = str(hata.value.code) + capsys.readouterr().out
    assert "RuntimeError" in metin
    assert parola not in metin and yonetici_parolasi not in metin
