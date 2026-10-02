"""Komut: python -m sentetik.demo_tazele --veritabani panosu_demo [--kuru]

Demo verisini bugüne kaydırır (Adım 9c; proje sahibi kararı, 2026-10-02; `docs/adim-9-tasarim.md` K11–K16).

K11 Zaman kaydırma: [DEMO] işletmelerin tüm tarihleri aynı d gün ileri kaydırılır; yeniden üretim yok (kimlikler,
    üyelikler, oturumlar korunur). M3 ve yenileme simülasyonu zamanı yalnızca farklarla görür (x, t_x, T, kalan gün),
    yani model zaman ötelemesine göre değişmezdir: p_hayatta_simdi birebir aynı kalır; p_yenileme yalnızca Monte
    Carlo hatası kadar oynar (simülasyon tohumu hesaplama tarihine bağlı).
K12 d = (yerel bugün − 1) − en son ziyaretin yerel günü; d ≤ 0 → dokunma. Tazelemeden sonra son ziyaret günü = dün.
K13 Kayanlar: ziyaretler.ziyaret_zamani, musteri_paketleri.baslangic_tarihi/bitis_tarihi, musteriler.olusturma_zamani,
    musteri_izinleri.kayit_zamani. yenileme_riskleri kaymaz; bugün için yeniden hesaplanır. isletme_giderleri: gider
    ayı sayısı korunur (yeni aylara en son ayın satırları kopyalanır, aynı sayıda en eski ay silinir).
K14 Kaydırmanın ürettiği denetim_kayitlari satırları aynı işlemde silinir (yalnızca [DEMO] kimlikleri, zaman = now()).
K15 Yalnızca adı "_demo" ile biten veritabanı (bağlantıdan önce doğrulanır) ve adı "[DEMO]" ile başlayan işletmeler.
    Tüm [DEMO] işletmeler tek işlemde, pg_advisory_xact_lock altında. Risk yeniden hesabı commit'ten sonra, işletme
    başına uygulama rolüyle ve kiracı bağlamında (yenileme_hesapla; RLS ve after_begin değişmez).
K16 demo_sunucu açılışta ve her gece 03:00'te (Europe/Istanbul) tazeler.

KURAL 3 İSTİSNASI (yukleyici.temizle() ile aynı, belgelenmiş): kaydırma YÖNETİCİ bağlantısıyla yapılır ve
sorgulara ELLE isletme_id filtresi eklenir; çünkü işlem birden çok kiracıya dokunur ve panosu_app'in denetim kaydı
silme yetkisi yoktur. Bu yol yalnızca adı "[DEMO]" ile başlayan işletmelere ve "_demo" veritabanına açıktır.
"""

import argparse
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, create_engine, text

from sentetik.yukleyici import DEMO_ONEK, DemoDisiVeritabani, baglanti_adresleri, demo_veritabani_dogrula

KILIT_ANAHTARI = "panosu.demo_tazele"
_KAYAN_TABLOLAR = (
    # (alan adı, tablo, SET ifadesi)
    ("ziyaret", "ziyaretler", "ziyaret_zamani = ziyaret_zamani + make_interval(days => :d)"),
    ("paket", "musteri_paketleri", "baslangic_tarihi = baslangic_tarihi + :d, bitis_tarihi = bitis_tarihi + :d"),
    ("musteri", "musteriler", "olusturma_zamani = olusturma_zamani + make_interval(days => :d)"),
    ("izin", "musteri_izinleri", "kayit_zamani = kayit_zamani + make_interval(days => :d)"),
)


# ---------------------------------------------------------------------------------------------
# Saf yardımcılar
# ---------------------------------------------------------------------------------------------
def kaydirma_gunu(son_ziyaret_gunu: date | None, bugun: date) -> int:
    """K12: son ziyaret gününü düne getiren gün sayısı; ziyaret yoksa veya son ziyaret dün/bugün/ileride ise 0."""
    if son_ziyaret_gunu is None:
        return 0
    return max(0, (bugun - timedelta(days=1) - son_ziyaret_gunu).days)


def _sonraki_ay(ay: date) -> date:
    return date(ay.year + ay.month // 12, ay.month % 12 + 1, 1)


def gider_penceresi(aylar: list[date], bugun: date) -> tuple[list[date], list[date]]:
    """K13: (eklenecek aylar, silinecek aylar). Bugünün ayı en son gider ayından sonraysa aradaki her ay eklenir ve
    aynı sayıda en eski ay silinir (gider ayı sayısı L korunur; L'den fazla silinmez)."""
    if not aylar:
        return [], []
    bu_ay = bugun.replace(day=1)
    en_son = max(aylar)
    if bu_ay <= en_son:
        return [], []
    eklenecek = []
    ay = _sonraki_ay(en_son)
    while ay <= bu_ay:
        eklenecek.append(ay)
        ay = _sonraki_ay(ay)
    silinecek = sorted(set(aylar))[:len(eklenecek)]
    return eklenecek, silinecek


@dataclass
class IsletmeTazeleme:
    isletme_id: uuid.UUID
    ad: str
    kaydirma_gun: int
    ziyaret: int = 0                 # kaydırılan (kuru: kaydırılacak) satır sayıları
    paket: int = 0
    musteri: int = 0
    izin: int = 0
    eklenen_gider_ayi: list[date] = field(default_factory=list)
    silinen_gider_ayi: list[date] = field(default_factory=list)
    silinen_denetim: int = 0
    risk_satiri: int | None = None   # yenileme_hesapla dönüşü; hesaplanmadıysa None
    risk_notu: str = ""              # risk satırı neden yok / ne yapıldı (ilerleme çıktısı için)
    bugun: date | None = None        # işletmenin yerel bugünü
    sure_sn: float = 0.0


# ---------------------------------------------------------------------------------------------
# Tazeleme
# ---------------------------------------------------------------------------------------------
def _kaydir(con, s: IsletmeTazeleme, kuru: bool) -> None:
    for alan, tablo, set_ifadesi in _KAYAN_TABLOLAR:
        degerler = {"i": s.isletme_id, "d": s.kaydirma_gun}
        if kuru:
            sayi = con.scalar(text(f"SELECT count(*) FROM {tablo} WHERE isletme_id = :i"), degerler)
        else:
            sayi = con.execute(text(f"UPDATE {tablo} SET {set_ifadesi} WHERE isletme_id = :i"), degerler).rowcount
        setattr(s, alan, sayi)


def _giderleri_tasi(con, s: IsletmeTazeleme, kuru: bool) -> None:
    aylar = list(con.scalars(text("SELECT DISTINCT ay FROM isletme_giderleri WHERE isletme_id = :i"),
                             {"i": s.isletme_id}))
    eklenecek, silinecek = gider_penceresi(aylar, s.bugun)
    s.eklenen_gider_ayi, s.silinen_gider_ayi = eklenecek, silinecek
    if kuru or not eklenecek:
        return
    en_son = max(aylar)
    for ay in eklenecek:                 # yönetici bağlamında aktif_isletme() yok: isletme_id açıkça verilir
        con.execute(text("INSERT INTO isletme_giderleri (isletme_id, ay, kategori, tutar, aciklama) "
                         "SELECT isletme_id, :yeni, kategori, tutar, aciklama FROM isletme_giderleri "
                         "WHERE isletme_id = :i AND ay = :son"),
                    {"i": s.isletme_id, "yeni": ay, "son": en_son})
    con.execute(text("DELETE FROM isletme_giderleri WHERE isletme_id = :i AND ay = ANY(:aylar)"),
                {"i": s.isletme_id, "aylar": silinecek})


def _riski_hesapla(uygulama: Engine, s: IsletmeTazeleme, kuru: bool) -> None:
    """Commit'ten sonra, uygulama rolüyle ve kiracı bağlamında (RLS). Bugün için kayıt varsa atlanır."""
    from database import SessionLocal
    from servisler.yenileme_servisi import YetersizVeri, yenileme_hesapla

    with SessionLocal(bind=uygulama) as db:              # after_begin olayı kiracı bağlamını ayarlar
        db.info["isletme_id"] = s.isletme_id
        aktif, son_hesap = db.execute(text(
            "SELECT (SELECT count(*) FROM musteri_paketleri WHERE durum = 'aktif'), "
            "(SELECT max(hesaplama_tarihi) FROM yenileme_riskleri)")).one()
        if not aktif:
            s.risk_notu = "aktif paket yok"
            return
        if son_hesap is not None and son_hesap >= s.bugun:
            s.risk_notu = "zaten bugün"
            return
        if kuru:
            s.risk_notu = f"hesaplanacak (son: {son_hesap})"
            return
        db.rollback()                                    # okuma işlemini kapat; hesap kendi işleminde
        try:
            s.risk_satiri = yenileme_hesapla(db, s.bugun)
            s.risk_notu = f"{s.risk_satiri} paket hesaplandı"
        except YetersizVeri:
            db.rollback()
            s.risk_notu = "yetersiz veri"


def tazele(yonetici: Engine, uygulama: Engine, *, bugun: date | None = None, kuru: bool = False,
           ilerleme=print) -> list[IsletmeTazeleme]:
    """[DEMO] işletmelerin verisini bugüne kaydırır (K11–K15). kuru=True: hiçbir şey yazılmaz, yalnızca rapor."""
    sonuclar: list[IsletmeTazeleme] = []
    with yonetici.connect() as con:
        islem = con.begin()
        try:
            con.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": KILIT_ANAHTARI})
            isletmeler = con.execute(
                text("SELECT isletme_id, ad, saat_dilimi FROM isletmeler WHERE starts_with(ad, :o) ORDER BY ad"),
                {"o": DEMO_ONEK},
            ).all()
            for isletme_id, ad, dilim in isletmeler:
                basla = time.perf_counter()
                yerel_bugun = bugun or datetime.now(ZoneInfo(dilim)).date()
                son_gun = con.scalar(
                    text("SELECT max((ziyaret_zamani AT TIME ZONE :tz)::date) FROM ziyaretler WHERE isletme_id = :i"),
                    {"tz": dilim, "i": isletme_id})
                s = IsletmeTazeleme(isletme_id=isletme_id, ad=ad, kaydirma_gun=kaydirma_gunu(son_gun, yerel_bugun),
                                    bugun=yerel_bugun)
                if s.kaydirma_gun > 0:
                    _kaydir(con, s, kuru)
                _giderleri_tasi(con, s, kuru)
                s.sure_sn = time.perf_counter() - basla
                sonuclar.append(s)

            if not kuru and sonuclar:
                silinen = con.execute(
                    text("DELETE FROM denetim_kayitlari WHERE isletme_id = ANY(:idler) AND zaman = now() "
                         "RETURNING isletme_id"),
                    {"idler": [s.isletme_id for s in sonuclar]},
                ).scalars().all()
                for s in sonuclar:
                    s.silinen_denetim = sum(1 for i in silinen if i == s.isletme_id)
        except BaseException:
            islem.rollback()
            raise
        if kuru:
            islem.rollback()
        else:
            islem.commit()

    for s in sonuclar:
        basla = time.perf_counter()
        _riski_hesapla(uygulama, s, kuru)
        s.sure_sn += time.perf_counter() - basla
        ilerleme(_satir(s, kuru))
    return sonuclar


def _ay_listesi(aylar: list[date]) -> str:
    return ",".join(a.strftime("%Y-%m") for a in aylar) or "-"


def _satir(s: IsletmeTazeleme, kuru: bool) -> str:
    fiil = "kayacak" if kuru else "kaydı"
    sayilar = (f"ziyaret {s.ziyaret}, paket {s.paket}, müşteri {s.musteri}, izin {s.izin} {fiil}"
               if s.kaydirma_gun > 0 else "tarihler aynı")
    return (f"  {s.ad:<31} bugün {s.bugun}  d = {s.kaydirma_gun:>3}  {sayilar}; "
            f"gider ekle {_ay_listesi(s.eklenen_gider_ayi)} sil {_ay_listesi(s.silinen_gider_ayi)}; "
            f"denetim silindi {s.silinen_denetim}; risk: {s.risk_notu}; {s.sure_sn:.1f} sn")


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser(prog="python -m sentetik.demo_tazele", description="Demo verisini bugüne kaydır")
    a.add_argument("--veritabani", required=True, help="hedef veritabanı; '_demo' ile bitmeli")
    a.add_argument("--kuru", action="store_true", help="hiçbir şey yazma; yalnızca ne yapılacağını raporla")
    arg = a.parse_args(argv)
    try:
        demo_veritabani_dogrula(arg.veritabani)          # bağlantıdan ÖNCE
    except DemoDisiVeritabani as e:
        raise SystemExit(f"HATA: {e}")

    yonetici_url, uygulama_url = baglanti_adresleri(arg.veritabani)
    yonetici, uygulama = create_engine(yonetici_url), create_engine(uygulama_url)
    try:
        print(f"{arg.veritabani}: demo tazeleme{' (KURU: hiçbir şey yazılmaz)' if arg.kuru else ''}", flush=True)
        sonuclar = tazele(yonetici, uygulama, kuru=arg.kuru)
        print(f"{len(sonuclar)} [DEMO] işletme işlendi.")
    finally:
        yonetici.dispose()
        uygulama.dispose()


if __name__ == "__main__":
    main()
