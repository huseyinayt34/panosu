"""Davet ve üye testleri (Adım 8)."""

import pytest
from sqlalchemy import text

from conftest import basliklar
from kimlik_yardimci import PAROLA, bearer, eposta, istemci, kayit_temizligi  # noqa: F401


def _davet(istemci, kiraci, rol="calisan"):
    return istemci.post("/davetler", json={"rol": rol}, headers=basliklar(kiraci))


def _davetle_kayit(istemci, epostalar, kod, **alanlar):
    e = alanlar.pop("eposta", None) or eposta()
    epostalar.append(e)
    return istemci.post("/kayit/davet", json={"kod": kod, "eposta": e, "ad_soyad": "Personel", "parola": PAROLA,
                                              **alanlar})


def test_sahip_yonetici_ve_calisan_davet_eder(istemci, iki_kiraci):
    a, _ = iki_kiraci
    for rol in ("yonetici", "calisan"):
        y = _davet(istemci, a, rol)
        assert y.status_code == 201, y.text
        assert y.json()["rol"] == rol and len(y.json()["kod"]) >= 20
    assert _davet(istemci, a, "sahip").status_code == 422                                    # sahip davet edilemez
    acik = istemci.get("/davetler", headers=basliklar(a)).json()
    assert len(acik) == 2 and all("kod" not in d for d in acik)


def test_yonetici_yonetici_davet_edemez_calisan_hic_edemez(istemci, iki_kiraci, calisan, kayit_temizligi):
    a, _ = iki_kiraci
    assert _davet(istemci, calisan).status_code == 403
    assert istemci.get("/davetler", headers=basliklar(calisan)).status_code == 403

    kod = _davet(istemci, a, "yonetici").json()["kod"]
    yonetici = _davetle_kayit(istemci, kayit_temizligi, kod).json()
    assert _davet_bearer(istemci, yonetici, "yonetici").status_code == 403
    assert _davet_bearer(istemci, yonetici, "calisan").status_code == 201


def _davet_bearer(istemci, cift, rol):
    return istemci.post("/davetler", json={"rol": rol}, headers=bearer(cift["erisim_tokeni"]))


def test_davetle_kayit_dogru_rol_ve_kod_tek_kullanimlik(istemci, iki_kiraci, kayit_temizligi):
    a, _ = iki_kiraci
    kod = _davet(istemci, a, "yonetici").json()["kod"]
    y = _davetle_kayit(istemci, kayit_temizligi, kod)
    assert y.status_code == 201 and y.json()["isletme_id"] == str(a.isletme_id)
    uyeler = istemci.get("/uyeler", headers=basliklar(a)).json()
    assert sorted(u["rol"] for u in uyeler) == ["sahip", "yonetici"]
    assert istemci.get("/musteriler", headers=bearer(y.json()["erisim_tokeni"])).status_code == 200

    assert _davetle_kayit(istemci, kayit_temizligi, kod).status_code == 404                  # ikinci kullanım
    assert istemci.get("/davetler", headers=basliklar(a)).json() == []                         # artık açık değil


def test_suresi_gecmis_ve_iptal_edilmis_davet_404(istemci, iki_kiraci, kayit_temizligi, admin_engine):
    a, _ = iki_kiraci
    gecmis = _davet(istemci, a).json()
    with admin_engine.begin() as con:
        con.execute(text("UPDATE davetler SET son_kullanma = now() - interval '1 second' WHERE davet_id = :d"),
                    {"d": gecmis["davet_id"]})
    assert _davetle_kayit(istemci, kayit_temizligi, gecmis["kod"]).status_code == 404

    iptal = _davet(istemci, a).json()
    assert istemci.post(f"/davetler/{iptal['davet_id']}/iptal", headers=basliklar(a)).status_code == 204
    assert _davetle_kayit(istemci, kayit_temizligi, iptal["kod"]).status_code == 404
    assert istemci.post(f"/davetler/{iptal['davet_id']}/iptal", headers=basliklar(a)).status_code == 404
    assert _davetle_kayit(istemci, kayit_temizligi, "uydurma-kod").status_code == 404


def test_gecersiz_davette_kullanici_olusmaz(istemci, iki_kiraci, kayit_temizligi, admin_engine):
    e = eposta()
    assert _davetle_kayit(istemci, kayit_temizligi, "uydurma-kod", eposta=e).status_code == 404
    with admin_engine.connect() as con:
        assert con.scalar(text("SELECT count(*) FROM kullanicilar WHERE eposta = :e"), {"e": e}) == 0


def test_baska_kiracinin_davetini_listeleyemez_iptal_edemez(istemci, iki_kiraci):
    a, b = iki_kiraci
    d = _davet(istemci, a).json()
    assert istemci.get("/davetler", headers=basliklar(b)).json() == []
    assert istemci.post(f"/davetler/{d['davet_id']}/iptal", headers=basliklar(b)).status_code == 404
    assert len(istemci.get("/davetler", headers=basliklar(a)).json()) == 1                    # A'nınki duruyor


def test_davet_kabul_zaten_uye_409_ve_gecersiz_404(istemci, iki_kiraci, kayit_temizligi):
    a, _ = iki_kiraci
    personel = _davetle_kayit(istemci, kayit_temizligi, _davet(istemci, a).json()["kod"]).json()
    ikinci_kod = _davet(istemci, a).json()["kod"]
    h = bearer(personel["erisim_tokeni"])
    assert istemci.post("/davetler/kabul", json={"kod": ikinci_kod}, headers=h).status_code == 409
    assert len(istemci.get("/davetler", headers=basliklar(a)).json()) == 1                    # tüketilmedi
    assert istemci.post("/davetler/kabul", json={"kod": "uydurma"}, headers=h).status_code == 404
    assert istemci.post("/davetler/kabul", json={"kod": ikinci_kod}).status_code == 401       # giriş gerekli


def test_uyeler_yalniz_aktif_isletmenin(istemci, iki_kiraci, capraz_davet_temizligi):
    a, b = iki_kiraci
    # A'nın sahibi B'ye de çalışan olarak katılır: A'nın üye listesinde B üyeliği görünmemeli
    kod = _davet(istemci, b).json()["kod"]
    assert istemci.post("/davetler/kabul", json={"kod": kod}, headers=basliklar(a)).status_code == 200
    uyeler = istemci.get("/uyeler", headers=basliklar(a)).json()
    assert [(u["kullanici_id"], u["rol"]) for u in uyeler] == [(str(a.kullanici_id), "sahip")]


@pytest.fixture()
def capraz_davet_temizligi(admin_engine, iki_kiraci):
    """A'nın sahibi B'nin davetini kullanınca B'nin davet satırı A'nın kullanıcısına bağlanır; kiracı temizliğinden
    önce (fixture sırası) bu davetler silinir."""
    yield
    _, b = iki_kiraci
    with admin_engine.begin() as con:
        con.execute(text("DELETE FROM davetler WHERE isletme_id = :i"), {"i": str(b.isletme_id)})


def test_uye_silme_ve_son_sahip(istemci, iki_kiraci, calisan, admin_engine):
    a, _ = iki_kiraci
    assert istemci.delete(f"/uyeler/{a.kullanici_id}", headers=basliklar(a)).status_code == 409   # kendini / son sahip
    assert istemci.delete(f"/uyeler/{calisan.kullanici_id}", headers=basliklar(calisan)).status_code == 403
    assert istemci.delete(f"/uyeler/{calisan.kullanici_id}", headers=basliklar(a)).status_code == 204
    assert istemci.delete(f"/uyeler/{calisan.kullanici_id}", headers=basliklar(a)).status_code == 404
    with admin_engine.connect() as con:
        assert con.scalar(text("SELECT count(*) FROM uyelikler WHERE isletme_id = :i AND rol = 'sahip'"),
                          {"i": str(a.isletme_id)}) == 1


def test_baska_kiracinin_uyesi_silinemez(istemci, iki_kiraci):
    a, b = iki_kiraci
    assert istemci.delete(f"/uyeler/{b.kullanici_id}", headers=basliklar(a)).status_code == 404
