"""Pilot validation and scoring without a database (pilot step, K64-K71, `docs/adim-pilot-tasarim.md`).

All tests except the last one use no database. The last one checks that `pilot.skorla` gives exactly the values
that `yenileme_servisi.yenileme_hesapla` writes for the same imported data (panosu_test).
"""

import csv
import io
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from sqlalchemy import text

from backtest.senaryolar import GOZLEM_GUN, S6_GIRIS_SON_KULLANMA, S6_PAKETLER, uret_s6
from servisler import ice_aktarma as ia
from servisler import pilot, pilot_dogrula

IST = ZoneInfo("Europe/Istanbul")
KOK = Path(__file__).resolve().parent.parent
PAKET_BASLIK = ["Üye No", "Paket No", "Paket Adı", "Başlangıç Tarihi", "Bitiş Tarihi", "Seans Sayısı", "Ücret", "Durum"]


def _s6_dosyalari(uye: int, tohum: int, son_gun: date, kaydir: int = 0) -> dict[str, list[list[str]]]:
    """Backtest S6 synthetic studio in the firm file format; day GOZLEM_GUN falls on `son_gun` (minus `kaydir`)."""
    v = uret_s6(np.random.default_rng([6, tohum]), uye)
    baz = datetime.combine(son_gun, datetime.min.time(), tzinfo=IST) - timedelta(days=GOZLEM_GUN + kaydir)
    gun = lambda t: (baz + timedelta(days=float(t))).date().strftime("%d.%m.%Y")
    paketler = []
    for j, pk in enumerate(v.paketler):
        ad, tur, _, sure, hak, fiyat = S6_PAKETLER[pk.tur_no]
        bitis = pk.baslangic + (sure if tur == "sure" else S6_GIRIS_SON_KULLANMA)
        paketler.append([f"U{pk.uye:05d}", f"K{j:06d}", ad, gun(pk.baslangic), gun(bitis), str(hak or ""),
                         f"{fiyat},00", ""])
    girisler = [[f"U{i:05d}", (baz + timedelta(days=float(t))).strftime("%d.%m.%Y %H:%M")]
                for i, z in enumerate(v.zamanlar) for t in z]
    return {"paketler": paketler, "girisler": girisler}


def _csv_bayt(baslik: list[str], satirlar: list[list[str]]) -> bytes:
    tampon = io.StringIO()
    w = csv.writer(tampon, delimiter=";", lineterminator="\r\n")
    w.writerow(baslik)
    w.writerows(satirlar)
    return tampon.getvalue().encode("utf-8-sig")


def _kayitlar(dosyalar: dict[str, list[list[str]]]):
    """Firm files -> (check-ins per member, package records), the same path as the command."""
    g_tablo = ia.dosya_oku(_csv_bayt(["Üye No", "Giriş Tarihi"], dosyalar["girisler"]), "girisler.csv")
    g = ia.satirlari_hazirla("girisler", g_tablo, ia.esleme_tahmin_et("girisler", g_tablo.basliklar).alanlar,
                             "Europe/Istanbul", date.today(), True, "csv:test")
    ziyaretler = pilot.ziyaret_gunleri(g.kayitlar, IST)
    p_tablo = ia.dosya_oku(_csv_bayt(PAKET_BASLIK, dosyalar["paketler"]), "paketler.csv")
    p = ia.satirlari_hazirla("paketler", p_tablo, ia.esleme_tahmin_et("paketler", p_tablo.basliklar).alanlar,
                             "Europe/Istanbul", pilot.veri_gunu(ziyaretler, IST), True, "csv:test")
    assert not g.hatalar and not p.hatalar
    return ziyaretler, p.kayitlar


@pytest.fixture(scope="module")
def s6():
    return _s6_dosyalari(250, 0, date(2026, 3, 31))


def test_s6_sentetik_studyoda_model_kuraldan_iyi(s6):
    d = pilot.dogrula(*_kayitlar(s6), IST)
    L = d.veri_gunu
    assert d.kesimler == [L - timedelta(days=g) for g in (90, 180, 270, 360)]
    assert {s.gun for s in d.skorlar} == set(d.kesimler)
    assert len(d.skorlar) >= 100 and not d.uyarilar
    assert d.auc > 0.75 and d.auc > d.kural_auc
    assert d.auc_alt < d.auc < d.auc_ust
    assert d.ilk_sira_n == 10 and d.ilk_sira_birakan >= 7
    assert [s.p_yenileme for s in d.skorlar] == sorted(s.p_yenileme for s in d.skorlar)
    assert len(d.dilimler) == 5 and sum(k.n for k in d.dilimler) == len(d.skorlar)
    assert d.gercek_kayip == sum((s.paket.ucret for s, r in zip(d.skorlar, d.yeniledi) if not r), Decimal(0))


def test_kesimler_gecmise_gore_secilir():
    L = date(2026, 6, 30)
    assert pilot.kesimleri_sec(L, L - timedelta(days=100)) == [L - timedelta(days=90)]       # always the newest
    assert pilot.kesimleri_sec(L, L - timedelta(days=359)) == [L - timedelta(days=90)]       # C1 has 179 days
    assert pilot.kesimleri_sec(L, L - timedelta(days=360)) == [L - timedelta(days=90), L - timedelta(days=180)]
    assert len(pilot.kesimleri_sec(L, L - timedelta(days=2000))) == pilot.AZAMI_KESIM


def test_bootstrap_ve_sonuc_belirlenimci(s6):
    a, b = pilot.dogrula(*_kayitlar(s6), IST), pilot.dogrula(*_kayitlar(s6), IST)
    assert (a.auc, a.auc_alt, a.auc_ust, a.tahmini_kayip) == (b.auc, b.auc_alt, b.auc_ust, b.tahmini_kayip)


def test_kesim_sonrasi_girisler_kesimdeki_skoru_degistirmez(s6):
    """No leakage: dropping every check-in strictly between the cut-off and the data day leaves scores at C equal."""
    ziyaretler, paketler = _kayitlar(s6)
    d = pilot.dogrula(ziyaretler, paketler, IST)
    L, C = d.veri_gunu, d.kesimler[0]
    kirpik = {u: [z for z in zs if not (C < z.astimezone(IST).date() < L)] for u, zs in ziyaretler.items()}
    kirpik = {u: zs for u, zs in kirpik.items() if zs}
    e = pilot.dogrula(kirpik, paketler, IST)
    assert e.veri_gunu == L
    onceki = {(s.gun, s.paket.dis_kimlik): s.p_yenileme for s in d.skorlar}
    assert {(s.gun, s.paket.dis_kimlik): s.p_yenileme for s in e.skorlar} == onceki


def test_tum_tarihleri_kaydirmak_sonucu_degistirmez():
    """Time-shift invariance: a firm may move every date back by the same number of days (K69)."""
    a = pilot.dogrula(*_kayitlar(_s6_dosyalari(250, 1, date(2026, 3, 31))), IST)
    b = pilot.dogrula(*_kayitlar(_s6_dosyalari(250, 1, date(2026, 3, 31), kaydir=100)), IST)
    assert b.veri_gunu == a.veri_gunu - timedelta(days=100)
    assert [(s.paket.dis_kimlik, s.p_yenileme) for s in a.skorlar] == \
           [(s.paket.dis_kimlik, s.p_yenileme) for s in b.skorlar]
    assert (a.auc, a.yeniledi, a.tahmini_kayip) == (b.auc, b.yeniledi, b.tahmini_kayip)


# ---------------------------------------------------------------------------------------------
# Selection and outcome rules on a hand-made studio
# ---------------------------------------------------------------------------------------------
L = date(2026, 6, 30)
C = L - timedelta(days=90)                      # 2026-04-01


def _pk(uye: str, no: str, bas: date, bit: date | None, durum: str = "aktif", hak: int | None = None,
        satir: int = 0) -> ia.PaketKaydi:
    return ia.PaketKaydi(satir, no, uye, "giris" if hak else "sure", "Paket", bas, bit, hak, Decimal("1000.00"),
                         durum, None)


def _elle_veri():
    ziyaretler = {}
    for i in range(12):                         # regular members so the model has something to fit
        bas = datetime(2025, 7, 1, 18, tzinfo=IST) + timedelta(days=i)
        ziyaretler[f"D{i}"] = [bas + timedelta(days=4 * k) for k in range(80)]
    for u in "ABCDEFGH":
        ziyaretler[u] = [datetime(2026, 1, 5, 18, tzinfo=IST) + timedelta(days=5 * k) for k in range(10)]
    ziyaretler["D0"].append(datetime(2026, 6, 30, 18, tzinfo=IST))     # data day L
    ziyaretler = {u: sorted(z) for u, z in ziyaretler.items()}
    paketler = [
        _pk("A", "A1", C - timedelta(days=20), C + timedelta(days=10)),
        _pk("A", "A2", C + timedelta(days=40), C + timedelta(days=70)),                  # end + 30: renewed
        _pk("B", "B1", C - timedelta(days=10), C + timedelta(days=20)),
        _pk("A", "A3", L - timedelta(days=10), L + timedelta(days=20)),                  # active on L
        _pk("B", "B2", C + timedelta(days=51), C + timedelta(days=81)),                  # end + 31: not renewed
        _pk("B", "B3", L - timedelta(days=10), L + timedelta(days=20), durum="bitti"),   # file status wins
        _pk("C", "C1", C - timedelta(days=10), C + timedelta(days=61)),                  # ends after C + 60
        _pk("D", "D1", C - timedelta(days=30), C),                                       # ended on C
        _pk("E", "E1", C - timedelta(days=10), C + timedelta(days=20), durum="iptal"),   # cancelled
        _pk("F", "F1", C - timedelta(days=40), C + timedelta(days=5)),                   # not the latest at C
        _pk("F", "F2", C - timedelta(days=2), C + timedelta(days=88)),
        _pk("G", "G1", C - timedelta(days=5), None, hak=8),                              # entries, no end date
        _pk("H", "H1", C - timedelta(days=5), C + timedelta(days=30), hak=8),
        _pk("H", "H2", L - timedelta(days=5), L + timedelta(days=25), durum="donduruldu"),
    ]
    return ziyaretler, paketler


def test_secim_ve_yenileme_kurallari():
    d = pilot.dogrula(*_elle_veri(), IST)
    assert (d.veri_gunu, d.kesimler) == (L, [C, C - timedelta(days=90)])     # 2025-07-01 + 184 days >= 180
    sonuc = {s.paket.dis_kimlik: r for s, r in zip(d.skorlar, d.yeniledi)}
    assert sonuc == {"A1": True, "B1": False, "H1": False}
    assert d.dislanan_bitissiz == 1
    h1 = next(s for s in d.skorlar if s.paket.dis_kimlik == "H1")
    assert h1.kalan_giris == 8 - 0 and h1.kalan_gun is None   # H's check-ins all happened before the package


def test_guncel_liste_aktif_paketler():
    g = pilot.guncel(*_elle_veri(), IST)
    assert g.gun == L
    assert {s.paket.dis_kimlik for s in g.skorlar} == {"A3", "G1"}      # C1/F2 ended, B3 "bitti", H2 frozen
    assert g.donduruldu == 1
    assert [s.riskteki_para for s in g.skorlar] == sorted((s.riskteki_para for s in g.skorlar), reverse=True)


# ---------------------------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------------------------
def _komut(tmp_path, s6, *ek, paket_satirlari=None, paket_basligi=None, giris_dosyalari=None) -> Path:
    (tmp_path / "paketler.csv").write_bytes(_csv_bayt(paket_basligi or PAKET_BASLIK,
                                                      paket_satirlari or s6["paketler"]))
    if giris_dosyalari is None:
        (tmp_path / "girisler.csv").write_bytes(_csv_bayt(["Üye No", "Giriş Tarihi"], s6["girisler"]))
        giris_dosyalari = ["girisler.csv"]
    cikti = tmp_path / "cikti"
    pilot_dogrula.main(["--kaynak", "deneme", "--paketler", str(tmp_path / "paketler.csv"),
                        "--girisler", *[str(tmp_path / g) for g in giris_dosyalari], "--cikti", str(cikti), *ek])
    return cikti


def test_komut_ciktilari_ve_kisisel_sutun_okunmaz(tmp_path, s6, capsys):
    baslik = PAKET_BASLIK + ["Ad Soyad", "TC Kimlik No", "Telefon"]
    satirlar = [r + ["Zeynep Örnekoğlu", "12345678901", "0532 111 22 33"] for r in s6["paketler"]]
    cikti = _komut(tmp_path, s6, "--ad", "Deneme Stüdyo", paket_satirlari=satirlar, paket_basligi=baslik)
    assert sorted(p.name for p in cikti.iterdir()) == ["dogrulama.csv", "esleme.json", "pilot-raporu.html",
                                                        "skorlar.csv"]
    metinler = [p.read_text(encoding="utf-8-sig") for p in cikti.iterdir()] + [capsys.readouterr().out]
    for deger in ("Zeynep", "12345678901", "0532"):
        assert not any(deger in m for m in metinler)
    assert (cikti / "skorlar.csv").read_text(encoding="utf-8-sig").splitlines()[0] == (
        "Üye No;Paket No;Paket Adı;Bitiş Tarihi;Kalan Gün;Kalan Giriş;Aktif Olasılığı;Yenileme Olasılığı;"
        "Riskteki Para;Neden")
    html = (cikti / "pilot-raporu.html").read_text(encoding="utf-8")
    assert "Deneme Stüdyo · pilot raporu" in html and "Ayırt etme gücü" in html


def test_komut_bolunmus_giris_dosyalari_ayni_sonuc(tmp_path, s6):
    (tmp_path / "tek").mkdir()
    tek = _komut(tmp_path / "tek", s6)
    yil = lambda r: r[1][6:10]
    (tmp_path / "iki").mkdir()
    for y in sorted({yil(r) for r in s6["girisler"]}):
        (tmp_path / "iki" / f"girisler-{y}.csv").write_bytes(
            _csv_bayt(["Üye No", "Giriş Tarihi"], [r for r in s6["girisler"] if yil(r) == y]))
    iki = _komut(tmp_path / "iki", s6, giris_dosyalari=sorted(p.name for p in (tmp_path / "iki").glob("girisler-*")))
    for ad in ("dogrulama.csv", "skorlar.csv"):
        assert (tek / ad).read_bytes() == (iki / ad).read_bytes()


def test_komut_yuzde_on_hatali_satirda_durur(tmp_path, s6):
    girisler = [r if i % 8 else [r[0], "31.13.2025"] for i, r in enumerate(s6["girisler"])]   # 12.5% invalid
    (tmp_path / "girisler.csv").write_bytes(_csv_bayt(["Üye No", "Giriş Tarihi"], girisler))
    with pytest.raises(SystemExit) as hata:
        _komut(tmp_path, s6, giris_dosyalari=["girisler.csv"])
    assert hata.value.code == 1
    assert not (tmp_path / "cikti").exists()


def test_komut_veritabani_ve_ayar_dosyasi_gerektirmez():
    """The firm runs it without .env and PostgreSQL: importing the command must not import database/config."""
    ortam = {k: v for k, v in os.environ.items() if not k.startswith("PANOSU_")}
    kod = ("import sys, servisler.pilot_dogrula; "
           "assert not {'database', 'config', 'models', 'sqlalchemy'} & set(sys.modules), sorted(sys.modules)")
    subprocess.run([sys.executable, "-c", kod], cwd=KOK, env=ortam, check=True)


# ---------------------------------------------------------------------------------------------
# Equivalence with the production renewal computation (panosu_test)
# ---------------------------------------------------------------------------------------------
def test_skorla_yenileme_hesapla_ile_ayni(admin_engine, oturum, iki_kiraci):
    from servisler.ice_aktarma_yaz import hazirliklari_olustur, yaz
    from servisler.yenileme_servisi import yenileme_hesapla

    dosyalar = _s6_dosyalari(80, 3, date.today() - timedelta(days=1))
    uyeler = sorted({r[0] for r in dosyalar["paketler"]} | {r[0] for r in dosyalar["girisler"]})
    bayt = {"uyeler": _csv_bayt(["Üye No"], [[u] for u in uyeler]),
            "paketler": _csv_bayt(PAKET_BASLIK, dosyalar["paketler"]),
            "girisler": _csv_bayt(["Üye No", "Giriş Tarihi"], dosyalar["girisler"])}
    a = iki_kiraci[0]
    db = oturum(a)
    tablolar = {tur: ia.dosya_oku(b, f"{tur}.csv") for tur, b in bayt.items()}
    eslemeler = {tur: ia.esleme_tahmin_et(tur, t.basliklar).alanlar for tur, t in tablolar.items()}
    hazirliklar = hazirliklari_olustur(db, tablolar, eslemeler, ia.dis_kaynak_olustur("pilot"), anonim=True)
    yaz(db, list(hazirliklar.values()), ia.dis_kaynak_olustur("pilot"), yenile=False)

    ziyaretler = pilot.ziyaret_gunleri(hazirliklar["girisler"].kayitlar, IST)
    L = pilot.veri_gunu(ziyaretler, IST)
    assert yenileme_hesapla(oturum(a), L) > 0
    with admin_engine.connect() as con:
        db_degerleri = {dis: (ph, py) for dis, ph, py in con.execute(text(
            "SELECT p.dis_kimlik, r.p_hayatta_simdi, r.p_yenileme FROM yenileme_riskleri r "
            "JOIN musteri_paketleri p USING (isletme_id, paket_id) "
            "WHERE r.isletme_id = :i AND r.hesaplama_tarihi = :g"), {"i": str(a.isletme_id), "g": L})}
    paketler = [pk for pk in hazirliklar["paketler"].kayitlar if pk.dis_kimlik in db_degerleri]
    assert len(paketler) == len(db_degerleri) >= 10
    pilot_degerleri = {s.paket.dis_kimlik: (s.p_hayatta_simdi, s.p_yenileme)
                       for s in pilot.skorla(ziyaretler, paketler, L, IST)}
    assert pilot_degerleri == db_degerleri
