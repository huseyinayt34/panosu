"""0002 şeması (veritabanı düzeyi, panosu_app rolüyle): tür kısıtları, hesaplanan riskteki_para, kiracı izolasyonu."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError

from models import MusteriPaketi, YenilemeRiski


def _paket(kiraci, **alanlar) -> MusteriPaketi:
    varsayilan = dict(musteri_id=kiraci.musteri_id, tur="sure", ad="1 Aylık", baslangic_tarihi=date(2026, 9, 1),
                      bitis_tarihi=date(2026, 10, 1), ucret=Decimal("2500.00"))
    return MusteriPaketi(**{**varsayilan, **alanlar})


@pytest.mark.parametrize("alanlar", [
    {"tur": "sure", "bitis_tarihi": None},                                       # sure: bitiş zorunlu
    {"tur": "sure", "giris_hakki": 12},                                          # sure: hak verilmez
    {"tur": "giris", "bitis_tarihi": None, "giris_hakki": None},                 # giris: hak zorunlu
    {"tur": "giris", "bitis_tarihi": None, "giris_hakki": 0},                    # giris: hak > 0
    {"bitis_tarihi": date(2026, 9, 1)},                                          # bitiş > başlangıç
    {"tur": "abonelik"},
    {"ucret": Decimal("-1")},
])
def test_tur_kisitlari(oturum, iki_kiraci, alanlar):
    a, _ = iki_kiraci
    db = oturum(a)
    db.add(_paket(a, **alanlar))
    with pytest.raises(IntegrityError):
        db.flush()


def test_gecerli_turler_kabul_edilir(oturum, iki_kiraci):
    a, _ = iki_kiraci
    db = oturum(a)
    db.add_all([_paket(a), _paket(a, tur="giris", ad="12 Giriş", bitis_tarihi=None, giris_hakki=12,
                                    ucret=Decimal("800"))])
    db.flush()                                           # commit edilmez, oturum kapanınca geri alınır


def test_riskteki_para_hesaplanan_sutun(oturum, iki_kiraci):
    a, _ = iki_kiraci
    db = oturum(a)
    paket = _paket(a, ucret=Decimal("6000.00"))
    db.add(paket)
    db.flush()
    risk = YenilemeRiski(musteri_id=a.musteri_id, paket_id=paket.paket_id, hesaplama_tarihi=date(2026, 9, 20),
                         model_versiyonu="test", p_yenileme=Decimal("0.3750"), yenileme_tutari=Decimal("6000.00"))
    db.add(risk)
    db.flush()
    db.refresh(risk)
    assert risk.riskteki_para == Decimal("3750.00")      # (1 − 0.375) × 6000


def test_baska_kiracinin_paketi_gorunmez_ve_yazilamaz(oturum, iki_kiraci, admin_engine):
    a, b = iki_kiraci
    db_b = oturum(b)
    paket_b = _paket(b)
    db_b.add(paket_b)
    db_b.commit()
    try:
        db_a = oturum(a)
        assert db_a.get(MusteriPaketi, paket_b.paket_id) is None
        assert db_a.scalars(select(MusteriPaketi)).all() == []

        db_a.add(_paket(b, isletme_id=b.isletme_id))      # B adına yazma: RLS WITH CHECK
        with pytest.raises(DBAPIError):
            db_a.flush()
        db_a.rollback()

        db_a.add(_paket(b))                               # A bağlamında B'nin müşterisine bağlama: bileşik FK
        with pytest.raises(IntegrityError):
            db_a.flush()
        db_a.rollback()
    finally:
        db_a.close()
        db_b.close()
