"""Sentetik veri üreticisi (saf Python + numpy; veritabanına dokunmaz).

Üretim süreci, BG/NBD modelinin varsayımlarıyla BİREBİR aynıdır. Böylece ileride yazılacak
modellerin gizli parametreleri geri bulup bulamadığı test edilebilir ("gerçek değerler" bilinir).

Her müşteri için:
  1. λ ~ Gamma(r, α)        günlük geliş hızı
  2. p ~ Beta(a, b)         her tekrar ziyaretten sonra kaybolma olasılığı
  3. t0 ~ Uniform(0, T)     ilk ziyaret (müşterinin edinildiği an)
  4. Ziyaretler arası süre ~ Üstel(λ)   (yani ziyaret sayısı Poisson süreci)
  5. Her TEKRAR ziyaretten hemen sonra, p olasılıkla müşteri kalıcı olarak kaybolur (churn).

Harcama tarafı: her müşterinin gizli bir "harcama eğilimi" (Gamma, ortalama 1) ve kişisel hizmet
tercihleri (Dirichlet) vardır. Sepet = 1 ana hizmet + eğilime bağlı olasılıkla ek hizmetler.
Harcama ve sıklık birbirinden bağımsızdır (Gamma-Gamma modelinin varsayımı).
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from sentetik.katalog import ERKEK_ADLARI, KADIN_ADLARI, PROFILLER, SOYADLARI, SektorProfili

KAYNAK_ETIKETI = "sentetik:v1"
SAAT_DILIMI = ZoneInfo("Europe/Istanbul")
_ODEME = ("kart", "nakit", "havale")
_ODEME_OLASILIK = (0.70, 0.25, 0.05)
_TR_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


@dataclass(frozen=True)
class UretimAyarlari:
    referans: date                      # "bugün": verinin bittiği gün
    musteri_sayisi: int = 400           # her işletme için
    gecmis_gun: int = 730               # veri penceresi (T)
    sektorler: tuple[str, ...] = tuple(PROFILLER)
    tohum: int = 42
    aylik_enflasyon: float = 0.0        # >0: geçmişteki fiyatlar daha düşük
    gelmedi_orani: float = 0.03         # tamamlanan ziyaret başına "gelmedi" kaydı olasılığı
    izin_orani: float = 0.65            # WhatsApp iletişim izni veren müşteri oranı
    indirim_orani: float = 0.05         # ana hizmette %10 indirim olasılığı


@dataclass(frozen=True)
class GercekDeger:
    """Modellerin göremediği, sadece değerlendirme için saklanan gerçek durum."""
    musteri_id: uuid.UUID
    sektor: str
    lambda_gunluk: float
    p_birakma: float
    harcama_egilimi: float
    edinim_zamani: datetime
    olum_zamani: datetime | None        # None = referans tarihinde hâlâ aktif
    tamamlanan_ziyaret: int

    @property
    def canli_mi(self) -> bool:
        return self.olum_zamani is None


@dataclass
class IsletmeVerisi:
    profil: SektorProfili
    hizmetler: list[dict] = field(default_factory=list)
    musteriler: list[dict] = field(default_factory=list)
    izinler: list[dict] = field(default_factory=list)
    ziyaretler: list[dict] = field(default_factory=list)
    kalemler: list[dict] = field(default_factory=list)
    gercek: list[GercekDeger] = field(default_factory=list)


@dataclass
class SentetikVeri:
    ayarlar: UretimAyarlari
    isletmeler: list[IsletmeVerisi]


# ---------------------------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------------------------
def _uuid(rng: np.random.Generator) -> uuid.UUID:
    """Tohuma bağlı (tekrarlanabilir) UUID4."""
    return uuid.UUID(bytes=rng.bytes(16), version=4)


def _fiyat(liste: float, t_gun: float, T: float, aylik_enflasyon: float) -> float:
    """Referans tarihindeki liste fiyatından, t anındaki fiyatı geri hesaplar (10 TL'ye yuvarlı)."""
    ay_farki = (T - t_gun) / 30.0
    ham = liste / (1 + aylik_enflasyon) ** ay_farki
    return max(10.0, round(ham / 10) * 10)


class _Takvim:
    """Sürekli zamanı (gün cinsinden t) işletmenin çalışma gün/saatine yerleştirir."""

    def __init__(self, profil: SektorProfili, baslangic: date, referans: date, rng: np.random.Generator):
        self.profil, self.baslangic, self.referans, self.rng = profil, baslangic, referans, rng

    def zaman(self, t_gun: float) -> datetime | None:
        gun = self.baslangic + timedelta(days=int(t_gun))
        while gun.weekday() in self.profil.kapali_gunler:
            gun += timedelta(days=1)
        if gun > self.referans:
            return None
        acilis, kapanis = self.profil.calisma_saatleri
        saat = int(self.rng.integers(acilis, kapanis))
        dakika = int(self.rng.choice((0, 15, 30, 45)))
        return datetime(gun.year, gun.month, gun.day, saat, dakika, tzinfo=SAAT_DILIMI)


def _benzersiz_telefon(rng: np.random.Generator, kullanilan: set[str]) -> str:
    while True:
        numara = f"+905{int(rng.integers(30, 56))}{int(rng.integers(0, 10_000_000)):07d}"
        if numara not in kullanilan:
            kullanilan.add(numara)
            return numara


# ---------------------------------------------------------------------------------------------
# Çekirdek: tek müşterinin yaşam öyküsü (BG/NBD süreci)
# ---------------------------------------------------------------------------------------------
def ziyaret_zamanlarini_uret(
    lam: float, p: float, t0: float, T: float, rng: np.random.Generator
) -> tuple[list[float], float | None]:
    """Tamamlanan ziyaret zamanlarını (gün) ve varsa kaybolma anını döndürür.

    İlk ziyaretten sonra kaybolma yoktur (BG/NBD varsayımı); kaybolma yalnızca tekrar ziyaretlerden
    hemen sonra, p olasılıkla gerçekleşir. Kaybolma anı = o son ziyaretin zamanı.
    """
    zamanlar = [t0]
    t = t0
    while True:
        t += rng.exponential(1.0 / lam)
        if t >= T:
            return zamanlar, None
        zamanlar.append(t)
        if rng.random() < p:
            return zamanlar, t


def _isletme_uret(profil: SektorProfili, ay: UretimAyarlari, rng: np.random.Generator) -> IsletmeVerisi:
    veri = IsletmeVerisi(profil=profil)
    T = float(ay.gecmis_gun)
    baslangic = ay.referans - timedelta(days=ay.gecmis_gun)
    takvim = _Takvim(profil, baslangic, ay.referans, rng)

    # --- Hizmet kataloğu
    hizmet_idleri = []
    for h in profil.hizmetler:
        hid = _uuid(rng)
        hizmet_idleri.append(hid)
        veri.hizmetler.append({
            "hizmet_id": hid, "ad": h.ad, "kategori": h.kategori,
            "liste_fiyati": h.fiyat, "sure_dk": h.sure_dk,
        })
    ana = [i for i, h in enumerate(profil.hizmetler) if h.ana_mi]
    ek = [i for i, h in enumerate(profil.hizmetler) if not h.ana_mi]
    ana_agirlik = np.array([profil.hizmetler[i].agirlik for i in ana])

    telefonlar: set[str] = set()
    ziyaret_no = 0

    for m_no in range(ay.musteri_sayisi):
        # --- Gizli parametreler
        lam = min(float(rng.gamma(profil.r, 1.0 / profil.alfa)), 1.0)   # günde en fazla 1 geliş ortalaması
        p = float(rng.beta(profil.beta_a, profil.beta_b))
        egilim = float(rng.gamma(4.0, 0.25))                            # ortalama 1, harcama çarpanı
        tercih = rng.dirichlet(ana_agirlik * 2.0)                       # kişisel favori hizmetler
        t0 = float(rng.uniform(0, T))

        zamanlar, olum_t = ziyaret_zamanlarini_uret(lam, p, t0, T, rng)
        takvim_zamanlari = [z for z in (takvim.zaman(t) for t in zamanlar) if z is not None]
        if not takvim_zamanlari:          # ilk ziyaret kapalı gün kayması ile pencereden taştı
            continue

        # --- Müşteri kartı
        kadin = rng.random() < profil.kadin_orani
        ad = str(rng.choice(KADIN_ADLARI if kadin else ERKEK_ADLARI))
        soyad = str(rng.choice(SOYADLARI))
        mid = _uuid(rng)
        edinim = takvim_zamanlari[0]
        eposta = None
        if rng.random() < 0.35:
            eposta = f"{ad.translate(_TR_ASCII).lower()}.{soyad.translate(_TR_ASCII).lower()}{int(rng.integers(1, 999))}@example.com"
        veri.musteriler.append({
            "musteri_id": mid, "ad_soyad": f"{ad} {soyad}",
            "telefon_e164": _benzersiz_telefon(rng, telefonlar), "eposta": eposta,
            "kaynak": "entegrasyon", "dis_kaynak": KAYNAK_ETIKETI, "dis_kimlik": f"M{m_no:05d}",
            "olusturma_zamani": edinim, "guncelleme_zamani": edinim,
        })

        # --- İletişim izni (KVKK): verildi, bazen sonradan geri çekildi
        if rng.random() < ay.izin_orani:
            veri.izinler.append({"musteri_id": mid, "kanal": "whatsapp", "durum": "verildi",
                                 "kaynak": "yazili_form", "kayit_zamani": edinim})
            if rng.random() < 0.05:
                geri = edinim + timedelta(days=float(rng.uniform(1, max(2.0, (T - t0)))))
                if geri.date() <= ay.referans:
                    veri.izinler.append({"musteri_id": mid, "kanal": "whatsapp", "durum": "geri_cekildi",
                                         "kaynak": "yazili_form", "kayit_zamani": geri})

        # --- Ziyaretler ve sepetler
        onceki = None
        for t, zaman in zip(zamanlar, takvim_zamanlari):
            if onceki is not None and rng.random() < ay.gelmedi_orani:
                gelmedi = zaman - timedelta(days=int(rng.integers(1, 4)))
                if gelmedi > onceki:
                    ziyaret_no += 1
                    veri.ziyaretler.append({
                        "ziyaret_id": _uuid(rng), "musteri_id": mid, "ziyaret_zamani": gelmedi,
                        "durum": "gelmedi", "toplam_tutar": 0, "odeme_yontemi": None,
                        "kaynak": "entegrasyon", "dis_kaynak": KAYNAK_ETIKETI, "dis_kimlik": f"Z{ziyaret_no:06d}",
                    })

            zid = _uuid(rng)
            secilen = [int(rng.choice(ana, p=tercih))]
            secilen += [i for i in ek if rng.random() < min(0.9, profil.hizmetler[i].agirlik * egilim)]
            toplam = 0.0
            for sira, i in enumerate(secilen):
                birim = _fiyat(profil.hizmetler[i].fiyat, t, T, ay.aylik_enflasyon)
                indirim = round(birim * 0.10) if sira == 0 and rng.random() < ay.indirim_orani else 0
                toplam += birim - indirim
                veri.kalemler.append({
                    "kalem_id": _uuid(rng), "ziyaret_id": zid, "hizmet_id": hizmet_idleri[i],
                    "adet": 1, "birim_fiyat": birim, "indirim_tutari": indirim,
                })
            ziyaret_no += 1
            veri.ziyaretler.append({
                "ziyaret_id": zid, "musteri_id": mid, "ziyaret_zamani": zaman, "durum": "tamamlandi",
                "toplam_tutar": toplam,
                "odeme_yontemi": str(rng.choice(_ODEME, p=_ODEME_OLASILIK)),
                "kaynak": "entegrasyon", "dis_kaynak": KAYNAK_ETIKETI, "dis_kimlik": f"Z{ziyaret_no:06d}",
            })
            onceki = zaman

        olum = takvim.zaman(olum_t) if olum_t is not None else None
        if olum_t is not None and olum is None:      # kaybolma anı pencere sonuna kaydıysa
            olum = takvim_zamanlari[-1]
        veri.gercek.append(GercekDeger(
            musteri_id=mid, sektor=profil.sektor, lambda_gunluk=lam, p_birakma=p,
            harcama_egilimi=egilim, edinim_zamani=edinim, olum_zamani=olum,
            tamamlanan_ziyaret=len(takvim_zamanlari),
        ))

    return veri


def uret(ayarlar: UretimAyarlari) -> SentetikVeri:
    """Ayarlara göre tüm işletmelerin verisini üretir. Aynı tohum => birebir aynı veri."""
    rng = np.random.default_rng(ayarlar.tohum)
    isletmeler = [_isletme_uret(PROFILLER[s], ayarlar, rng) for s in ayarlar.sektorler]
    return SentetikVeri(ayarlar=ayarlar, isletmeler=isletmeler)
