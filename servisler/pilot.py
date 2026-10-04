"""Pilot scoring and retrospective validation without a database (pilot step, K64-K71,
`docs/adim-pilot-tasarim.md`).

Pure core: takes the package and check-in records prepared by `servisler.ice_aktarma` (same reading, mapping and
whitelist rules as the import) and works only in memory. No database, no FastAPI, no config; the firm can run it
on its own machine.

  skorla   : P(active now), P(renewal), Riskteki Para and the "why risky" sentence for given packages on a given day;
             the same computation as `servisler.yenileme_servisi.yenileme_hesapla` (equivalence test in
             tests/test_pilot.py), with check-ins counted only up to that day.
  dogrula  : K40 (4b-2) time-split test with rolling cut-offs (K65-K67). Cut-offs C = L - 90, L - 180, ... (data
             day L, at most 4, each with at least 180 days of history; the newest one always). At each C the model
             sees only check-ins up to C; packages that are the member's latest package at C and end in
             (C, C + 60] are scored; outcome = a new package starting in (C, end + 30]. 60 + 30 = 90, so every
             outcome is observable by L, and the windows of different cut-offs do not overlap.
  guncel   : today's list on day L (active packages), for the firm to map back to names on its side.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

import numpy as np

from analitik import mbgnbd
from analitik.aciklama import Aciklama, neden_riskli
from analitik.ozellikler import ozellik_cikar
from analitik.riskteki_para import yenileme_riskteki_para
from analitik.yenileme import MODEL_VERSIYONU, yenileme_olasiligi
from backtest.metrikler import auc as roc_auc
from servisler.ice_aktarma import GirisKaydi, PaketKaydi

GERI_GUN = 90                 # H (K40): newest cut-off = data day - 90
KESIM_ARALIGI_GUN = 90        # earlier cut-offs every 90 days (their evaluation windows do not overlap)
AZAMI_KESIM = 4
MIN_GECMIS_GUN = 180          # an earlier cut-off needs this much history before it
UFUK_GUN = 60                 # packages ending within 60 days of the cut-off (same as backtest S6)
YENILEME_PAYI_GUN = 30        # a new package up to 30 days after the end still counts as renewal
KURAL_PENCERE_GUN = 21        # baseline rule (backtest S6): at most 1 check-in in the last 21 days -> will not renew
ILK_SIRA = 10                 # "top 10 riskiest" hit rate
DILIM_SAYISI = 5              # calibration: 5 equal-count groups
BOOTSTRAP_SAYISI = 2_000
BOOTSTRAP_TOHUMU = 2026       # fixed seed: same files -> same report
AZ_ORNEK = 30                 # fewer evaluated packages than this -> report warns that results are uncertain
KISA_GECMIS_GUN = 365         # history shorter than this before the cut-off -> warning

_GUN_SANIYE = 86_400.0
_DORT_HANE = Decimal("0.0001")


class YetersizVeri(Exception):
    """Not enough check-in history to fit the model or to validate."""


@dataclass(frozen=True)
class Skor:
    gun: date                         # scoring day (a cut-off, or the data day)
    paket: PaketKaydi
    p_hayatta_simdi: Decimal          # 4 decimals, as stored in yenileme_riskleri
    p_yenileme: Decimal
    riskteki_para: Decimal
    kalan_gun: int | None
    kalan_giris: int | None
    son_21_gun_giris: int             # check-ins in (day - 21, day]; used by the baseline rule
    aciklama: Aciklama


def _olasilik(deger: float) -> Decimal:
    return Decimal(repr(deger)).quantize(_DORT_HANE, rounding=ROUND_HALF_UP)


def ziyaret_gunleri(girisler: list[GirisKaydi], dilim: ZoneInfo) -> dict[str, list[datetime]]:
    """Completed check-ins per member (UTC datetimes, sorted)."""
    sonuc: dict[str, list[datetime]] = defaultdict(list)
    for g in girisler:
        if g.durum == "tamamlandi":
            sonuc[g.uye_kimlik].append(g.ziyaret_zamani)
    return {u: sorted(z) for u, z in sonuc.items()}


def veri_gunu(ziyaretler: dict[str, list[datetime]], dilim: ZoneInfo) -> date:
    """L: local date of the latest completed check-in (the extraction day; real 'today' is not used, K65)."""
    if not ziyaretler:
        raise YetersizVeri("Dosyada tamamlanmış giriş yok")
    return max(z[-1] for z in ziyaretler.values()).astimezone(dilim).date()


def skorla(ziyaretler: dict[str, list[datetime]], paketler: list[PaketKaydi], gun: date,
           dilim: ZoneInfo) -> list[Skor]:
    """Scores `paketler` on `gun` using only check-ins up to the end of that local day."""
    son = datetime.combine(gun + timedelta(days=1), time(0), tzinfo=dilim)
    goreli = {u: np.array([(z - son).total_seconds() / _GUN_SANIYE for z in zs if z < son])
              for u, zs in ziyaretler.items()}
    goreli = {u: z for u, z in goreli.items() if len(z)}
    if not goreli:
        raise YetersizVeri(f"{gun} tarihine kadar tamamlanmış giriş yok")
    uyeler = list(goreli)
    zamanlar = [goreli[u] for u in uyeler]
    oz = ozellik_cikar(zamanlar, zamanlar, 0.0)
    prm = mbgnbd.fit(oz.x, oz.t_x, oz.T)
    sira = {u: i for i, u in enumerate(uyeler)}

    skorlar = []
    for pk in paketler:
        z = goreli.get(pk.uye_kimlik, np.array([]))
        gunler = [(son + timedelta(days=float(t))).astimezone(dilim).date() for t in z]
        if pk.uye_kimlik in sira:
            i = sira[pk.uye_kimlik]
            x, t_x, T = oz.x[i], oz.t_x[i], oz.T[i]
        else:                                            # has a package but never came: acquisition = package start
            x, t_x, T = 0.0, 0.0, max((gun - pk.baslangic_tarihi).days + 1, 1)
        kalan_gun = (pk.bitis_tarihi - gun).days if pk.bitis_tarihi else None
        kalan_giris = None
        if pk.tur == "giris":
            ust = min(pk.bitis_tarihi, gun) if pk.bitis_tarihi else gun
            kullanilan = sum(1 for d in gunler if pk.baslangic_tarihi <= d <= ust)
            kalan_giris = max(0, pk.giris_hakki - kullanilan)
        sonuc = yenileme_olasiligi(prm, x, t_x, T, pencere_gun=kalan_gun, kalan_hak=kalan_giris)
        p_h, p_y = _olasilik(sonuc.p_hayatta_simdi), _olasilik(sonuc.p_yenileme)
        aciklama = neden_riskli(
            p_hayatta_simdi=p_h, p_yenileme=p_y, ziyaret_sayisi=len(gunler),
            ilk_ziyaret=gunler[0] if gunler else None, son_ziyaret=gunler[-1] if gunler else None,
            hesaplama_tarihi=gun, paket_baslangic=pk.baslangic_tarihi, tur=pk.tur,
            kalan_gun=kalan_gun if pk.tur == "sure" else None, kalan_giris=kalan_giris)
        skorlar.append(Skor(
            gun=gun, paket=pk, p_hayatta_simdi=p_h, p_yenileme=p_y,
            riskteki_para=yenileme_riskteki_para(p_y, pk.ucret),
            kalan_gun=kalan_gun if pk.tur == "sure" else None, kalan_giris=kalan_giris,
            son_21_gun_giris=sum(1 for t in z if t > -KURAL_PENCERE_GUN), aciklama=aciklama))
    return skorlar


def _son_paketler(paketler: list[PaketKaydi], gun: date) -> dict[str, PaketKaydi]:
    """Each member's latest non-cancelled package started on or before `gun` (ties: later file row)."""
    son: dict[str, PaketKaydi] = {}
    for pk in sorted(paketler, key=lambda p: (p.baslangic_tarihi, p.satir)):
        if pk.durum != "iptal" and pk.baslangic_tarihi <= gun:
            son[pk.uye_kimlik] = pk
    return son


# ---------------------------------------------------------------------------------------------
# Today's list (K68)
# ---------------------------------------------------------------------------------------------
@dataclass
class GuncelListe:
    gun: date
    skorlar: list[Skor]               # sorted by riskteki_para desc
    donduruldu: int                   # frozen packages left out
    model_versiyonu: str = MODEL_VERSIYONU


def guncel(ziyaretler: dict[str, list[datetime]], paketler: list[PaketKaydi], dilim: ZoneInfo) -> GuncelListe:
    L = veri_gunu(ziyaretler, dilim)
    adaylar = [pk for pk in _son_paketler(paketler, L).values()
               if (pk.bitis_tarihi is None or pk.bitis_tarihi >= L) and pk.durum != "bitti"]
    aktif = [pk for pk in adaylar if pk.durum != "donduruldu"]
    skorlar = sorted(skorla(ziyaretler, aktif, L, dilim),
                     key=lambda s: (-s.riskteki_para, s.p_yenileme, s.paket.uye_kimlik))
    return GuncelListe(gun=L, skorlar=skorlar, donduruldu=len(adaylar) - len(aktif))


# ---------------------------------------------------------------------------------------------
# Retrospective validation (K40 / 4b-2, K65-K67)
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Dilim:
    n: int
    ort_tahmin: float                 # mean predicted P(renewal)
    gercek_oran: float                # observed renewal rate


@dataclass
class Dogrulama:
    veri_gunu: date                   # L
    kesimler: list[date]              # cut-offs, newest first
    ilk_giris: date
    uye_sayisi: int                   # members with at least one completed check-in
    paket_sayisi: int                 # non-cancelled packages in the file
    giris_sayisi: int                 # completed check-ins
    skorlar: list[Skor]               # evaluated packages of all cut-offs, riskiest first
    yeniledi: list[bool]              # aligned with skorlar
    dislanan_bitissiz: int            # entry packages without an end date at a cut-off (no observable end)
    yenileme_orani: float | None
    auc: float | None
    auc_alt: float | None             # 95% bootstrap interval (members resampled)
    auc_ust: float | None
    kural_auc: float | None
    brier: float | None
    dilimler: list[Dilim]
    ilk_sira_birakan: int             # of the ILK_SIRA riskiest, how many did not renew
    ilk_sira_n: int
    tahmini_kayip: Decimal            # sum of Riskteki Para at the cut-offs
    gercek_kayip: Decimal             # sum of prices of packages that were not renewed
    uyarilar: list[str]


def kesimleri_sec(L: date, ilk: date) -> list[date]:
    """Newest first: L - 90 always, then every 90 days back while at least MIN_GECMIS_GUN of history remains."""
    kesimler = [L - timedelta(days=GERI_GUN)]
    while len(kesimler) < AZAMI_KESIM:
        C = kesimler[-1] - timedelta(days=KESIM_ARALIGI_GUN)
        if (C - ilk).days < MIN_GECMIS_GUN:
            break
        kesimler.append(C)
    return kesimler


def _bootstrap_auc(skor: np.ndarray, etiket: np.ndarray, uyeler: list[str]) -> tuple[float | None, float | None]:
    """95% percentile interval; members are resampled with all their packages (a member can appear at several
    cut-offs, so packages are not independent)."""
    _, ters = np.unique(np.array(uyeler), return_inverse=True)
    gruplar = [np.flatnonzero(ters == j) for j in range(ters.max() + 1)]
    rng = np.random.default_rng(BOOTSTRAP_TOHUMU)
    degerler = []
    for _ in range(BOOTSTRAP_SAYISI):
        i = np.concatenate([gruplar[j] for j in rng.integers(0, len(gruplar), len(gruplar))])
        a = roc_auc(skor[i], etiket[i])
        if a is not None:
            degerler.append(a)
    if not degerler:
        return None, None
    return float(np.percentile(degerler, 2.5)), float(np.percentile(degerler, 97.5))


def dogrula(ziyaretler: dict[str, list[datetime]], paketler: list[PaketKaydi], dilim: ZoneInfo) -> Dogrulama:
    L = veri_gunu(ziyaretler, dilim)
    ilk = min(z[0] for z in ziyaretler.values()).astimezone(dilim).date()
    kesimler = kesimleri_sec(L, ilk)
    uyarilar = []
    if (kesimler[0] - ilk).days < KISA_GECMIS_GUN:
        uyarilar.append(f"Kesim tarihinden önceki geçmiş {(kesimler[0] - ilk).days} gün; en az {KISA_GECMIS_GUN} gün "
                        "önerilir.")
    baslangiclar: dict[str, list[date]] = defaultdict(list)
    for pk in paketler:
        if pk.durum != "iptal":
            baslangiclar[pk.uye_kimlik].append(pk.baslangic_tarihi)

    skorlar, bitissiz = [], set()
    for C in kesimler:
        son = _son_paketler(paketler, C)
        secilen = [pk for pk in son.values()
                   if pk.bitis_tarihi is not None and C < pk.bitis_tarihi <= C + timedelta(days=UFUK_GUN)]
        bitissiz |= {pk.dis_kimlik for pk in son.values() if pk.bitis_tarihi is None}
        if secilen:
            skorlar += skorla(ziyaretler, secilen, C, dilim)
    skorlar.sort(key=lambda s: (s.p_yenileme, -s.riskteki_para, -s.gun.toordinal(), s.paket.uye_kimlik))
    yeniledi = [any(s.gun < b <= s.paket.bitis_tarihi + timedelta(days=YENILEME_PAYI_GUN)
                    for b in baslangiclar[s.paket.uye_kimlik]) for s in skorlar]

    n = len(skorlar)
    y = np.array(yeniledi, dtype=int)
    p = np.array([float(s.p_yenileme) for s in skorlar])
    kural = np.array([0.0 if s.son_21_gun_giris <= 1 else 1.0 for s in skorlar])
    auc = roc_auc(p, y) if n else None
    alt, ust = _bootstrap_auc(p, y, [s.paket.uye_kimlik for s in skorlar]) if auc is not None else (None, None)
    dilimler = []
    if n >= DILIM_SAYISI:
        for parca in np.array_split(np.argsort(p, kind="mergesort"), DILIM_SAYISI):
            dilimler.append(Dilim(len(parca), float(p[parca].mean()), float(y[parca].mean())))
    if n < AZ_ORNEK:
        uyarilar.append(f"Değerlendirilen paket sayısı {n}; {AZ_ORNEK}'un altında sonuçlar çok belirsizdir.")
    k = min(ILK_SIRA, n)
    return Dogrulama(
        veri_gunu=L, kesimler=kesimler, ilk_giris=ilk, uye_sayisi=len(ziyaretler),
        paket_sayisi=sum(1 for pk in paketler if pk.durum != "iptal"),
        giris_sayisi=sum(len(z) for z in ziyaretler.values()),
        skorlar=skorlar, yeniledi=yeniledi, dislanan_bitissiz=len(bitissiz),
        yenileme_orani=float(y.mean()) if n else None, auc=auc, auc_alt=alt, auc_ust=ust,
        kural_auc=roc_auc(kural, y) if n else None,
        brier=float(np.mean((p - y) ** 2)) if n else None, dilimler=dilimler,
        ilk_sira_birakan=int(k - y[:k].sum()), ilk_sira_n=k,
        tahmini_kayip=sum((s.riskteki_para for s in skorlar), Decimal("0.00")),
        gercek_kayip=sum((s.paket.ucret for s, r in zip(skorlar, yeniledi) if not r), Decimal("0.00")),
        uyarilar=uyarilar)
