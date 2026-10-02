"""İçe aktarmanın veritabanı testleri (Adım 4b-1, K32–K41; panosu_test).

Gidiş-dönüş (K41): A'nın verisi sentetik.disa_aktar ile dışa aktarılıp B'ye içe aktarılır; sayılar birebir korunur,
aynı dosyanın ikinci yüklemesi 0 satır ekler.
"""

import json
import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from sentetik.disa_aktar import csv_uret, tutar_bicimle
from servisler import ice_aktar
from servisler.ice_aktarma import (
    TURLER,
    Hazirlik,
    PaketKaydi,
    UyeKaydi,
    dis_kaynak_olustur,
    dosya_oku,
    esleme_tahmin_et,
)
from servisler.ice_aktarma_yaz import EsikAsildi, hazirliklari_olustur, yaz
from servisler.yenileme_servisi import yenileme_hesapla

IST = ZoneInfo("Europe/Istanbul")


def _ice_aktar(oturum, kiraci, dosyalar: dict[str, bytes], kaynak: str = "eski", yenile: bool = False):
    """Komutun akışı (tahmini eşleştirme → hazırlık → yaz), dosya adları 'uyeler.csv' vb."""
    db = oturum(kiraci)
    dis_kaynak = dis_kaynak_olustur(kaynak)
    tablolar = {tur: dosya_oku(dosyalar[f"{tur}.csv"], f"{tur}.csv") for tur in TURLER if f"{tur}.csv" in dosyalar}
    eslemeler = {tur: esleme_tahmin_et(tur, t.basliklar).alanlar for tur, t in tablolar.items()}
    hazirliklar = hazirliklari_olustur(db, tablolar, eslemeler, dis_kaynak, anonim=False)
    for h in hazirliklar.values():
        assert not h.hatalar, [str(x) for x in h.hatalar]
    return yaz(db, list(hazirliklar.values()), dis_kaynak, yenile=yenile)


def _csv(*satirlar: str) -> bytes:
    return "\r\n".join(satirlar).encode("cp1254")


def _say(admin_engine, tablo: str, isletme_id, kosul: str = "true") -> int:
    with admin_engine.connect() as con:
        return con.scalar(text(f"SELECT count(*) FROM {tablo} WHERE isletme_id = :i AND {kosul}"),
                          {"i": str(isletme_id)})


# ---------------------------------------------------------------------------------------------
# Gidiş-dönüş (K41)
# ---------------------------------------------------------------------------------------------
@pytest.fixture()
def a_verisi(admin_engine, iki_kiraci):
    """A'da 32 üye (16'sı dis_kimlik'li), ~6 ay tam dakikalı girişler, süre ve giriş bazlı paketler, 3 paketli
    zincirler, bir dondurulmuş paket, paketli ama hiç gelmemiş bir üye. Temizliği iki_kiraci yapar."""
    a, _ = iki_kiraci
    i = str(a.isletme_id)
    bugun = datetime.now(IST).date()
    rng = np.random.default_rng(11)
    with admin_engine.begin() as con:
        uyeler = []
        for no in range(32):
            m = str(uuid.uuid4())
            dis = ("csv:eski", f"U{no:03d}", "csv") if no < 16 else (None, None, "manuel")
            con.execute(text(
                "INSERT INTO musteriler (musteri_id, isletme_id, ad_soyad, telefon_e164, eposta, kaynak, dis_kaynak, "
                "dis_kimlik) VALUES (:m, :i, :a, :t, :e, :k, :dk, :dkim)"),
                {"m": m, "i": i, "a": f"Üye Şahin {no}", "t": f"+90532{no:07d}" if no % 2 == 0 else None,
                 "e": f"uye{no}@ornek.com" if no % 3 == 0 else None, "k": dis[2], "dk": dis[0], "dkim": dis[1]})
            uyeler.append(m)
            if no >= 30 or no == 18:
                continue
            gun = bugun - timedelta(days=int(rng.integers(150, 183)))
            son = bugun - timedelta(days=1 if no % 5 else int(rng.integers(40, 90)))     # bir kısmı bırakmış
            while gun <= son:
                zaman = datetime(gun.year, gun.month, gun.day, int(rng.integers(8, 21)),
                                 int(rng.choice((0, 15, 30, 45))), tzinfo=IST)
                durum = "iptal" if rng.random() < 0.03 else "tamamlandi"
                con.execute(text("INSERT INTO ziyaretler (isletme_id, musteri_id, ziyaret_zamani, durum) "
                                 "VALUES (:i, :m, :z, :d)"), {"i": i, "m": m, "z": zaman, "d": durum})
                gun += timedelta(days=int(rng.integers(2, 12)))
        for no in range(20):
            onceki = None
            adet = 1 + no % 3
            giris = no % 4 == 1
            for j in range(adet):
                geri = adet - 1 - j
                if giris:
                    bas = bugun - timedelta(days=10 + no + 45 * geri)
                    bit = None if (geri == 0 and no in (1, 9, 17)) else bas + timedelta(days=60 if geri == 0 else 45)
                    hak, ucret = 10, Decimal("1250.50")
                else:
                    bit = bugun + timedelta(days=5 + no - 30 * geri)
                    bas = bit - timedelta(days=30)
                    hak, ucret = None, Decimal("2500.00") + no * Decimal("10.50")
                durum = ("donduruldu" if no == 19 else "aktif") if geri == 0 else "bitti"
                p = str(uuid.uuid4())
                dis = ("csv:eski", f"P{no:02d}-{j}") if no < 10 else (None, None)
                con.execute(text(
                    "INSERT INTO musteri_paketleri (paket_id, isletme_id, musteri_id, tur, ad, baslangic_tarihi, "
                    "bitis_tarihi, giris_hakki, ucret, durum, onceki_paket_id, dis_kaynak, dis_kimlik) "
                    "VALUES (:p, :i, :m, :t, :a, :b, :e, :h, :u, :d, :o, :dk, :dkim)"),
                    {"p": p, "i": i, "m": uyeler[no], "t": "giris" if giris else "sure",
                     "a": "10 Giriş" if giris else "Aylık", "b": bas, "e": bit, "h": hak, "u": ucret, "d": durum,
                     "o": onceki, "dk": dis[0], "dkim": dis[1]})
                onceki = p
    return a


_UYE_OZETI = """
SELECT COALESCE(m.dis_kimlik, m.musteri_id::text) AS anahtar, count(z.ziyaret_id) AS adet,
       min(z.ziyaret_zamani) AS ilk, max(z.ziyaret_zamani) AS son
FROM musteriler m LEFT JOIN ziyaretler z ON z.musteri_id = m.musteri_id AND z.durum = 'tamamlandi'
WHERE m.isletme_id = :i AND (CAST(:k AS text) IS NULL OR m.dis_kaynak = :k)
GROUP BY 1
"""
_PAKETLER = """
SELECT COALESCE(p.dis_kimlik, p.paket_id::text) AS anahtar, p.tur, p.durum, p.ucret, p.ad, p.baslangic_tarihi,
       p.bitis_tarihi, p.giris_hakki, COALESCE(o.dis_kimlik, o.paket_id::text) AS onceki
FROM musteri_paketleri p LEFT JOIN musteri_paketleri o ON o.paket_id = p.onceki_paket_id
WHERE p.isletme_id = :i
"""
_RISKLER = """
SELECT COALESCE(p.dis_kimlik, p.paket_id::text) AS anahtar, r.p_hayatta_simdi, r.p_yenileme
FROM yenileme_riskleri r JOIN musteri_paketleri p ON p.paket_id = r.paket_id
WHERE r.isletme_id = :i
"""


def _oku(admin_engine, sorgu: str, isletme_id, kaynak: str | None = None) -> dict:
    with admin_engine.connect() as con:
        return {s.anahtar: s for s in con.execute(text(sorgu), {"i": str(isletme_id), "k": kaynak})}


def _zincir_uzunluklari(paketler: dict) -> list[int]:
    def derinlik(anahtar):
        onceki = paketler[anahtar].onceki
        return 1 if onceki is None else 1 + derinlik(onceki)
    return sorted(derinlik(k) for k in paketler)


def _musteri_satirlari(admin_engine, isletme_id):
    with admin_engine.connect() as con:
        return con.execute(text(
            "SELECT musteri_id, ad_soyad, telefon_e164, eposta, dis_kaynak, dis_kimlik, guncelleme_zamani "
            "FROM musteriler WHERE isletme_id = :i ORDER BY musteri_id"), {"i": str(isletme_id)}).all()


def test_gidis_donus_sayilar_korunur_ve_ikinci_yukleme_eklemez(admin_engine, oturum, iki_kiraci, a_verisi):
    a, b = iki_kiraci
    a_once = _musteri_satirlari(admin_engine, a.isletme_id)
    dosyalar = csv_uret(oturum(a))

    sonuc = _ice_aktar(oturum, b, dosyalar, kaynak="eski", yenile=True)       # A'nın dis_kaynak'ı ile aynı
    assert sonuc.yenileme_uyarisi is None and sonuc.yenilenen > 0
    assert not sonuc.uyarilar

    yenileme_hesapla(oturum(a))
    uye_a, uye_b = _oku(admin_engine, _UYE_OZETI, a.isletme_id), _oku(admin_engine, _UYE_OZETI, b.isletme_id,
                                                                       "csv:eski")
    assert len(uye_a) == len(uye_b) == 33                                        # 32 + fixture'ın müşterisi
    assert sonuc.turler["uyeler"].eklenen == 33
    for anahtar, s in uye_a.items():                                             # üye başına giriş sayısı, ilk/son
        assert (uye_b[anahtar].adet, uye_b[anahtar].ilk, uye_b[anahtar].son) == (s.adet, s.ilk, s.son), anahtar
    tamamlanan = sum(s.adet for s in uye_a.values())
    assert sum(s.adet for s in uye_b.values()) == tamamlanan == sonuc.turler["girisler"].eklenen
    assert _say(admin_engine, "ziyaretler", a.isletme_id, "durum <> 'tamamlandi'") > 0   # iptaller aktarılmaz

    paket_a, paket_b = _oku(admin_engine, _PAKETLER, a.isletme_id), _oku(admin_engine, _PAKETLER, b.isletme_id)
    assert len(paket_a) == len(paket_b) == sonuc.turler["paketler"].eklenen
    assert sum(p.ucret for p in paket_b.values()) == sum(p.ucret for p in paket_a.values())
    assert isinstance(sum(p.ucret for p in paket_b.values()), Decimal)
    assert Counter((p.tur, p.durum) for p in paket_b.values()) == Counter((p.tur, p.durum) for p in paket_a.values())
    assert _zincir_uzunluklari(paket_b) == _zincir_uzunluklari(paket_a)
    assert max(_zincir_uzunluklari(paket_a)) == 3
    assert {k: tuple(p) for k, p in paket_b.items()} == {k: tuple(p) for k, p in paket_a.items()}

    risk_a, risk_b = _oku(admin_engine, _RISKLER, a.isletme_id), _oku(admin_engine, _RISKLER, b.isletme_id)
    assert set(risk_a) == set(risk_b) and risk_a
    hayatta_fark = max(abs(risk_a[k].p_hayatta_simdi - risk_b[k].p_hayatta_simdi) for k in risk_a)
    yenileme_fark = abs(sum(r.p_yenileme for r in risk_a.values()) - sum(r.p_yenileme for r in risk_b.values())) \
        / len(risk_a)
    print(f"\nGIDIS-DONUS: {len(risk_a)} aktif paket; p_hayatta_simdi en büyük |fark| = {hayatta_fark}; "
          f"p_yenileme ortalama |fark| = {yenileme_fark:.4f}")
    assert hayatta_fark <= Decimal("0.01")
    assert yenileme_fark <= Decimal("0.03")

    # RLS: B'ye içe aktarma A'yı değiştirmez; aynı (dis_kaynak, dis_kimlik) B'de ayrı satırdır
    assert _musteri_satirlari(admin_engine, a.isletme_id) == a_once
    with admin_engine.connect() as con:
        sahipler = con.execute(text("SELECT isletme_id, musteri_id FROM musteriler "
                                    "WHERE dis_kaynak = 'csv:eski' AND dis_kimlik = 'U000'")).all()
    assert {s.isletme_id for s in sahipler} == {a.isletme_id, b.isletme_id} and len(sahipler) == 2

    # Aynı dosyalar ikinci kez: hiçbir şey eklenmez, güncellenmez
    ikinci = _ice_aktar(oturum, b, dosyalar, kaynak="eski")
    assert {t: (s.eklenen, s.guncellenen) for t, s in ikinci.turler.items()} == {t: (0, 0) for t in TURLER}
    assert ikinci.turler["girisler"].atlanan == tamamlanan

    # Bir üyenin adı değişmiş dosya: 1 güncellenen, giriş eklenmez
    metin = dosyalar["uyeler.csv"].decode("cp1254").replace("Üye Şahin 7;", "Üye Şahin Yeni;")
    ucuncu = _ice_aktar(oturum, b, {"uyeler.csv": metin.encode("cp1254"), "girisler.csv": dosyalar["girisler.csv"]},
                        kaynak="eski")
    assert (ucuncu.turler["uyeler"].eklenen, ucuncu.turler["uyeler"].guncellenen) == (0, 1)
    assert (ucuncu.turler["girisler"].eklenen, ucuncu.turler["girisler"].atlanan) == (0, tamamlanan)
    assert _say(admin_engine, "musteriler", b.isletme_id, "ad_soyad = 'Üye Şahin Yeni'") == 1


def test_disa_aktarma_bicimi(oturum, iki_kiraci, a_verisi):
    a, _ = iki_kiraci
    dosyalar = csv_uret(oturum(a))
    paketler = dosyalar["paketler.csv"].decode("cp1254").splitlines()
    assert paketler[0] == "Üye No;Paket No;Paket Adı;Başlangıç Tarihi;Bitiş Tarihi;Seans Sayısı;Ücret;Durum"
    assert any(";1.250,50;" in s for s in paketler)
    girisler = dosyalar["girisler.csv"].decode("cp1254").splitlines()
    assert girisler[0] == "Üye No;Giriş Tarihi"
    assert all(len(s.split(";")[1]) == len("31.12.2025 14:30") for s in girisler[1:])
    assert tutar_bicimle(Decimal("1250")) == "1.250,00" and tutar_bicimle(Decimal("1234567.5")) == "1.234.567,50"


# ---------------------------------------------------------------------------------------------
# Paket zinciri ve telefon (proje sahibi kararları, 2026-10-02)
# ---------------------------------------------------------------------------------------------
_PAKET_BASLIK = "Üye No;Paket Adı;Başlangıç Tarihi;Bitiş Tarihi;Ücret"


def _zincir(admin_engine, isletme_id) -> dict:
    with admin_engine.connect() as con:
        return dict(con.execute(text(
            "SELECT p.baslangic_tarihi, o.baslangic_tarihi FROM musteri_paketleri p "
            "LEFT JOIN musteri_paketleri o ON o.paket_id = p.onceki_paket_id WHERE p.isletme_id = :i"),
            {"i": str(isletme_id)}).all())


def test_paket_zinciri_sonraki_yuklemede_kurulur_ve_korunur(admin_engine, oturum, iki_kiraci):
    _, b = iki_kiraci
    uyeler = _csv("Üye No;Ad Soyad", "1;Ali", "2;Veli")
    birinci = _csv(_PAKET_BASLIK, "1;Aylık;01.01.2026;01.02.2026;100", "1;Aylık;01.02.2026;01.03.2026;100",
                   "2;Aylık;01.01.2026;01.02.2026;100")
    ikinci = _csv(_PAKET_BASLIK, "1;Aylık;01.03.2026;01.04.2026;100", "1;Aylık;01.04.2026;01.05.2026;100")
    _ice_aktar(oturum, b, {"uyeler.csv": uyeler, "paketler.csv": birinci})
    _ice_aktar(oturum, b, {"paketler.csv": ikinci})
    beklenen = {date(2026, 1, 1): None, date(2026, 2, 1): date(2026, 1, 1), date(2026, 3, 1): date(2026, 2, 1),
                date(2026, 4, 1): date(2026, 3, 1)}
    zincir = _zincir(admin_engine, b.isletme_id)
    with admin_engine.connect() as con:                 # 2. üyenin paketi 1. üyenin zincirine girmez
        uye2_onceki = con.scalar(text(
            "SELECT p.onceki_paket_id FROM musteri_paketleri p JOIN musteriler m ON m.musteri_id = p.musteri_id "
            "WHERE p.isletme_id = :i AND m.dis_kimlik = '2'"), {"i": str(b.isletme_id)})
    assert uye2_onceki is None
    del zincir[date(2026, 1, 1)]                        # iki üyenin 01.01 paketi: ikisinin de öncülü yok
    assert zincir == {k: v for k, v in beklenen.items() if k != date(2026, 1, 1)}

    for dosya in (ikinci, birinci):                     # yeniden yükleme zinciri bozmaz (COALESCE)
        sonuc = _ice_aktar(oturum, b, {"paketler.csv": dosya})
        assert (sonuc.turler["paketler"].eklenen, sonuc.turler["paketler"].guncellenen) == (0, 0)
    son_zincir = _zincir(admin_engine, b.isletme_id)
    del son_zincir[date(2026, 1, 1)]
    assert son_zincir == {k: v for k, v in beklenen.items() if k != date(2026, 1, 1)}


def test_telefon_cakismasi_bos_birakilir_ayni_uye_uyari_uretmez(admin_engine, oturum, iki_kiraci):
    _, b = iki_kiraci
    with admin_engine.begin() as con:
        con.execute(text("INSERT INTO musteriler (isletme_id, ad_soyad, telefon_e164) VALUES (:i, 'Elle', :t)"),
                    {"i": str(b.isletme_id), "t": "+905551112233"})
    dosya = _csv("Üye No;Ad Soyad;Telefon", "1;Ali;0555 111 22 33", "2;Veli;0555 444 55 66")
    sonuc = _ice_aktar(oturum, b, {"uyeler.csv": dosya})
    assert sonuc.uyarilar["telefon_cakisma"] == 1
    with admin_engine.connect() as con:
        telefonlar = dict(con.execute(text("SELECT dis_kimlik, telefon_e164 FROM musteriler "
                                           "WHERE isletme_id = :i AND dis_kimlik IS NOT NULL"),
                                      {"i": str(b.isletme_id)}).all())
    assert telefonlar == {"1": None, "2": "+905554445566"}

    ikinci = _ice_aktar(oturum, b, {"uyeler.csv": dosya})              # yalnızca gerçek çakışma yine uyarır
    assert ikinci.uyarilar["telefon_cakisma"] == 1
    tek = _ice_aktar(oturum, b, {"uyeler.csv": _csv("Üye No;Ad Soyad;Telefon", "2;Veli;0555 444 55 66")})
    assert tek.uyarilar["telefon_cakisma"] == 0 and tek.turler["uyeler"].atlanan == 1


# ---------------------------------------------------------------------------------------------
# Eşik, geri alma, hassas alan
# ---------------------------------------------------------------------------------------------
def test_yuzde_on_esigi_asilinca_hicbir_sey_yazilmaz(admin_engine, oturum, iki_kiraci):
    _, b = iki_kiraci
    db = oturum(b)
    tablolar = {"uyeler": dosya_oku(_csv("Üye No;Ad Soyad", "1;Ali", "2;Veli"), "u.csv"),
                "girisler": dosya_oku(_csv("Üye No;Tarih", "1;01.09.2026", "1;02.09.2026", "2;03.09.2026",
                                           "2;99.09.2026", "1;04.09.2026"), "g.csv")}
    eslemeler = {t: esleme_tahmin_et(t, x.basliklar).alanlar for t, x in tablolar.items()}
    hazirliklar = hazirliklari_olustur(db, tablolar, eslemeler, "csv:x", anonim=False)
    assert hazirliklar["girisler"].esik_asildi                                   # 1/5 = %20
    with pytest.raises(EsikAsildi):
        yaz(db, list(hazirliklar.values()), "csv:x")
    assert _say(admin_engine, "musteriler", b.isletme_id, "dis_kaynak IS NOT NULL") == 0
    assert _say(admin_engine, "ziyaretler", b.isletme_id) == 0


def test_yazma_hatasinda_tamami_geri_alinir(admin_engine, oturum, iki_kiraci):
    _, b = iki_kiraci
    uyeler = Hazirlik("uyeler", "csv:x", 1, ("uye_kimlik", "ad_soyad"),
                      kayitlar=[UyeKaydi(2, "1", "Ali", None, None)])
    # Çekirdeği atlayan sahte kayıt: süre bazlı pakette bitiş yok → DB CHECK ihlali
    paketler = Hazirlik("paketler", "csv:x", 1, ("uye_kimlik", "paket_adi", "baslangic", "ucret"), kayitlar=[
        PaketKaydi(2, "P1", "1", "sure", "Aylık", date(2026, 9, 1), None, None, Decimal("100"), "aktif", None)])
    with pytest.raises(IntegrityError):
        yaz(oturum(b), [uyeler, paketler], "csv:x")
    assert _say(admin_engine, "musteriler", b.isletme_id, "dis_kaynak IS NOT NULL") == 0
    assert _say(admin_engine, "musteri_paketleri", b.isletme_id) == 0


GIZLI_TC = "98765432109"
GIZLI_KAN = "ABRhGizli"


def _hassas_yok(admin_engine, isletme_id) -> None:
    for tablo in ("musteriler", "musteri_paketleri", "ziyaretler", "denetim_kayitlari"):
        for gizli in (GIZLI_TC, GIZLI_KAN):
            assert _say(admin_engine, tablo, isletme_id, f"{tablo}::text LIKE '%{gizli}%'") == 0, (tablo, gizli)


# ---------------------------------------------------------------------------------------------
# Komut
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("ad", ["panosu", "panosu_canli", ""])
def test_komut_izinsiz_veritabaninda_baglanmadan_cikar(monkeypatch, tmp_path, ad):
    def _yasak(*_a, **_k):
        raise AssertionError("bağlantı kurulmamalıydı")

    monkeypatch.setattr(ice_aktar, "create_engine", _yasak)
    dosya = tmp_path / "u.csv"
    dosya.write_bytes(_csv("Üye No;Ad Soyad", "1;Ali"))
    with pytest.raises(SystemExit):
        ice_aktar.main(["--veritabani", ad, "--isletme", str(uuid.uuid4()), "--kaynak", "x", "--uyeler", str(dosya)])


def _komut(b, tmp_path, *ek: str, **dosyalar: bytes) -> list[str]:
    argv = ["--veritabani", "panosu_test", "--isletme", str(b.isletme_id), "--kaynak", "deneme", *ek]
    for tur, icerik in dosyalar.items():
        yol = tmp_path / f"{tur}.csv"
        yol.write_bytes(icerik)
        argv += [f"--{tur}", str(yol)]
    return argv


def test_komut_onizleme_yazmaz_onayla_yazar_kisisel_veri_basmaz(admin_engine, iki_kiraci, tmp_path, monkeypatch,
                                                                capsys):
    _, b = iki_kiraci
    monkeypatch.setattr(ice_aktar, "ESLEME_CIKTI", tmp_path / "esleme.json")
    uyeler = _csv("Üye No;Adı Soyadı;Telefon;E-posta;TC Kimlik No;Kan Grubu",
                  f"1;Zeynep Gizlioğlu;0555 987 65 43;gizli@ornek.com;{GIZLI_TC};{GIZLI_KAN}",
                  f"2;Mehmet Saklı;abc;yok;{GIZLI_TC};{GIZLI_KAN}")
    girisler = _csv("Üye No;Giriş Tarihi;Tutar", "1;01.09.2026 10:00;0", "2;99.99.2026;0")
    paketler = _csv(_PAKET_BASLIK, "1;Aylık;01.09.2026;01.10.2026;1.250,00")

    ice_aktar.main(_komut(b, tmp_path, uyeler=uyeler, paketler=paketler, girisler=girisler))
    cikti = capsys.readouterr().out
    assert _say(admin_engine, "musteriler", b.isletme_id, "dis_kaynak IS NOT NULL") == 0     # önizleme yazmaz
    assert "uye_kimlik   ← Üye No" in cikti and "Hassas (okunmadı) başlıklar: TC Kimlik No, Kan Grubu" in cikti
    assert "satır 3, tarih: geçersiz ay" in cikti and "Paket geliri ve giriş tutarı birlikte" in cikti
    oneri = json.loads((tmp_path / "esleme.json").read_text(encoding="utf-8"))
    assert oneri["uyeler"]["ad_soyad"] == "Adı Soyadı" and oneri["girisler"]["giris_kimlik"] is None

    with pytest.raises(SystemExit) as cikis:                                     # girişlerde 1/2 hatalı → red
        ice_aktar.main(_komut(b, tmp_path, "--onayla", uyeler=uyeler, paketler=paketler, girisler=girisler))
    assert cikis.value.code == 1
    assert _say(admin_engine, "musteriler", b.isletme_id, "dis_kaynak IS NOT NULL") == 0

    girisler = _csv("Üye No;Giriş Tarihi", "1;01.09.2026 10:00", "2;02.09.2026")
    ice_aktar.main(_komut(b, tmp_path, "--onayla", uyeler=uyeler, paketler=paketler, girisler=girisler))
    cikti += capsys.readouterr().out
    assert "uyeler             2            0         0" in cikti
    assert _say(admin_engine, "musteriler", b.isletme_id, "dis_kaynak = 'csv:deneme'") == 2
    assert _say(admin_engine, "ziyaretler", b.isletme_id) == 2
    for gizli in ("Zeynep", "Gizlioğlu", "Mehmet", "Saklı", "987 65 43", "5559876543", "gizli@ornek.com", GIZLI_TC,
                  GIZLI_KAN):
        assert gizli not in cikti
    _hassas_yok(admin_engine, b.isletme_id)


def test_komut_hassas_alan_elle_eslenirse_reddeder(admin_engine, iki_kiraci, tmp_path, monkeypatch, capsys):
    _, b = iki_kiraci
    monkeypatch.setattr(ice_aktar, "ESLEME_CIKTI", tmp_path / "esleme.json")
    esleme = tmp_path / "elle.json"
    esleme.write_text(json.dumps({"uyeler": {"uye_kimlik": "Üye No", "ad_soyad": "TC Kimlik No"}}), encoding="utf-8")
    uyeler = _csv("Üye No;Ad Soyad;TC Kimlik No", f"1;Ali;{GIZLI_TC}")
    with pytest.raises(SystemExit) as cikis:
        ice_aktar.main(_komut(b, tmp_path, "--onayla", "--esleme", str(esleme), uyeler=uyeler))
    assert cikis.value.code == 2
    cikti = capsys.readouterr().out
    assert "ad_soyad: hassas alan" in cikti and GIZLI_TC not in cikti
    assert _say(admin_engine, "musteriler", b.isletme_id, "dis_kaynak IS NOT NULL") == 0
    _hassas_yok(admin_engine, b.isletme_id)
