"""Adım 9b: "neden riskli" açıklaması (veritabanı yok). Proje sahibi kararı, 2026-10-02 (docs/adim-9-tasarim.md).

K6 Riskin iki çarpana ayrılması: P(yenileme) = P(aktif şimdi) × P(sürdürme | aktif).
   p_aktif = p_hayatta_simdi; q = min(p_yenileme / p_aktif, 1) (p_aktif = 0 ise q tanımsız).
   A = −ln p_aktif, B = −ln q; −ln P(yenileme) = A + B; sessizlik_payi = A / (A + B).
   A ≥ B → ana neden sessizlik; B > A → ana neden kalan süre (süre bazlı) / kalan hak (giriş bazlı).
K7 Normal aralık m = (son ziyaret − ilk ziyaret) / (ziyaret sayısı − 1); sessiz gün s = hesaplama günü − son ziyaret;
   kat k = s / m. Aktif üyede s gün hiç gelmeme olasılığı ≈ e^(−k). "Normal aralık" yalnızca en az 4 ziyaret varsa
   söylenir (ortalamanın göreli hatası ≈ 1/√(n−1)).
K9 Sadakat: açıklama yalnızca modelin kullandığı bilgiden (ziyaret sayısı, ilk/son ziyaret, kalan gün/giriş, iki
   olasılık) türetilir; modelde olmayan sinyal yazılmaz. P(yenileme) ≥ 0,80 → "Düzenli geliyor; belirgin bir risk yok."

ln için float kullanılır; dışarı verilen tüm sayılar Decimal'dir.
"""

import math
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from servisler.bicim import ondalik, tarih

DUSUK_RISK_ESIGI = Decimal("0.80")
NORMAL_ARALIK_MIN_ZIYARET = 4
# p_aktif bunun altındaysa ayrıştırma (aktif × sürdürme) gösterilmez: q = p_yenileme / p_aktif, simülasyondaki
# ~2000·p_aktif "aktif" çekilişten tahmin edilir; %5'te ~100 çekiliş, standart hata en fazla ~5 puan (proje sahibi
# kararı, 2026-10-02).
AYRISTIRMA_MIN_P_AKTIF = Decimal("0.05")


@dataclass(frozen=True)
class Aciklama:
    ana_neden: str                       # 'dusuk_risk' | 'hic_gelmedi' | 'az_gecmis' | 'sessizlik' | 'uzun_sure' | 'kalan_hak'
    cumle: str
    p_aktif: Decimal                     # = p_hayatta_simdi
    p_surdurme: Decimal | None           # q, 4 hane; p_aktif = 0 ise None
    sessizlik_payi: Decimal | None       # 0–1, 2 hane; dusuk_risk ve hic_gelmedi'de None
    ziyaret_sayisi: int                  # hesaplama gününe kadarki tamamlanmış ziyaret (ilk dahil)
    sessiz_gun: int | None               # s; hiç ziyaret yoksa None
    normal_aralik_gun: Decimal | None    # m, 1 hane; ziyaret_sayisi < 4 veya m = 0 ise None
    kat: Decimal | None                  # k, 1 hane; m None ise None


def _eksi_ln(deger: Decimal) -> float:
    """−ln(deger); deger = 0 → ∞."""
    return math.inf if deger <= 0 else -math.log(float(deger))


def _yuvarla(deger: Decimal, hane: int) -> Decimal:
    return deger.quantize(Decimal(1).scaleb(-hane), rounding=ROUND_HALF_UP)


def neden_riskli(*, p_hayatta_simdi: Decimal, p_yenileme: Decimal, ziyaret_sayisi: int,
                 ilk_ziyaret: date | None, son_ziyaret: date | None, hesaplama_tarihi: date,
                 paket_baslangic: date, tur: str, kalan_gun: int | None, kalan_giris: int | None) -> Aciklama:
    p_aktif = Decimal(p_hayatta_simdi)
    p_yen = Decimal(p_yenileme)
    q = None if p_aktif <= 0 else min(p_yen / p_aktif, Decimal(1))
    p_surdurme = None if q is None else _yuvarla(q, 4)

    sessiz_gun = None if son_ziyaret is None else (hesaplama_tarihi - son_ziyaret).days
    m = None
    if ziyaret_sayisi >= NORMAL_ARALIK_MIN_ZIYARET and ilk_ziyaret is not None and son_ziyaret is not None:
        m = Decimal((son_ziyaret - ilk_ziyaret).days) / Decimal(ziyaret_sayisi - 1)
        if m == 0:
            m = None
    kat = None if m is None or sessiz_gun is None else _yuvarla(Decimal(sessiz_gun) / m, 1)
    normal_aralik_gun = None if m is None else _yuvarla(m, 1)

    def sonuc(ana_neden: str, cumle: str, sessizlik_payi: Decimal | None) -> Aciklama:
        return Aciklama(ana_neden=ana_neden, cumle=cumle, p_aktif=p_aktif, p_surdurme=p_surdurme,
                        sessizlik_payi=sessizlik_payi, ziyaret_sayisi=ziyaret_sayisi, sessiz_gun=sessiz_gun,
                        normal_aralik_gun=normal_aralik_gun, kat=kat)

    if p_yen >= DUSUK_RISK_ESIGI:
        return sonuc("dusuk_risk", "Düzenli geliyor; belirgin bir risk yok.", None)
    if ziyaret_sayisi == 0:
        gun = (hesaplama_tarihi - paket_baslangic).days
        return sonuc("hic_gelmedi", f"Paketi {tarih(paket_baslangic)} tarihinde aldı, o günden beri hiç gelmedi "
                                    f"({gun} gün).", None)

    a = _eksi_ln(p_aktif)
    b = math.inf if q is None else _eksi_ln(q)      # p_aktif = 0: q tanımsız; A = ∞ zaten A ≥ B'yi sağlar
    if math.isinf(a):
        pay = Decimal(1)                            # A = ∞ (B sonlu ya da ∞) → 1
    elif math.isinf(b):
        pay = Decimal(0)
    else:
        pay = Decimal(str(a / (a + b)))
    sessizlik_payi = _yuvarla(pay, 2)

    if a >= b:
        if m is None:
            son = "son ziyareti hesaplama gününde" if sessiz_gun == 0 else f"son ziyaret {sessiz_gun} gün önce"
            return sonuc("az_gecmis", f"Yalnızca {ziyaret_sayisi} kez geldi; {son}. "
                                      "Geçmiş az, tahmin belirsiz.", sessizlik_payi)
        m_tam = max(int(_yuvarla(m, 0)), 1)
        return sonuc("sessizlik", f"Normalde ~{m_tam} günde bir geliyor; {sessiz_gun} gündür gelmiyor "
                                  f"(normalin {ondalik(kat)} katı).", sessizlik_payi)
    if tur == "giris":
        return sonuc("kalan_hak", f"Şu an düzenli geliyor; risk, kalan {kalan_giris} giriş hakkını kullanırken "
                                  "bırakma ihtimalinden.", sessizlik_payi)
    return sonuc("uzun_sure", f"Şu an düzenli geliyor; risk, paketin bitmesine kalan {kalan_gun} günde bırakma "
                              "ihtimalinden.", sessizlik_payi)
