"""Giderler, /panel/finans ve /panel/sessiz-uyeler (TestClient + panosu_test, RLS gerçek rolle)."""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from conftest import basliklar
from models import IsletmeGideri
from servisler.finans_servisi import finans_ozeti, zarar_icin_kayip_uye

D = Decimal
BUGUN = datetime.now(timezone(timedelta(hours=3))).date()          # işletme saat dilimi: Europe/Istanbul


@pytest.fixture()
def istemci():
    from main import app
    return TestClient(app)


# ---------------------------------------------------------------- Giderler

def test_gider_put_olusturur_gunceller_null_degismez(istemci, iki_kiraci):
    a, _ = iki_kiraci
    y = istemci.put("/giderler/2026-09", json={"kira": "45000.00", "personel": "60000"}, headers=basliklar(a))
    assert y.status_code == 200, y.text
    assert (D(y.json()["kira"]), D(y.json()["personel"]), y.json()["faturalar"]) == (D("45000"), D("60000"), None)
    assert D(y.json()["toplam"]) == D("105000")

    y = istemci.put("/giderler/2026-09", json={"kira": "47000.00", "personel": None, "faturalar": "8000"},
                    headers=basliklar(a))
    g = y.json()
    assert (D(g["kira"]), D(g["personel"]), D(g["faturalar"]), g["diger"]) == (D("47000"), D("60000"), D("8000"), None)
    assert istemci.get("/giderler/2026-09", headers=basliklar(a)).json() == g
    assert istemci.get("/giderler/2026-08", headers=basliklar(a)).json()["toplam"] is None


@pytest.mark.parametrize("ay,govde", [("2026-13", {"kira": "1"}), ("2026-9", {"kira": "1"}),
                                      ("2026-09", {"kira": "-1"}), ("2026-09", {"elektrik": "1"})])
def test_gider_gecersiz_422(istemci, iki_kiraci, ay, govde):
    a, _ = iki_kiraci
    assert istemci.put(f"/giderler/{ay}", json=govde, headers=basliklar(a)).status_code == 422


def test_gider_calisan_403(istemci, iki_kiraci, calisan):
    assert istemci.put("/giderler/2026-09", json={"kira": "1"}, headers=basliklar(calisan)).status_code == 403
    assert istemci.get("/giderler/2026-09", headers=basliklar(calisan)).status_code == 403
    assert istemci.get("/panel/finans", params={"ay": "2026-09"}, headers=basliklar(calisan)).status_code == 403


def test_baska_kiracinin_gideri_gorunmez(istemci, iki_kiraci, oturum):
    a, b = iki_kiraci
    istemci.put("/giderler/2026-09", json={"kira": "45000"}, headers=basliklar(b))
    assert istemci.get("/giderler/2026-09", headers=basliklar(a)).json()["toplam"] is None
    db = oturum(a)
    assert db.scalars(select(IsletmeGideri)).all() == []                                # DB düzeyinde (RLS)
    db.add(IsletmeGideri(isletme_id=b.isletme_id, ay=date(2026, 9, 1), kategori="kira", tutar=D("1")))
    with pytest.raises(DBAPIError):                                                     # RLS WITH CHECK
        db.flush()


# ---------------------------------------------------------------- Finans (tamamlanmış aylar: Ağustos, Eylül 2026)

def _finans_hazirla(istemci, a):
    for govde in ({"baslangic_tarihi": "2026-08-17", "bitis_tarihi": "2026-09-16", "ucret": "3000.00"},
                  {"baslangic_tarihi": "2026-09-16", "bitis_tarihi": "2026-10-16", "ucret": "3000.00"}):
        y = istemci.post(f"/musteriler/{a.musteri_id}/paketler", json={"tur": "sure", "ad": "1 Aylık", **govde},
                         headers=basliklar(a))
        assert y.status_code == 201, y.text
    y = istemci.post(f"/musteriler/{a.musteri_id}/ziyaretler",
                     json={"ziyaret_zamani": "2026-09-10T12:00:00+03:00", "toplam_tutar": "250.00"}, headers=basliklar(a))
    assert y.status_code == 201, y.text


def test_finans_tamamlanmis_ay(istemci, iki_kiraci):
    a, _ = iki_kiraci
    _finans_hazirla(istemci, a)
    istemci.put("/giderler/2026-09", json={"kira": "1000.00", "personel": "500.00"}, headers=basliklar(a))

    f = istemci.get("/panel/finans", params={"ay": "2026-09"}, headers=basliklar(a)).json()
    # 3000 / 30 gün = 100/gün: 1. paket 1–15 Eylül, 2. paket 16–30 Eylül → 3000; ziyaret 250
    assert D(f["gercek_gelir"]) == D("3250.00")
    assert D(f["kasaya_giren"]) == D("3250.00")                                         # 2. paketin ücreti 16 Eylül'de
    assert (D(f["gider_toplam"]), D(f["gider_bugune_kadar"]), D(f["kar_zarar"])) == (D("1500"), D("1500"), D("1750"))
    assert f["gider_girilmedi"] is False
    assert len(f["gunluk"]) == 30
    gun16 = next(g for g in f["gunluk"] if g["tarih"] == "2026-09-16")
    assert (D(gun16["kasaya_giren"]), D(gun16["gercek_gelir"]), D(gun16["gider_payi"])) == (D("3000"), D("100"), D("50"))
    assert D(gun16["net"]) == D("50")
    assert sum(D(g["net"]) for g in f["gunluk"]) == D(f["kar_zarar"])
    assert D(f["ortalama_aktif_uye"]) == D("1.00")
    assert D(f["uye_basi_aylik_gelir"]) == D("3250.00")
    assert f["basabas_uye_sayisi"] == 1                                                 # ⌈1500 / 3250⌉
    assert f["gecmis_ay"] is True
    assert f["aktif_uye_sayisi"] == 1                    # 30 Eylül'de 2. paket aktif; artık BUGUN'e bağlı değil (K2)
    assert (f["basabas_farki"], f["zarar_icin_kayip_uye"]) == (None, None)
    assert D(f["basabas_farki_ortalama"]) == D("0.00")                                  # ort 1,00 − başabaş 1
    assert D(f["riskteki_para_45_gun"]) == D("0")


def test_finans_gider_girilmedi(istemci, iki_kiraci):
    a, _ = iki_kiraci
    _finans_hazirla(istemci, a)
    f = istemci.get("/panel/finans", params={"ay": "2026-08"}, headers=basliklar(a)).json()
    assert (f["gider_toplam"], f["kar_zarar"], f["gider_girilmedi"], f["basabas_uye_sayisi"]) == (None, None, True, None)
    assert (f["basabas_farki"], f["zarar_icin_kayip_uye"]) == (None, None)
    assert D(f["kasaya_giren"]) == D("3000.00") and D(f["gercek_gelir"]) == D("1500.00")   # 17–31 Ağustos
    assert all(g["gider_payi"] is None and g["net"] is None for g in f["gunluk"])


def _ozet(oturum, a, ay, bugun):
    return finans_ozeti(oturum(a), ay, bugun=bugun)


def test_finans_ilk_7_gunde_basabas_gecen_aydan(istemci, iki_kiraci, oturum):
    a, _ = iki_kiraci
    _finans_hazirla(istemci, a)
    istemci.put("/giderler/2026-09", json={"kira": "1000.00", "personel": "500.00"}, headers=basliklar(a))

    f = _ozet(oturum, a, date(2026, 10, 1), date(2026, 10, 3))
    assert (f.gecen_gun, f.onceki_ay, f.onceki_ay_kar_zarar) == (3, date(2026, 9, 1), D("1750.00"))
    assert f.basabas_kaynak_ay == date(2026, 9, 1)                      # ayın 3'ü: Eylül'ün tamamlanmış verisi
    assert (f.uye_basi_aylik_gelir, f.basabas_uye_sayisi, f.ortalama_aktif_uye) == (D("3250.00"), 1, D("1.00"))
    assert f.gercek_gelir == D("300.00") and f.gider_girilmedi                # Ekim'in kendi verisi değişmez
    assert f.basabas_farki == f.aktif_uye_sayisi - 1


def test_finans_7_gunden_sonra_basabas_bu_aydan(istemci, iki_kiraci, oturum):
    a, _ = iki_kiraci
    _finans_hazirla(istemci, a)
    istemci.put("/giderler/2026-09", json={"kira": "1000.00", "personel": "500.00"}, headers=basliklar(a))

    f = _ozet(oturum, a, date(2026, 10, 1), date(2026, 10, 8))
    assert (f.gecen_gun, f.basabas_kaynak_ay) == (8, date(2026, 10, 1))
    assert f.uye_basi_aylik_gelir == D("3100.00")                            # 800 × 31/8 / 1 üye
    assert f.basabas_uye_sayisi is None                                      # Ekim gideri yok
    assert f.onceki_ay_kar_zarar == D("1750.00")


def test_finans_gecmis_ay_kaynak_kendisi(istemci, iki_kiraci, oturum):
    a, _ = iki_kiraci
    _finans_hazirla(istemci, a)
    istemci.put("/giderler/2026-09", json={"kira": "1000.00", "personel": "500.00"}, headers=basliklar(a))
    f = _ozet(oturum, a, date(2026, 9, 1), date(2026, 10, 3))
    assert (f.basabas_kaynak_ay, f.gecen_gun, f.basabas_uye_sayisi) == (date(2026, 9, 1), 30, 1)
    assert (f.onceki_ay, f.onceki_ay_kar_zarar, f.onceki_ay_gider_girilmedi) == (date(2026, 8, 1), None, True)


def test_finans_icinde_bulunulan_ay_eski_tanim(istemci, iki_kiraci, oturum):
    a, _ = iki_kiraci
    _finans_hazirla(istemci, a)
    istemci.put("/giderler/2026-09", json={"kira": "1000.00", "personel": "500.00"}, headers=basliklar(a))
    f = _ozet(oturum, a, date(2026, 10, 1), date(2026, 10, 3))
    assert (f.gecmis_ay, f.basabas_farki_ortalama) == (False, None)
    assert (f.aktif_uye_sayisi, f.basabas_uye_sayisi) == (1, 1)                 # 3 Ekim'de 2. paket aktif
    assert (f.basabas_farki, f.zarar_icin_kayip_uye) == (0, 1)                  # aktif − başabaş (bugünün aktif üyesi)


def test_finans_gecmis_ay_aktif_ay_sonuna_gore(istemci, iki_kiraci, oturum):
    a, _ = iki_kiraci
    _finans_hazirla(istemci, a)
    f = _ozet(oturum, a, date(2026, 10, 1), date(2026, 11, 5))                  # 2. paket 16 Ekim'de bitti
    assert f.gecmis_ay is True
    assert f.aktif_uye_sayisi == 0                                               # 31 Ekim
    assert f.ortalama_aktif_uye == D("0.48")                                     # 1–15 Ekim: 15 / 31 gün
    assert (f.basabas_farki, f.zarar_icin_kayip_uye) == (None, None)


def test_finans_gecmis_ay_gider_yoksa_ortalama_fark_yok(istemci, iki_kiraci):
    a, _ = iki_kiraci
    _finans_hazirla(istemci, a)
    f = istemci.get("/panel/finans", params={"ay": "2026-08"}, headers=basliklar(a)).json()
    assert (f["gecmis_ay"], f["basabas_farki_ortalama"], f["basabas_uye_sayisi"]) == (True, None, None)
    assert f["aktif_uye_sayisi"] == 1                                            # 31 Ağustos'ta 1. paket aktif


def test_finans_yanitinda_yeni_alanlar(istemci, iki_kiraci):
    a, _ = iki_kiraci
    f = istemci.get("/panel/finans", params={"ay": "2026-09"}, headers=basliklar(a)).json()
    assert {"gecen_gun", "onceki_ay", "onceki_ay_kar_zarar", "onceki_ay_gider_girilmedi", "basabas_kaynak_ay",
            "zarar_icin_kayip_uye"} <= f.keys()
    assert f["basabas_kaynak_ay"] == "2026-09-01" and f["onceki_ay"] == "2026-08-01"


@pytest.mark.parametrize("fark,beklenen", [(11, 12), (0, 1), (-3, None), (None, None)])
def test_zarar_icin_kayip_uye(fark, beklenen):
    # Başabaş tavanla bulunur: başabaştaki üyeyle kâr ≥ 0, zarar 1 altında başlar. None: başabaş yok.
    assert zarar_icin_kayip_uye(fark) == beklenen


def test_finans_ay_bicimi_422(istemci, iki_kiraci):
    a, _ = iki_kiraci
    assert istemci.get("/panel/finans", params={"ay": "2026-9"}, headers=basliklar(a)).status_code == 422


def test_finans_bu_ay_gelecek_gun_yok(istemci, iki_kiraci):
    a, _ = iki_kiraci
    f = istemci.get("/panel/finans", headers=basliklar(a)).json()
    assert f["ay"] == BUGUN.replace(day=1).isoformat()
    assert len(f["gunluk"]) == BUGUN.day and f["gunluk"][-1]["tarih"] == BUGUN.isoformat()


# ---------------------------------------------------------------- Sessiz üyeler

@pytest.fixture()
def sessiz_kurulum(admin_engine, iki_kiraci):
    """A'da 4 üye: aktif süre paketleri + yenileme riski kaydı (p_hayatta_simdi verili)."""
    a, _ = iki_kiraci
    i = str(a.isletme_id)
    # (p_hayatta_simdi, p_yenileme, ucret, son ziyaret kaç gün önce)
    uyeler = [("0.10", "0.20", "6000.00", 40), ("0.30", "0.50", "6000.00", 20), ("0.45", "0.00", "2500.00", 60),
              ("0.80", "0.10", "10000.00", 2)]
    idler = []
    with admin_engine.begin() as con:
        for no, (ph, py, ucret, gecen) in enumerate(uyeler):
            m, p = uuid.uuid4(), uuid.uuid4()
            idler.append(m)
            con.execute(text("INSERT INTO musteriler (musteri_id, isletme_id, ad_soyad) VALUES (:m, :i, :a)"),
                        {"m": str(m), "i": i, "a": f"Sessiz {no}"})
            con.execute(text("INSERT INTO ziyaretler (isletme_id, musteri_id, ziyaret_zamani) "
                             "VALUES (:i, :m, now() - make_interval(days => :g))"), {"i": i, "m": str(m), "g": gecen})
            con.execute(text("INSERT INTO musteri_paketleri (paket_id, isletme_id, musteri_id, tur, ad, baslangic_tarihi, "
                             "bitis_tarihi, ucret) VALUES (:p, :i, :m, 'sure', 'Paket', :b, :e, :u)"),
                        {"p": str(p), "i": i, "m": str(m), "b": BUGUN - timedelta(days=70),
                         "e": BUGUN + timedelta(days=20), "u": ucret})
            con.execute(text("INSERT INTO yenileme_riskleri (isletme_id, musteri_id, paket_id, hesaplama_tarihi, "
                             "model_versiyonu, p_hayatta_simdi, p_yenileme, yenileme_tutari) "
                             "VALUES (:i, :m, :p, :t, 'test', :ph, :py, :u)"),
                        {"i": i, "m": str(m), "p": str(p), "t": BUGUN, "ph": ph, "py": py, "u": ucret})
    return a, idler


def test_sessiz_uyeler_esik_ve_siralama(istemci, sessiz_kurulum):
    a, idler = sessiz_kurulum
    g = istemci.get("/panel/sessiz-uyeler", params={"esik": 0.5}, headers=basliklar(a)).json()
    # riskteki_para: üye0 4800, üye1 3000, üye2 2500; üye3 eşik üstünde (0.80)
    assert g["uye_sayisi"] == 3
    assert [o["musteri_id"] for o in g["ogeler"]] == [str(idler[0]), str(idler[1]), str(idler[2])]
    assert D(g["toplam_riskteki_para"]) == D("10300.00")
    assert g["ogeler"][0]["son_ziyaretten_gecen_gun"] == 40 and g["ogeler"][0]["kalan_gun"] == 20
    assert istemci.get("/panel/sessiz-uyeler", params={"esik": 0.2}, headers=basliklar(a)).json()["uye_sayisi"] == 1
    assert istemci.get("/panel/sessiz-uyeler", headers=basliklar(a)).json()["uye_sayisi"] == 3   # varsayılan 0.5


def test_sessiz_uyeler_esitlikte_gecen_gun_azalan(istemci, sessiz_kurulum, admin_engine):
    a, idler = sessiz_kurulum
    with admin_engine.begin() as con:                    # üye1'in riskini üye0'a eşitle (4800)
        con.execute(text("UPDATE yenileme_riskleri SET p_yenileme = 0.20 WHERE musteri_id = :m"), {"m": str(idler[1])})
    g = istemci.get("/panel/sessiz-uyeler", params={"esik": 0.5}, headers=basliklar(a)).json()
    assert [o["musteri_id"] for o in g["ogeler"][:2]] == [str(idler[0]), str(idler[1])]  # 40 gün > 20 gün


@pytest.mark.parametrize("esik", [-0.1, 1.5, "abc"])
def test_sessiz_uyeler_esik_disi_422(istemci, iki_kiraci, esik):
    a, _ = iki_kiraci
    assert istemci.get("/panel/sessiz-uyeler", params={"esik": esik}, headers=basliklar(a)).status_code == 422


def test_sessiz_uyeler_baska_kiraci_gormez(istemci, sessiz_kurulum, iki_kiraci):
    _, b = iki_kiraci
    assert istemci.get("/panel/sessiz-uyeler", params={"esik": 1}, headers=basliklar(b)).json()["uye_sayisi"] == 0
