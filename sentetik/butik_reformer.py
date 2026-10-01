"""İkinci Faz 0 demosu: "[DEMO] Butik Reformer" (yalnızca _demo veritabanı; mevcut demoya dokunmaz).

    python -m sentetik.butik_reformer --sadece-uret                     # veritabanına dokunmadan aylık özet
    python -m sentetik.butik_reformer --veritabani panosu_demo           # üret ve yükle (bir kez)

S6 kalıbı (takvim günleriyle): paket karışımı ve fiyatları S6'dan (1 Aylık %45 2.500, 3 Aylık %25 6.000, 6 Aylık %15
10.000, 12 Giriş %15 800 TL; giriş paketi 60 gün). Her üye ilk ziyaretinde paket alır; düzenli aralıklarla gelir
(Gamma k = 8); bırakma MBG/NBD tarzı, ilk ziyaret dahil her ziyaretten sonra p ile; paket bittiğinde hayattaysa
YENILEME_ORANI ile aynı türü yeniler, yenilemeyen üyenin ziyaretleri biter. Durağan bir üye kitlesi için simülasyon
ISINMA_GUN önce başlar; yalnızca son 18 ayın (PENCERE_BAS..bugün) ziyaretleri ve bu dönemle kesişen paketler yüklenir.
Giriş (check-in) ziyaretlerinin tutarı 0'dır (paket geliri çift sayılmaz). Her ay için giderler (HİPOTEZ) yüklenir.

Hedef (proje sahibi): tipik bir ayda kâr, gerçek gelirin %10–25'i. Yalnızca bu dosyadaki üretici parametreleriyle
sağlanır; modellere dokunulmaz.
"""

import argparse
import calendar
import statistics
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import create_engine, insert, text

from backtest.senaryolar import S6_GIRIS_SON_KULLANMA, S6_PAKETLER
from models import Musteri, MusteriPaketi, Ziyaret
from sentetik.katalog import ERKEK_ADLARI, KADIN_ADLARI, SOYADLARI
from sentetik.uretici import KAYNAK_ETIKETI, _benzersiz_telefon, _uuid
from sentetik.yukleyici import DemoDisiVeritabani, _demo_sahibi, baglanti_adresleri
from servisler import gelir as g

ISLETME_ADI = "[DEMO] Butik Reformer"
SEKTOR = "spor_salonu"
SAAT_DILIMI = ZoneInfo("Europe/Istanbul")
BUGUN = date(2026, 10, 1)
PENCERE_BAS = date(2025, 4, 1)                 # son 18 ay: Nisan 2025 – Eylül 2026
ISINMA_GUN = 365

# Her ay için giderler (HİPOTEZ), TL
AYLIK_GIDER = {"kira": Decimal("40000.00"), "personel": Decimal("70000.00"), "faturalar": Decimal("8000.00"),
               "diger": Decimal("6000.00")}


@dataclass(frozen=True)
class Parametreler:
    """Üretici parametreleri (kâr hedefi bunlarla ayarlanır)."""
    baslangic_uye: int = 85                    # ısınma başındaki üye sayısı (ilk 30 güne yayılır)
    aylik_yeni_uye: float = 4.0                # Poisson geliş hızı (üye / 30 gün)
    ort_aralik_gun: float = 3.5                # μ_i ~ Gamma(şekil 3, bu ortalama); haftada ~2 ders
    birakma_a: float = 1.0                     # p ~ Beta(a, b): ziyaret başına bırakma
    birakma_b: float = 399.0
    yenileme_orani: float = 0.95               # paket bittiğinde hayattaysa yenileme olasılığı
    kadin_orani: float = 0.85
    izin_orani: float = 0.70                   # WhatsApp izni veren üye oranı
    tohum: int = 2026


@dataclass
class ButikVerisi:
    musteriler: list[dict] = field(default_factory=list)
    izinler: list[dict] = field(default_factory=list)
    ziyaretler: list[dict] = field(default_factory=list)
    paketler: list[dict] = field(default_factory=list)


def _uye_simule(t0: date, tur_no: int, prm: Parametreler, rng: np.random.Generator) -> tuple[list[date], list[dict]]:
    """Bir üyenin ziyaret günleri ve paket zinciri (bugüne kadar). Ziyaret günleri son paketin bitişinde kesilir."""
    ad, tur, _, sure, hak, fiyat = S6_PAKETLER[tur_no]
    mu = rng.gamma(3.0, prm.ort_aralik_gun / 3.0)
    p = rng.beta(prm.birakma_a, prm.birakma_b)

    gunler, t, olum = [], 0.0, None             # t: t0'dan itibaren gün
    while True:
        gun = t0 + timedelta(days=int(t))
        if gun >= BUGUN:
            break
        gunler.append(gun)
        if rng.random() < p:                    # MBG/NBD: ilk ziyaret dahil her ziyaretten sonra
            olum = gun
            break
        t += rng.gamma(8.0, mu / 8.0)

    paketler, baslangic = [], t0
    son_kullanma = timedelta(days=int(S6_GIRIS_SON_KULLANMA))
    while True:
        if tur == "sure":
            bitis = baslangic + timedelta(days=int(sure))
            kayit_bitis, aktif = bitis, bitis >= BUGUN
        else:
            kayit_bitis = baslangic + son_kullanma
            donem = [d for d in gunler if baslangic <= d <= kayit_bitis][:hak]
            if len(donem) == hak and donem[-1] < BUGUN:
                bitis, aktif = donem[-1], False
            else:
                bitis, aktif = kayit_bitis, kayit_bitis >= BUGUN
        paketler.append({"tur": tur, "ad": ad, "baslangic_tarihi": baslangic, "bitis_tarihi": kayit_bitis,
                         "giris_hakki": hak, "ucret": Decimal(fiyat), "durum": "aktif" if aktif else "bitti"})
        if aktif:
            break
        hayatta = olum is None or olum > bitis
        if not (hayatta and rng.random() < prm.yenileme_orani):
            gunler = [d for d in gunler if d <= bitis]
            break
        baslangic = bitis if tur == "sure" else bitis + timedelta(days=1)
    return gunler, paketler


def uret(prm: Parametreler = Parametreler()) -> ButikVerisi:
    rng = np.random.default_rng(prm.tohum)
    bas = PENCERE_BAS - timedelta(days=ISINMA_GUN)
    gelisler = [bas + timedelta(days=int(rng.uniform(0, 30))) for _ in range(prm.baslangic_uye)]
    t = 0.0
    while True:
        t += rng.exponential(30.0 / prm.aylik_yeni_uye)
        gun = bas + timedelta(days=int(t))
        if gun >= BUGUN:
            break
        gelisler.append(gun)

    veri, telefonlar = ButikVerisi(), set()
    oranlar = np.array([pk[2] for pk in S6_PAKETLER])
    for no, t0 in enumerate(sorted(gelisler)):
        gunler, paketler = _uye_simule(t0, int(rng.choice(len(S6_PAKETLER), p=oranlar)), prm, rng)
        paketler = [pk for pk in paketler if pk["bitis_tarihi"] >= PENCERE_BAS]
        gunler = [d for d in gunler if d >= PENCERE_BAS]
        if not paketler:
            continue
        mid = _uuid(rng)
        kadin = rng.random() < prm.kadin_orani
        ad = str(rng.choice(KADIN_ADLARI if kadin else ERKEK_ADLARI))
        kayit = datetime.combine(max(t0, PENCERE_BAS), datetime.min.time(), tzinfo=SAAT_DILIMI).replace(hour=9)
        veri.musteriler.append({"musteri_id": mid, "ad_soyad": f"{ad} {rng.choice(SOYADLARI)}",
                                "telefon_e164": _benzersiz_telefon(rng, telefonlar), "kaynak": "entegrasyon",
                                "dis_kaynak": KAYNAK_ETIKETI, "dis_kimlik": f"BR{no:05d}",
                                "olusturma_zamani": kayit, "guncelleme_zamani": kayit})
        if rng.random() < prm.izin_orani:
            veri.izinler.append({"musteri_id": mid, "kanal": "whatsapp", "durum": "verildi", "kaynak": "yazili_form",
                                 "kayit_zamani": kayit})
        for gun in gunler:
            saat = int(rng.integers(7, 21))
            veri.ziyaretler.append({
                "ziyaret_id": _uuid(rng), "musteri_id": mid, "durum": "tamamlandi", "toplam_tutar": 0,
                "ziyaret_zamani": datetime(gun.year, gun.month, gun.day, saat, int(rng.choice((0, 30))), tzinfo=SAAT_DILIMI),
                "kaynak": "entegrasyon", "dis_kaynak": KAYNAK_ETIKETI, "dis_kimlik": f"BZ{len(veri.ziyaretler):06d}",
            })
        onceki = None
        for pk in paketler:
            pid = _uuid(rng)
            veri.paketler.append({**pk, "paket_id": pid, "musteri_id": mid, "onceki_paket_id": onceki,
                                  "dis_kaynak": KAYNAK_ETIKETI, "dis_kimlik": f"BP{len(veri.paketler):06d}"})
            onceki = pid
    return veri


# ---------------------------------------------------------------------------------------------
# Aylık özet (ürünün gelir kurallarıyla; veritabanı yok)
# ---------------------------------------------------------------------------------------------
@dataclass
class AylikOzet:
    ay: date
    gelir: Decimal
    gider: Decimal
    kar: Decimal
    ort_aktif: float

    @property
    def kar_orani(self) -> float:
        return float(self.kar / self.gelir) if self.gelir else float("nan")


def aylik_ozet(veri: ButikVerisi) -> list[AylikOzet]:
    """Pencere aylarının gerçek geliri (hak edilen), gideri, kârı ve ortalama günlük aktif üyesi."""
    gunler_m: dict[uuid.UUID, list[date]] = defaultdict(list)
    for z in veri.ziyaretler:
        gunler_m[z["musteri_id"]].append(z["ziyaret_zamani"].date())
    paketler = []
    for pk in veri.paketler:
        kullanim = ()
        if pk["tur"] == "giris":
            kullanim = tuple(sorted(d for d in gunler_m[pk["musteri_id"]]
                                    if pk["baslangic_tarihi"] <= d <= pk["bitis_tarihi"]))
        paketler.append((pk["musteri_id"], g.PaketGeliri(pk["tur"], pk["baslangic_tarihi"], pk["bitis_tarihi"],
                                                         pk["giris_hakki"], pk["ucret"], None, kullanim)))
    hak: dict[date, Decimal] = defaultdict(lambda: g.SIFIR)
    for _, p in paketler:
        for gun, tutar in g.hak_edilen(p, BUGUN).items():
            hak[gun] += tutar
    gider = sum(AYLIK_GIDER.values(), Decimal(0))
    ozet, ay = [], PENCERE_BAS
    while ay < BUGUN.replace(day=1):
        n = calendar.monthrange(ay.year, ay.month)[1]
        gunler = [ay + timedelta(days=i) for i in range(n)]
        gelir = sum((hak[d] for d in gunler), g.SIFIR)
        aktif = statistics.mean(len({m for m, p in paketler if g.paket_aktif_mi(p, d)}) for d in gunler)
        ozet.append(AylikOzet(ay=ay, gelir=gelir, gider=gider, kar=gelir - gider, ort_aktif=aktif))
        ay = (ay + timedelta(days=n))
    return ozet


def ozet_yazdir(veri: ButikVerisi) -> list[AylikOzet]:
    ozet = aylik_ozet(veri)
    print(f"{len(veri.musteriler)} üye, {len(veri.ziyaretler)} ziyaret, {len(veri.paketler)} paket "
          f"({sum(p['durum'] == 'aktif' for p in veri.paketler)} aktif)")
    for o in ozet:
        print(f"  {o.ay:%Y-%m}  gelir {o.gelir:>10}  kâr {o.kar:>10}  oran {o.kar_orani:>6.1%}  aktif {o.ort_aktif:5.1f}")
    oranlar = [o.kar_orani for o in ozet]
    print(f"  kâr oranı: medyan {statistics.median(oranlar):.1%}, "
          f"%10–25 aralığında {sum(0.10 <= r <= 0.25 for r in oranlar)}/{len(oranlar)} ay")
    return ozet


# ---------------------------------------------------------------------------------------------
# Yükleme (yalnızca _demo)
# ---------------------------------------------------------------------------------------------
class ButikZatenVar(RuntimeError):
    pass


def yukle(veri: ButikVerisi, veritabani: str, ilerleme=print) -> uuid.UUID:
    """İşletmeyi, üyeleri, izinleri, ziyaretleri, paketleri ve aylık giderleri tek işlemde yükler (panosu_app, RLS)."""
    yonetici_url, uygulama_url = baglanti_adresleri(veritabani)     # ad doğrulanmadan bağlantı yok
    yonetici, uygulama = create_engine(yonetici_url), create_engine(uygulama_url)
    try:
        with yonetici.connect() as con:
            if con.scalar(text("SELECT count(*) FROM isletmeler WHERE ad = :a"), {"a": ISLETME_ADI}):
                raise ButikZatenVar(f"{ISLETME_ADI} zaten var; yeniden yüklenmez.")
        sahip = _demo_sahibi(yonetici)
        with uygulama.begin() as con:
            con.execute(text("SELECT set_config('app.kullanici_id', :u, true)"), {"u": str(sahip)})
            iid = con.execute(text("SELECT isletme_olustur(:ad, :u, :s)"),
                              {"ad": ISLETME_ADI, "u": sahip, "s": SEKTOR}).scalar_one()
            con.execute(insert(Musteri.__table__), veri.musteriler)          # isletme_id: aktif_isletme()
            if veri.izinler:
                con.execute(text("INSERT INTO musteri_izinleri (musteri_id, kanal, durum, kaynak, kayit_zamani, "
                                 "kaydeden_kullanici_id) VALUES (:musteri_id, :kanal, :durum, :kaynak, :kayit_zamani, :s)"),
                            [{**i, "s": sahip} for i in veri.izinler])
            con.execute(insert(Ziyaret.__table__), veri.ziyaretler)
            con.execute(insert(MusteriPaketi.__table__), veri.paketler)
            aylar, ay = [], PENCERE_BAS
            while ay <= BUGUN:
                aylar.append(ay)
                ay = (ay + timedelta(days=32)).replace(day=1)
            con.execute(text("INSERT INTO isletme_giderleri (ay, kategori, tutar, aciklama) "
                             "VALUES (:ay, :k, :t, 'Demo gideri (HİPOTEZ)')"),
                        [{"ay": a, "k": k, "t": t} for a in aylar for k, t in AYLIK_GIDER.items()])
        ilerleme(f"{ISLETME_ADI} yüklendi: {iid} | {len(veri.musteriler)} üye, {len(veri.ziyaretler)} ziyaret, "
                 f"{len(veri.paketler)} paket, {len(aylar)} ay gider")
        return iid
    finally:
        yonetici.dispose()
        uygulama.dispose()


def main() -> None:
    a = argparse.ArgumentParser(prog="python -m sentetik.butik_reformer", description=f"{ISLETME_ADI} demosu")
    a.add_argument("--veritabani", help="hedef veritabanı; '_demo' ile bitmeli")
    a.add_argument("--sadece-uret", action="store_true", help="veritabanına yazma, yalnızca aylık özet")
    arg = a.parse_args()
    if not arg.sadece_uret and not arg.veritabani:
        a.error("yükleme için --veritabani zorunludur; yalnızca üretmek için --sadece-uret")
    veri = uret()
    ozet_yazdir(veri)
    if arg.sadece_uret:
        return
    try:
        yukle(veri, arg.veritabani)
    except (DemoDisiVeritabani, ButikZatenVar) as hata:
        raise SystemExit(f"HATA: {hata}")


if __name__ == "__main__":
    main()
