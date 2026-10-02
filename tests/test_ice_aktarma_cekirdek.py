"""İçe aktarma çekirdeği birim testleri (Adım 4b-1, K29–K39). Veritabanı yok."""

import io
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from servisler.ice_aktarma import (
    AZAMI_BAYT,
    CIFT_SAYIM_UYARISI,
    DegerHatasi,
    DosyaHatasi,
    EslemeHatasi,
    GirisKaydi,
    PaketKaydi,
    Tablo,
    baslik_normallestir,
    ciro_cift_sayim_uyarisi,
    dis_kaynak_olustur,
    dosya_oku,
    durum_coz,
    esleme_dogrula,
    esleme_tahmin_et,
    para_coz,
    satirlari_hazirla,
    tarih_coz,
    zaman_coz,
)

IST = ZoneInfo("Europe/Istanbul")
SIMDI = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)          # İstanbul 12:00
BUGUN = date(2026, 10, 2)
KAYNAK = "csv:deneme"


def _csv(satirlar: list[str], ayirici: str = ";", kodlama: str = "utf-8-sig") -> bytes:
    return "\r\n".join(ayirici.join(s) if isinstance(s, (list, tuple)) else s for s in satirlar).encode(kodlama)


def _hazirla(tur, tablo, esleme=None, anonim=False, bilinen=None):
    esleme = esleme if esleme is not None else esleme_tahmin_et(tur, tablo.basliklar).alanlar
    return satirlari_hazirla(tur, tablo, esleme, "Europe/Istanbul", BUGUN, anonim, KAYNAK, simdi=SIMDI,
                             bilinen_uyeler=bilinen)


# ---------------------------------------------------------------------------------------------
# Okuma
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kodlama", ["utf-8-sig", "cp1254"])
def test_utf8_ve_cp1254_ayni_eslestirmeye_cevrilir(kodlama):
    icerik = _csv(["Üye No;Üye Adı Soyadı;Paket Adı;Başlangıç Tarihi;Ücret", "1;Ayşe Işık;Aylık;01.09.2026;1.250,00"],
                  kodlama=kodlama)
    tablo = dosya_oku(icerik, "uyeler.csv")
    assert tablo.kodlama == kodlama
    assert tablo.basliklar[1] == "Üye Adı Soyadı"
    assert esleme_tahmin_et("uyeler", tablo.basliklar).alanlar == {
        "uye_kimlik": "Üye No", "ad_soyad": "Üye Adı Soyadı"}
    assert esleme_tahmin_et("paketler", tablo.basliklar).alanlar == {
        "uye_kimlik": "Üye No", "paket_adi": "Paket Adı", "baslangic": "Başlangıç Tarihi", "ucret": "Ücret"}


@pytest.mark.parametrize("ayirici", [";", ",", "\t"])
def test_ayirici_bulunur(ayirici):
    icerik = _csv([["Üye No", "Ad Soyad", "Telefon"], ["1", "Ali Veli", "0532 123 45 67"],
                   ["2", "Can Su", "0533 222 33 44"]], ayirici=ayirici)
    tablo = dosya_oku(icerik, "u.csv")
    assert tablo.ayirici == ayirici
    assert tablo.satirlar[1][1] == ("2", "Can Su", "0533 222 33 44")


def test_bos_satirlar_atlanir_satir_numaralari_dosyadaki_gibi():
    tablo = dosya_oku(_csv(["", "Üye No;Ad Soyad", ";", "1;Ali", "", "2;Can"]), "u.csv")
    assert tablo.basliklar == ["Üye No", "Ad Soyad"]
    assert [n for n, _ in tablo.satirlar] == [4, 6]


def test_xlsx_tarih_hucresi_ve_sayilar():
    from openpyxl import Workbook

    kitap = Workbook()
    sayfa = kitap.active
    sayfa.append(["Üye No", "Giriş Tarihi", "Tutar"])
    sayfa.append([1001, datetime(2026, 9, 15, 18, 30), 1250.5])
    sayfa.append([1002, datetime(2026, 9, 16), 990])
    tampon = io.BytesIO()
    kitap.save(tampon)

    tablo = dosya_oku(tampon.getvalue(), "girisler.xlsx")
    assert tablo.bicim == "xlsx"
    assert tablo.satirlar[0] == (2, (1001, datetime(2026, 9, 15, 18, 30), Decimal("1250.5")))
    h = _hazirla("girisler", tablo)
    assert not h.hatalar
    k1, k2 = h.kayitlar
    assert k1.uye_kimlik == "1001" and k1.ziyaret_zamani == datetime(2026, 9, 15, 15, 30, tzinfo=UTC)
    assert k2.ziyaret_zamani == datetime(2026, 9, 16, 9, 0, tzinfo=UTC)       # saatsiz → yerel 12:00
    assert k1.toplam_tutar == Decimal("1250.5") and type(k1.toplam_tutar) is Decimal


def test_boyut_siniri_okumadan_reddedilir():
    with pytest.raises(DosyaHatasi, match="MB"):
        dosya_oku(b"x" * (AZAMI_BAYT + 1), "buyuk.csv")


def test_satir_siniri(monkeypatch):
    monkeypatch.setattr("servisler.ice_aktarma.AZAMI_SATIR", 3)
    dosya_oku(_csv(["Üye No", "1", "2", "3"]), "u.csv")
    with pytest.raises(DosyaHatasi, match="veri satırı sınırını aşıyor"):
        dosya_oku(_csv(["Üye No", "1", "2", "3", "4"]), "u.csv")


def test_desteklenmeyen_uzanti():
    with pytest.raises(DosyaHatasi):
        dosya_oku(b"a;b", "eski.xls")


# ---------------------------------------------------------------------------------------------
# Eşleştirme
# ---------------------------------------------------------------------------------------------
def test_baslik_normallestirme():
    assert baslik_normallestir("  ÜYE ADI-SOYADI  ") == "uye adi soyadi"
    assert baslik_normallestir("İsim") == "isim"
    assert baslik_normallestir("IŞIK") == "isik"
    assert baslik_normallestir("E-Posta") == "e posta"
    assert baslik_normallestir("Check-in (Tarih)") == "check in tarih"


def test_es_anlamli_eslestirme_uzun_es_anlamli_kazanir():
    e = esleme_tahmin_et("paketler", ["Üye No", "Paket No", "Paket Adı", "Satış Tarihi", "Son Kullanma Tarihi",
                                      "Seans Sayısı", "Ödenen Tutar", "Durum", "Not"])
    assert e.alanlar == {"uye_kimlik": "Üye No", "paket_kimlik": "Paket No", "paket_adi": "Paket Adı",
                         "baslangic": "Satış Tarihi", "bitis": "Son Kullanma Tarihi", "giris_hakki": "Seans Sayısı",
                         "ucret": "Ödenen Tutar", "durum": "Durum"}
    assert e.eslesmeyenler == ["Not"]


def test_ayni_alana_iki_baslik_uzun_olan_kazanir():
    e = esleme_tahmin_et("uyeler", ["Müşteri No", "Ad Soyad", "Telefon", "Cep Telefonu"])
    assert e.alanlar["telefon"] == "Cep Telefonu"
    assert "Telefon" in e.eslesmeyenler


def test_kisa_es_anlamli_yalnizca_basta_eslesir():
    e = esleme_tahmin_et("uyeler", ["Üye No", "Ad", "Soyad", "Paket Adı", "Eğitmen Adı", "Cep Tel"])
    assert e.alanlar == {"uye_kimlik": "Üye No", "ad": "Ad", "soyad": "Soyad", "telefon": "Cep Tel"}
    assert {"Paket Adı", "Eğitmen Adı"} <= set(e.eslesmeyenler)


def test_tam_eslesme_kismi_eslesmeyi_yener():
    e = esleme_tahmin_et("uyeler", ["Üye No", "Veli Adı Soyadı", "Adı Soyadı"])
    assert e.alanlar["ad_soyad"] == "Adı Soyadı" and "Veli Adı Soyadı" in e.eslesmeyenler


def test_bilesik_turkce_baslik_uzun_es_anlamliyla():
    e = esleme_tahmin_et("paketler", ["Üye No", "Üyelik Tipi", "Üyelik Başlangıç Tarihi", "Paket Bitiş Tarihi",
                                      "Ücret (TL)"])
    assert e.alanlar == {"uye_kimlik": "Üye No", "paket_adi": "Üyelik Tipi", "baslangic": "Üyelik Başlangıç Tarihi",
                         "bitis": "Paket Bitiş Tarihi", "ucret": "Ücret (TL)"}


@pytest.mark.parametrize("baslik", ["Kalan Seans", "Kullanılan Seans", "Kullanılmış Ders Hakkı", "Harcanan Kredi"])
def test_kalan_kullanilan_giris_hakkina_eslesmez(baslik):
    e = esleme_tahmin_et("paketler", ["Üye No", "Paket", "Başlangıç", "Ücret", baslik])
    assert "giris_hakki" not in e.alanlar and baslik in e.eslesmeyenler


def test_paket_fiyati_ucrete_uyelik_durumu_duruma():
    e = esleme_tahmin_et("paketler", ["Üye No", "Paket Adı", "Başlangıç", "Paket Fiyatı", "Üyelik Durumu"])
    assert e.alanlar["ucret"] == "Paket Fiyatı" and e.alanlar["durum"] == "Üyelik Durumu"
    assert esleme_tahmin_et("paketler", ["Üye No", "Paket Durumu"]).alanlar["durum"] == "Paket Durumu"
    assert esleme_tahmin_et("paketler", ["Üye No", "Üyelik Ücreti"]).alanlar["ucret"] == "Üyelik Ücreti"


def test_belirsiz_baslik():
    e = esleme_tahmin_et("paketler", ["Üye No", "Paket Durum", "Ücret"])
    assert e.belirsizler == ["Paket Durum"]
    assert "paket_adi" not in e.alanlar and "durum" not in e.alanlar


def test_tek_basina_id_yalnizca_baska_kimlik_yoksa():
    assert esleme_tahmin_et("uyeler", ["ID", "Ad Soyad"]).alanlar["uye_kimlik"] == "ID"
    e = esleme_tahmin_et("paketler", ["ID", "Paket No", "Paket", "Başlangıç", "Fiyat"])
    assert "uye_kimlik" not in e.alanlar and "ID" in e.eslesmeyenler


def test_ad_ve_soyad_birlestirilir():
    tablo = dosya_oku(_csv(["Üye No;Adı;Soyadı", "1;Ayşe;Işık"]), "u.csv")
    e = esleme_tahmin_et("uyeler", tablo.basliklar)
    assert e.alanlar == {"uye_kimlik": "Üye No", "ad": "Adı", "soyad": "Soyadı"}
    assert _hazirla("uyeler", tablo).kayitlar[0].ad_soyad == "Ayşe Işık"


@pytest.mark.parametrize("baslik", ["TC Kimlik No", "T.C. No", "TCKN", "Kan Grubu", "Sağlık Durumu", "Parmak İzi",
                                    "Biyometrik Veri", "Hastalık", "Kullandığı İlaçlar"])
def test_hassas_baslik_eslesmez_ve_elle_verilse_reddedilir(baslik):
    basliklar = ["Üye No", "Ad Soyad", baslik]
    e = esleme_tahmin_et("uyeler", basliklar)
    assert baslik in e.hassaslar and baslik not in e.alanlar.values()
    with pytest.raises(EslemeHatasi, match="hassas alan"):
        esleme_dogrula("uyeler", {"uye_kimlik": "Üye No", "ad_soyad": baslik}, basliklar)


def test_hassas_sutun_okunurken_atilir():
    tablo = dosya_oku(_csv(["Üye No;Ad Soyad;TC Kimlik No", "1;Ali;12345678901"]), "u.csv")
    assert "12345678901" not in repr(tablo)


def test_esleme_dogrula_zorunlu_ve_olmayan_baslik():
    with pytest.raises(EslemeHatasi) as hata:
        esleme_dogrula("paketler", {"uye_kimlik": "Üye No", "paket_adi": "Yok Böyle"}, ["Üye No", "Paket"])
    sorunlar = hata.value.sorunlar
    assert "paket_adi: dosyada olmayan başlık" in sorunlar
    assert {"zorunlu alan eşleşmedi: baslangic", "zorunlu alan eşleşmedi: ucret"} <= set(sorunlar)
    assert esleme_dogrula("uyeler", {"uye_kimlik": "No", "ad_soyad": None, "ad": "Ad"}, ["No", "Ad"]) == {
        "uye_kimlik": "No", "ad": "Ad"}


# ---------------------------------------------------------------------------------------------
# Dönüştürücüler
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("deger, beklenen", [
    ("31.12.2025", (date(2025, 12, 31), None)),
    ("31/12/2025 14:30", (date(2025, 12, 31), time(14, 30))),
    ("31-12-2025 14:30:15", (date(2025, 12, 31), time(14, 30, 15))),
    ("2025-12-31", (date(2025, 12, 31), None)),
    ("1.2.25", (date(2025, 2, 1), None)),
    (45000, (date(2023, 3, 15), None)),
    ("45000", (date(2023, 3, 15), None)),
    (Decimal("45000.75"), (date(2023, 3, 15), time(18, 0))),
    (datetime(2025, 12, 31, 0, 0), (date(2025, 12, 31), None)),
    (date(2025, 12, 31), (date(2025, 12, 31), None)),
])
def test_tarih_coz(deger, beklenen):
    assert tarih_coz(deger) == beklenen


@pytest.mark.parametrize("deger, sebep", [
    ("13.13.2025", "gün/ay sırası"),
    ("12/31/2025", "gün/ay sırası"),
    ("31.02.2025", "geçersiz tarih"),
    ("31.12.2025 25:00", "geçersiz saat"),
    ("dün", "tanınmayan"),
    (12345, "tanınmayan"),
])
def test_tarih_coz_hatalari(deger, sebep):
    with pytest.raises(DegerHatasi, match=sebep):
        tarih_coz(deger)


def test_zaman_coz_istanbul_utc_ve_saatsiz_oglen():
    assert zaman_coz("31.12.2025 14:30", None, IST, SIMDI) == datetime(2025, 12, 31, 11, 30, tzinfo=UTC)
    assert zaman_coz("31.12.2025", None, IST, SIMDI) == datetime(2025, 12, 31, 9, 0, tzinfo=UTC)
    assert zaman_coz("31.12.2025", "08:15", IST, SIMDI) == datetime(2025, 12, 31, 5, 15, tzinfo=UTC)


def test_zaman_coz_gelecek_tarih_hata():
    yerel = SIMDI.astimezone(IST)
    assert zaman_coz(yerel.strftime("%d.%m.%Y"), "12:04", IST, SIMDI)           # 4 dk ileri: kabul
    with pytest.raises(DegerHatasi, match="gelecek"):
        zaman_coz(yerel.strftime("%d.%m.%Y"), "12:06", IST, SIMDI)
    with pytest.raises(DegerHatasi, match="gelecek"):
        zaman_coz((yerel + timedelta(days=1)).strftime("%d.%m.%Y"), None, IST, SIMDI)


def test_bugunun_sabah_girisi_ayri_saat_sutunuyla_gelecek_sayilmaz():
    """Saatsiz varsayılan (12:00) saat sütunundan önce denetlenmemeli."""
    simdi = datetime(2026, 10, 2, 7, 0, tzinfo=UTC)                              # İstanbul 10:00
    tablo = Tablo(["Üye No", "Tarih", "Saat"], [(2, ("1", "02.10.2026", "09:00"))], "csv")
    h = satirlari_hazirla("girisler", tablo, {"uye_kimlik": "Üye No", "tarih": "Tarih", "saat": "Saat"},
                          "Europe/Istanbul", BUGUN, False, KAYNAK, simdi=simdi)
    assert not h.hatalar and h.kayitlar[0].ziyaret_zamani == datetime(2026, 10, 2, 6, 0, tzinfo=UTC)


@pytest.mark.parametrize("deger, beklenen", [
    ("1.250,50", Decimal("1250.50")),
    ("1250.50", Decimal("1250.50")),
    ("1,250.50", Decimal("1250.50")),
    ("₺ 990", Decimal("990")),
    ("990 TL", Decimal("990")),
    ("12,5", Decimal("12.5")),
    ("0", Decimal("0")),
    (990, Decimal("990")),
    (Decimal("1250.5"), Decimal("1250.5")),
])
def test_para_coz(deger, beklenen):
    sonuc = para_coz(deger)
    assert sonuc == beklenen and type(sonuc) is Decimal


def test_para_coz_binlik_nokta_uyari_sayar():
    uyarilar = Counter()
    sonuc = para_coz("1.250", uyarilar)
    assert sonuc == Decimal("1250") and type(sonuc) is Decimal
    assert para_coz("1.250.000", uyarilar) == Decimal("1250000")
    assert uyarilar["binlik_nokta"] == 2


@pytest.mark.parametrize("deger, sebep", [
    ("-5", "negatif"),
    ("1,234", "ondalık"),
    ("1.2345", "ondalık"),
    ("abc", "tanınmayan"),
    ("1,2,3", "tanınmayan"),
    (None, "boş"),
])
def test_para_coz_hatalari(deger, sebep):
    with pytest.raises(DegerHatasi, match=sebep):
        para_coz(deger)


@pytest.mark.parametrize("tur, deger, beklenen", [
    ("paketler", "Devam Ediyor", "aktif"),
    ("paketler", "SÜRESİ DOLDU", "bitti"),
    ("paketler", "Tamamlandı", "bitti"),
    ("paketler", "İptal Edildi", "iptal"),
    ("paketler", "frozen", "donduruldu"),
    ("paketler", None, None),
    ("girisler", "Katıldı", "tamamlandi"),
    ("girisler", "No-Show", "gelmedi"),
    ("girisler", "iptal", "iptal"),
    ("girisler", None, "tamamlandi"),
])
def test_durum_coz(tur, deger, beklenen):
    assert durum_coz(tur, deger) == beklenen


def test_durum_coz_tanimsiz_hata():
    with pytest.raises(DegerHatasi, match="durum"):
        durum_coz("paketler", "belki")


def test_dis_kaynak():
    assert dis_kaynak_olustur("stuvio") == "csv:stuvio"
    for kotu in ("", "Stuvio", "a b", "x" * 41, "ş"):
        with pytest.raises(ValueError):
            dis_kaynak_olustur(kotu)


# ---------------------------------------------------------------------------------------------
# Satırların hazırlanması
# ---------------------------------------------------------------------------------------------
GIZLI_AD = "Zeynep Gizlioğlu"
GIZLI_TELEFON = "0555 987 65 43"
GIZLI_EPOSTA = "gizli.kisi@ornek.com"


def test_hata_mesajlarinda_kisisel_deger_gecmez_ve_esik():
    satirlar = ["Üye No;Ad Soyad;Telefon;E-posta"]
    satirlar += [f"{i};Üye {i};;" for i in range(1, 19)]
    satirlar += [f";{GIZLI_AD};{GIZLI_TELEFON};{GIZLI_EPOSTA}",            # kimlik boş → hata
                 f"19;{GIZLI_AD} 2;abc{GIZLI_TELEFON};{GIZLI_EPOSTA}"]      # telefon geçersiz → uyarı
    tablo = dosya_oku(_csv(satirlar), "u.csv")
    h = _hazirla("uyeler", tablo)
    assert (h.okunan, h.gecerli, h.hatali) == (20, 19, 1)
    assert h.uyarilar["telefon_gecersiz"] == 1
    assert not h.esik_asildi                                                # 1/20 = %5
    metin = " ".join(str(x) for x in h.hatalar) + repr(h.hatalar) + repr(h.uyarilar)
    for gizli in (GIZLI_AD, "Gizlioğlu", GIZLI_TELEFON, "987 65 43", "5559876543", GIZLI_EPOSTA):
        assert gizli not in metin
    assert str(h.hatalar[0]) == "satır 20, uye_kimlik: boş"


def test_paket_hata_mesajinda_deger_gecmez():
    tablo = dosya_oku(_csv(["Üye No;Paket;Başlangıç;Bitiş;Fiyat;Durum",
                            "1;Aylık;01.09.2026;01.10.2026;GizliTutar99;GizliDurumX"]), "p.csv")
    h = _hazirla("paketler", tablo)
    metin = " ".join(str(x) for x in h.hatalar)
    assert "GizliTutar99" not in metin and "GizliDurumX" not in metin
    assert {(x.alan, x.sebep) for x in h.hatalar} == {("ucret", "tanınmayan tutar"), ("durum", "tanınmayan durum")}


def test_yuzde_on_esigi():
    def tablo(hatali: int) -> Tablo:
        return Tablo(["Üye No", "Ad Soyad"],
                     [(i + 2, (None if i < hatali else str(i), f"Üye {i}")) for i in range(20)], "csv")

    assert not _hazirla("uyeler", tablo(2)).esik_asildi                   # %10: eşik değil
    assert _hazirla("uyeler", tablo(3)).esik_asildi                       # %15


def test_anonim_mod():
    tablo = dosya_oku(_csv(["Üye No;Ad Soyad;Telefon;E-posta", f"7;{GIZLI_AD};{GIZLI_TELEFON};{GIZLI_EPOSTA}"]),
                      "u.csv")
    k1 = _hazirla("uyeler", tablo, anonim=True).kayitlar[0]
    k2 = _hazirla("uyeler", tablo, anonim=True).kayitlar[0]
    assert k1 == k2
    assert k1.ad_soyad.startswith("Üye ") and len(k1.ad_soyad) == 10
    assert k1.telefon_e164 is None and k1.eposta is None
    assert GIZLI_AD not in repr(k1)
    # Ad sütunu eşleşmese de çalışır; farklı kaynakta farklı ad
    sadece_kimlik = Tablo(["Üye No"], [(2, ("7",))], "csv")
    k3 = satirlari_hazirla("uyeler", sadece_kimlik, {"uye_kimlik": "Üye No"}, "Europe/Istanbul", BUGUN, True,
                           KAYNAK).kayitlar[0]
    k4 = satirlari_hazirla("uyeler", sadece_kimlik, {"uye_kimlik": "Üye No"}, "Europe/Istanbul", BUGUN, True,
                           "csv:baska").kayitlar[0]
    assert k3.ad_soyad == k1.ad_soyad and k4.ad_soyad != k1.ad_soyad


def test_ayni_telefon_ikinci_uyede_bos_birakilir():
    tablo = dosya_oku(_csv(["Üye No;Ad Soyad;Telefon", "1;Anne;0532 111 22 33", "2;Çocuk;05321112233"]), "u.csv")
    h = _hazirla("uyeler", tablo)
    assert [k.telefon_e164 for k in h.kayitlar] == ["+905321112233", None]
    assert h.uyarilar["telefon_tekrar"] == 1


def test_acik_kimlik_tekrari_satir_hatasi():
    tablo = dosya_oku(_csv(["Üye No;Ad Soyad", "1;Ali", "1;Veli"]), "u.csv")
    h = _hazirla("uyeler", tablo)
    assert h.gecerli == 1 and str(h.hatalar[0]) == "satır 3, uye_kimlik: kimlik dosyada tekrar ediyor (ilk: satır 2)"


def test_paket_turu_durum_cikarimi_ve_zincir():
    tablo = dosya_oku(_csv([
        "Üye No;Paket Adı;Başlangıç Tarihi;Bitiş Tarihi;Seans Sayısı;Ücret;Durum",
        "1;3 Aylık;01.07.2026;01.10.2026;;6.000,00;",          # 3. paket (sırasız), bitiş < bugün → bitti
        "1;Aylık;01.01.2026;01.02.2026;;2.000,00;",            # 1.
        "1;12 Giriş;01.03.2026;;12;2.400,00;",                 # 2. giriş bazlı, bitişsiz → aktif
        "2;Aylık;15.09.2026;15.10.2026;;2.000,00;",            # bitiş ≥ bugün → aktif
        "2;Aylık;01.05.2026;01.06.2026;;2.000,00;Dondu",       # açık durum
        "3;Süresiz;01.05.2026;;;2.000,00;",                    # süre bazlı, bitiş yok → hata
        "4;Ters;01.05.2026;01.04.2026;;2.000,00;",             # bitiş ≤ başlangıç → hata
        "5;Sıfır;01.05.2026;;0;100;",                          # giriş hakkı 0 → hata
    ]), "p.csv")
    h = _hazirla("paketler", tablo)
    assert {(x.satir, x.alan) for x in h.hatalar} == {(7, "bitis"), (8, "bitis"), (9, "giris_hakki")}
    p = {(k.uye_kimlik, k.ad, k.baslangic_tarihi.month): k for k in h.kayitlar}
    uc, bir, iki = p[("1", "3 Aylık", 7)], p[("1", "Aylık", 1)], p[("1", "12 Giriş", 3)]
    assert (bir.tur, bir.durum, bir.onceki_dis_kimlik) == ("sure", "bitti", None)
    assert (iki.tur, iki.giris_hakki, iki.durum, iki.onceki_dis_kimlik) == ("giris", 12, "aktif", bir.dis_kimlik)
    assert (uc.durum, uc.onceki_dis_kimlik) == ("bitti", iki.dis_kimlik)
    assert uc.ucret == Decimal("6000.00") and type(uc.ucret) is Decimal
    eylul, mayis = p[("2", "Aylık", 9)], p[("2", "Aylık", 5)]
    assert (eylul.durum, mayis.durum, eylul.onceki_dis_kimlik) == ("aktif", "donduruldu", mayis.dis_kimlik)
    assert all(isinstance(k, PaketKaydi) and k.dis_kimlik.startswith("P") and len(k.dis_kimlik) == 17
               for k in h.kayitlar)


def test_paket_kimligi_dosyadan_gelirse_kullanilir():
    tablo = dosya_oku(_csv(["Üye No;Paket No;Paket;Başlangıç;Bitiş;Fiyat", "1;S-9;Aylık;01.09.2026;01.10.2026;10"]),
                      "p.csv")
    assert _hazirla("paketler", tablo).kayitlar[0].dis_kimlik == "S-9"


def test_turetilmis_giris_kimligi_ayni_satir_iki_kez_tek_kayit():
    tablo = dosya_oku(_csv(["Üye No;Giriş Tarihi", "1;15.09.2026 18:00", "1;15.09.2026 18:00", "1;16.09.2026 18:00",
                            "2;15.09.2026 18:00"]), "g.csv")
    h = _hazirla("girisler", tablo)
    assert h.gecerli == 3 and not h.hatalar and h.uyarilar["tekrar_satir"] == 1
    assert len({k.dis_kimlik for k in h.kayitlar}) == 3
    assert all(isinstance(k, GirisKaydi) and k.dis_kimlik.startswith("G") and k.durum == "tamamlandi"
               and k.toplam_tutar == Decimal("0") for k in h.kayitlar)
    # Kimlik kararlı: aynı dosya yeniden okununca aynı kimlikler
    assert [k.dis_kimlik for k in _hazirla("girisler", tablo).kayitlar] == [k.dis_kimlik for k in h.kayitlar]


def test_giris_bilinmeyen_uye_satir_hatasi():
    tablo = dosya_oku(_csv(["Üye No;Tarih", "1;15.09.2026", "9;15.09.2026"]), "g.csv")
    h = _hazirla("girisler", tablo, bilinen={"1"})
    assert h.gecerli == 1 and [(x.satir, x.alan) for x in h.hatalar] == [(3, "uye_kimlik")]


def test_ciro_cift_sayim_uyarisi():
    assert ciro_cift_sayim_uyarisi({"uye_kimlik": "No", "tarih": "T", "tutar": "Tutar"}, True) == CIFT_SAYIM_UYARISI
    assert ciro_cift_sayim_uyarisi({"uye_kimlik": "No", "tarih": "T", "tutar": "Tutar"}, False) is None
    assert ciro_cift_sayim_uyarisi({"uye_kimlik": "No", "tarih": "T"}, True) is None


def test_beyaz_liste_eslesmeyen_sutun_kayitlara_girmez():
    tablo = dosya_oku(_csv(["Üye No;Ad Soyad;Adres;Notlar", "1;Ali;GizliAdres 5;GizliNot"]), "u.csv")
    h = _hazirla("uyeler", tablo)
    assert "GizliAdres" not in repr(h) and "GizliNot" not in repr(h)
