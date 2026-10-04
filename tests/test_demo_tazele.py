"""Demo tazeleme (Adım 9c, K11–K16): saf yardımcılar, panosu_test'te geçici bir [DEMO] işletmede kaydırma, değişmezlik,
gider penceresi, kuru çalıştırma ve CLI kilidi.

tazele() burada panosu_test motorlarıyla doğrudan çağrılır (CLI yalnızca _demo kabul eder). panosu_test'teki tek
[DEMO] işletme bu dosyanın kurduğu geçici işletmedir; testten sonra silinir.
"""

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from sqlalchemy import text

from sentetik import demo_tazele
from sentetik.demo_tazele import gider_penceresi, kaydirma_gunu, tazele
from sentetik.yukleyici import _SILME_SIRASI, DEMO_ONEK

ISTANBUL = ZoneInfo("Europe/Istanbul")
BUGUN = datetime.now(ISTANBUL).date()
DEMO_ADI = f"{DEMO_ONEK} Tazeleme Testi"


def _ay(gun: date, fark: int) -> date:
    toplam = gun.year * 12 + gun.month - 1 + fark
    return date(toplam // 12, toplam % 12 + 1, 1)


# ---------------------------------------------------------------------------------------------
# Saf yardımcılar
# ---------------------------------------------------------------------------------------------
def test_kaydirma_gunu():
    b = date(2026, 10, 2)
    assert kaydirma_gunu(None, b) == 0
    assert kaydirma_gunu(b - timedelta(days=1), b) == 0
    assert kaydirma_gunu(b - timedelta(days=3), b) == 2
    assert kaydirma_gunu(b, b) == 0
    assert kaydirma_gunu(b + timedelta(days=5), b) == 0


def test_gider_penceresi():
    aylar = [date(2026, 3, 1), date(2026, 4, 1), date(2026, 5, 1)]
    assert gider_penceresi(aylar, date(2026, 5, 20)) == ([], [])                      # aynı ay
    assert gider_penceresi(aylar, date(2026, 4, 20)) == ([], [])                      # gider ayı ileride
    assert gider_penceresi(aylar, date(2026, 6, 2)) == ([date(2026, 6, 1)], [date(2026, 3, 1)])
    ekle, sil = gider_penceresi(aylar, date(2026, 8, 31))
    assert ekle == [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)]
    assert sil == aylar
    assert len(set(aylar) - set(sil) | set(ekle)) == len(aylar)                       # L korunur
    assert gider_penceresi([], date(2026, 6, 2)) == ([], [])
    ekle, sil = gider_penceresi([date(2026, 11, 1)], date(2027, 2, 1))                # yıl geçişi; L = 1
    assert ekle == [date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1)]
    assert sil == [date(2026, 11, 1)]                                                 # L'den fazla silinmez


# ---------------------------------------------------------------------------------------------
# panosu_test'te geçici [DEMO] işletme
# ---------------------------------------------------------------------------------------------
def _demo_sil(con) -> None:
    idler = list(con.execute(text("SELECT isletme_id FROM isletmeler WHERE starts_with(ad, :o)"),
                             {"o": DEMO_ONEK}).scalars())
    if not idler:
        return
    for tablo in _SILME_SIRASI:
        con.execute(text(f"DELETE FROM {tablo} WHERE isletme_id = ANY(:idler)"), {"idler": idler})
    con.execute(text("DELETE FROM isletmeler WHERE isletme_id = ANY(:idler)"), {"idler": idler})


@pytest.fixture()
def demo_kur(admin_engine):
    """Fabrika: [DEMO] işletme + üyeler + ziyaretler + paketler + izin + giderler. Testten sonra silinir."""
    with admin_engine.begin() as con:
        con.execute(text("SET LOCAL lock_timeout = '10s'"))
        _demo_sil(con)                                   # önceki yarım kalmış çalışmadan artık

    def _kur(son_gun: date, *, uye: int = 15, tohum: int = 7, gider_aylari: tuple[date, ...] = ()) -> uuid.UUID:
        rng = np.random.default_rng(tohum)
        iid = uuid.uuid4()
        with admin_engine.begin() as con:
            con.execute(text("INSERT INTO isletmeler (isletme_id, ad) VALUES (:i, :a)"), {"i": iid, "a": DEMO_ADI})
            musteriler = []
            for no in range(uye):
                m = uuid.uuid4()
                musteriler.append(m)
                con.execute(text("INSERT INTO musteriler (musteri_id, isletme_id, ad_soyad) VALUES (:m, :i, :a)"),
                            {"m": m, "i": iid, "a": f"Üye {no}"})
                # Geriye doğru ziyaretler: ilk üye tam son_gun'de gelir; diğerleri rastgele; bir kısmı bırakmış
                gun = 0 if no == 0 else int(rng.integers(0, 40 if no % 3 == 0 else 6))
                while gun < 200:
                    an = datetime.combine(son_gun - timedelta(days=gun), time(9), tzinfo=ISTANBUL) + timedelta(
                        minutes=int(rng.integers(0, 600)))
                    con.execute(text("INSERT INTO ziyaretler (isletme_id, musteri_id, ziyaret_zamani) "
                                     "VALUES (:i, :m, :z)"), {"i": iid, "m": m, "z": an})
                    gun += int(rng.integers(3, 12))
            con.execute(text("INSERT INTO musteri_izinleri (isletme_id, musteri_id, kanal, durum, kaynak, "
                             "kayit_zamani) VALUES (:i, :m, 'whatsapp', 'verildi', 'yazili_form', :z)"),
                        {"i": iid, "m": musteriler[0], "z": datetime.combine(son_gun - timedelta(days=90), time(12),
                                                                              tzinfo=ISTANBUL)})
            bugun = son_gun + timedelta(days=1)
            for no, m in enumerate(musteriler[:6]):
                if no % 2 == 0:
                    tur, ad, bit, hak = "sure", "1 Aylık", bugun + timedelta(days=10 + 5 * no), None
                else:
                    tur, ad, bit, hak = "giris", "12 Giriş", bugun + timedelta(days=30), 12
                con.execute(text("INSERT INTO musteri_paketleri (isletme_id, musteri_id, tur, ad, baslangic_tarihi, "
                                 "bitis_tarihi, giris_hakki, ucret) VALUES (:i, :m, :t, :a, :b, :e, :h, 2500)"),
                            {"i": iid, "m": m, "t": tur, "a": ad, "b": bugun - timedelta(days=20), "e": bit,
                             "h": hak})
            for ay in gider_aylari:
                for kategori, tutar in (("kira", "40000.00"), ("personel", "90000.00")):
                    con.execute(text("INSERT INTO isletme_giderleri (isletme_id, ay, kategori, tutar, aciklama) "
                                     "VALUES (:i, :ay, :k, :t, :a)"),
                                {"i": iid, "ay": ay, "k": kategori, "t": tutar, "a": f"{kategori} açıklaması"})
        return iid

    yield _kur
    with admin_engine.begin() as con:
        con.execute(text("SET LOCAL lock_timeout = '10s'"))
        _demo_sil(con)


@pytest.fixture()
def uygulama():
    from database import engine
    return engine


def _tarihler(admin_engine, iid) -> dict[str, list]:
    i = {"i": iid}
    with admin_engine.connect() as con:
        return {
            "ziyaret": con.execute(text("SELECT ziyaret_id, ziyaret_zamani FROM ziyaretler WHERE isletme_id = :i "
                                        "ORDER BY ziyaret_id"), i).all(),
            "paket": con.execute(text("SELECT paket_id, baslangic_tarihi, bitis_tarihi FROM musteri_paketleri "
                                      "WHERE isletme_id = :i ORDER BY paket_id"), i).all(),
            "musteri": con.execute(text("SELECT musteri_id, olusturma_zamani FROM musteriler WHERE isletme_id = :i "
                                        "ORDER BY musteri_id"), i).all(),
            "izin": con.execute(text("SELECT izin_id, kayit_zamani FROM musteri_izinleri WHERE isletme_id = :i "
                                     "ORDER BY izin_id"), i).all(),
            "gider": con.execute(text("SELECT ay, kategori, tutar, aciklama FROM isletme_giderleri "
                                      "WHERE isletme_id = :i ORDER BY ay, kategori"), i).all(),
        }


def _denetim_sayisi(admin_engine, iid) -> int:
    with admin_engine.connect() as con:
        return con.scalar(text("SELECT count(*) FROM denetim_kayitlari WHERE isletme_id = :i"), {"i": iid})


def _son_ziyaret_gunu(admin_engine, iid) -> date:
    with admin_engine.connect() as con:
        return con.scalar(text("SELECT max((ziyaret_zamani AT TIME ZONE 'Europe/Istanbul')::date) FROM ziyaretler "
                               "WHERE isletme_id = :i"), {"i": iid})


def _sessiz(*_):
    pass


def test_kaydirma_tum_tarihler_ayni_gun(admin_engine, uygulama, demo_kur):
    B = BUGUN
    iid = demo_kur(B - timedelta(days=5))
    once = _tarihler(admin_engine, iid)
    sonuc = tazele(admin_engine, uygulama, bugun=B, ilerleme=_sessiz)
    sonra = _tarihler(admin_engine, iid)

    s = next(s for s in sonuc if s.isletme_id == iid)
    assert s.kaydirma_gun == 4
    assert (s.ziyaret, s.paket, s.musteri, s.izin) == (len(once["ziyaret"]), len(once["paket"]),
                                                      len(once["musteri"]), len(once["izin"]))
    for tablo in ("ziyaret", "musteri", "izin"):
        assert len(sonra[tablo]) == len(once[tablo])
        for o, n in zip(once[tablo], sonra[tablo]):
            assert o[0] == n[0] and n[1] - o[1] == timedelta(days=4)
    for o, n in zip(once["paket"], sonra["paket"], strict=True):
        assert o.paket_id == n.paket_id
        assert n.baslangic_tarihi - o.baslangic_tarihi == timedelta(days=4)
        assert n.bitis_tarihi - o.bitis_tarihi == timedelta(days=4)
    assert _son_ziyaret_gunu(admin_engine, iid) == B - timedelta(days=1)
    assert s.risk_satiri == len(once["paket"])                   # bugün için risk hesaplandı


def test_ikinci_tazele_idempotent(admin_engine, uygulama, demo_kur):
    B = BUGUN
    iid = demo_kur(B - timedelta(days=5))
    tazele(admin_engine, uygulama, bugun=B, ilerleme=_sessiz)
    once = _tarihler(admin_engine, iid)
    sonuc = tazele(admin_engine, uygulama, bugun=B, ilerleme=_sessiz)
    s = next(s for s in sonuc if s.isletme_id == iid)
    assert s.kaydirma_gun == 0
    assert s.risk_satiri is None and s.risk_notu == "zaten bugün"
    assert _tarihler(admin_engine, iid) == once


def test_denetim_kayitlari_degismez(admin_engine, uygulama, demo_kur):
    B = BUGUN
    iid = demo_kur(B - timedelta(days=5), gider_aylari=(_ay(B, -2), _ay(B, -1)))
    once = _denetim_sayisi(admin_engine, iid)
    sonuc = tazele(admin_engine, uygulama, bugun=B, ilerleme=_sessiz)
    s = next(s for s in sonuc if s.isletme_id == iid)
    assert s.silinen_denetim > 0                                 # paket UPDATE'leri + gider INSERT/DELETE
    assert _denetim_sayisi(admin_engine, iid) == once


def test_demo_olmayan_isletmeye_dokunulmaz(admin_engine, uygulama, demo_kur, iki_kiraci):
    a, _ = iki_kiraci
    B = BUGUN
    demo_kur(B - timedelta(days=5))
    zaman = datetime.combine(B - timedelta(days=10), time(12), tzinfo=ISTANBUL)
    with admin_engine.begin() as con:
        con.execute(text("INSERT INTO ziyaretler (isletme_id, musteri_id, ziyaret_zamani) VALUES (:i, :m, :z)"),
                    {"i": a.isletme_id, "m": a.musteri_id, "z": zaman})
        con.execute(text("INSERT INTO musteri_paketleri (isletme_id, musteri_id, tur, ad, baslangic_tarihi, "
                         "bitis_tarihi, ucret) VALUES (:i, :m, 'sure', '1 Aylık', :b, :e, 100)"),
                    {"i": a.isletme_id, "m": a.musteri_id, "b": B - timedelta(days=10), "e": B + timedelta(days=20)})
    once = _tarihler(admin_engine, a.isletme_id)
    denetim_once = _denetim_sayisi(admin_engine, a.isletme_id)
    assert denetim_once > 0

    sonuc = tazele(admin_engine, uygulama, bugun=B, ilerleme=_sessiz)

    assert a.isletme_id not in {s.isletme_id for s in sonuc}
    assert _tarihler(admin_engine, a.isletme_id) == once
    assert _denetim_sayisi(admin_engine, a.isletme_id) == denetim_once


def test_degismezlik_p_hayatta_birebir(admin_engine, uygulama, demo_kur, oturum):
    """K11: kaydırılmış demoda bugün hesaplanan p_hayatta_simdi (and since K61 p_yenileme) eskisiyle birebir aynı."""
    from servisler.yenileme_servisi import yenileme_hesapla

    T0 = BUGUN
    iid = demo_kur(T0 - timedelta(days=1), uye=15, tohum=11)
    db = oturum()
    db.info["isletme_id"] = iid
    assert yenileme_hesapla(db, T0) == 6
    db.close()

    sonuc = tazele(admin_engine, uygulama, bugun=T0 + timedelta(days=7), ilerleme=_sessiz)
    s = next(s for s in sonuc if s.isletme_id == iid)
    assert s.kaydirma_gun == 7
    assert s.risk_satiri == 6

    with admin_engine.connect() as con:
        satirlar = con.execute(text(
            "SELECT paket_id, hesaplama_tarihi, p_hayatta_simdi, p_yenileme, kalan_gun, kalan_giris "
            "FROM yenileme_riskleri WHERE isletme_id = :i"), {"i": iid}).all()
    eski = {r.paket_id: r for r in satirlar if r.hesaplama_tarihi == T0}
    yeni = {r.paket_id: r for r in satirlar if r.hesaplama_tarihi == T0 + timedelta(days=7)}
    assert len(eski) == len(yeni) == 6 and eski.keys() == yeni.keys()
    for paket_id, e in eski.items():
        y = yeni[paket_id]
        assert y.p_hayatta_simdi == e.p_hayatta_simdi
        assert (y.kalan_gun, y.kalan_giris) == (e.kalan_gun, e.kalan_giris)
        assert y.p_yenileme == e.p_yenileme                       # K61: exact formula, no seed


def test_gider_penceresi_db(admin_engine, uygulama, demo_kur):
    B = BUGUN
    iid = demo_kur(B - timedelta(days=1), gider_aylari=(_ay(B, -2), _ay(B, -1)))
    tazele(admin_engine, uygulama, bugun=B, ilerleme=_sessiz)
    giderler = _tarihler(admin_engine, iid)["gider"]
    assert sorted({g.ay for g in giderler}) == [_ay(B, -1), _ay(B, 0)]
    bu_ay = [(g.kategori, g.tutar, g.aciklama) for g in giderler if g.ay == _ay(B, 0)]
    gecen = [(g.kategori, g.tutar, g.aciklama) for g in giderler if g.ay == _ay(B, -1)]
    assert bu_ay == gecen and len(bu_ay) == 2


def test_kuru_hicbir_sey_yazmaz(admin_engine, uygulama, demo_kur):
    B = BUGUN
    iid = demo_kur(B - timedelta(days=5), gider_aylari=(_ay(B, -2), _ay(B, -1)))
    once, denetim_once = _tarihler(admin_engine, iid), _denetim_sayisi(admin_engine, iid)
    sonuc = tazele(admin_engine, uygulama, bugun=B, kuru=True, ilerleme=_sessiz)
    s = next(s for s in sonuc if s.isletme_id == iid)
    assert s.kaydirma_gun == 4 and s.ziyaret == len(once["ziyaret"])                  # rapor dolu
    assert s.eklenen_gider_ayi == [_ay(B, 0)] and s.silinen_gider_ayi == [_ay(B, -2)]
    assert s.risk_satiri is None
    assert _tarihler(admin_engine, iid) == once
    assert _denetim_sayisi(admin_engine, iid) == denetim_once
    with admin_engine.connect() as con:
        assert con.scalar(text("SELECT count(*) FROM yenileme_riskleri WHERE isletme_id = :i"), {"i": iid}) == 0


@pytest.mark.parametrize("ad", ["panosu_test", "panosu", "panosu_canli", "demo"])
def test_cli_baglanmadan_reddeder(monkeypatch, ad):
    def _yasak(*a, **k):
        raise AssertionError("Kilit, bağlantı kurulmadan önce devreye girmeliydi")
    monkeypatch.setattr(demo_tazele, "create_engine", _yasak)
    with pytest.raises(SystemExit):
        demo_tazele.main(["--veritabani", ad])
    with pytest.raises(SystemExit):
        demo_tazele.main(["--veritabani", ad, "--kuru"])


# ---------------------------------------------------------------------------------------------
# demo_sunucu: gece tazelemesinin zamanı (K16)
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("saat, beklenen_gun", [
    (time(2, 59), 2),                     # 02:59 → aynı gün 03:00
    (time(0, 0), 2),
    (time(3, 0), 3),                      # tam 03:00 → ertesi gün
    (time(3, 0, 1), 3),
    (time(23, 59), 3),
])
def test_sonraki_calisma(saat, beklenen_gun):
    from sentetik.demo_sunucu import sonraki_calisma
    sonuc = sonraki_calisma(datetime.combine(date(2026, 10, 2), saat, tzinfo=ISTANBUL))
    assert sonuc == datetime(2026, 10, beklenen_gun, 3, 0, tzinfo=ISTANBUL)


def test_sonraki_calisma_baska_saat_diliminden():
    from datetime import timezone

    from sentetik.demo_sunucu import sonraki_calisma
    # 2026-10-01 23:30 UTC = 2026-10-02 02:30 İstanbul → aynı (İstanbul) gün 03:00
    sonuc = sonraki_calisma(datetime(2026, 10, 1, 23, 30, tzinfo=timezone.utc))
    assert sonuc == datetime(2026, 10, 2, 3, 0, tzinfo=ISTANBUL)
