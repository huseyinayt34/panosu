"""M1: BG/NBD (Fader, Hardie & Lee, 2005, "Counting Your Customers the Easy Way").

    Hayattayken ziyaretler Poisson(λ),             λ ~ Gamma(r, α)   (α: oran)
    Her tekrar ziyaretten sonra bırakma olasılığı p,  p ~ Beta(a, b)

Müşteri başına veri (analitik.ozellikler): x, t_x, T. Zaman birimi: gün.

Log-olabilirlik (makale, denklem 6), A1 = lnΓ(r+x) − lnΓ(r) + r·ln α:
    ln L = A1 + ln[ B(a, b+x)/B(a,b) · (α+T)^−(r+x)
                    + 1{x>0} · B(a+1, b+x−1)/B(a,b) · (α+t_x)^−(r+x) ]

Uyum en büyük sonsal (MAP) ile yapılır (K42–K48, docs/adim-mu-kappa-tasarim.md). Optimizasyon uzayı
θ = (ln m, ln r, logit μ, ln κ); m = r/α (ortalama günlük ziyaret oranı), μ = a/(a+b) (ortalama bırakma olasılığı),
κ = a+b. Veri κ'yı ve küçük veride r'yi zayıf belirler (düz sırt); bu iki yöne zayıf log-normal önsel konur:
ln κ ~ Normal(ln 10, 2²), ln r ~ Normal(ln 30, 2²); m ve μ önselsizdir. L-BFGS-B türevi merkezi farkla alır.
İki başlangıçtan çözülür (varsayılan ve "tek seferlik payı" başlangıcı), amacı küçük olan seçilir.
"""

import math
import warnings
from dataclasses import dataclass

import numpy as np
from scipy.integrate import quad
from scipy.optimize import minimize
from scipy.special import betaln, expit, gammaln, hyp2f1

# Yakınsama bildirilmese de, türevsiz cila toplam log-olabilirliği bundan az iyileştiriyorsa nokta kabul edilir
# (plato: ör. a, b → ∞ sınır çözümü; olabilirlik o yönde istatistiksel olarak anlamsız ölçüde değişir).
PLATO_LL_TOLERANS = 1e-2

# Zayıf önseller (K44); log_onsel bunları çağrı anında okur. SAPMA = math.inf: o yönde önsel yok.
ONSEL_LN_KAPPA_MERKEZ = math.log(10)   # ln κ önselinin merkezi: κ = a+b ≈ 10
ONSEL_LN_KAPPA_SAPMA = 2.0             # ln κ önselinin standart sapması (±2 sapma: κ ≈ 0,18–550)
ONSEL_LN_R_MERKEZ = math.log(30)       # ln r önselinin merkezi: r ≈ 30
ONSEL_LN_R_SAPMA = 2.0                 # ln r önselinin standart sapması (±2 sapma: r ≈ 0,55–1 640)
# BG/NBD ve MBG/NBD MAP'inde L-BFGS-B ayarları (K46): merkezi fark türevi, sıkı göreli amaç toleransı.
MAP_SECENEKLERI = {"jac": "3-point", "options": {"ftol": 1e-12}}
# θ = (ln m, ln r, logit μ, ln κ) sınırları (K48), bu sırayla.
TETA_SINIRLARI = [(-15.0, 10.0), (-10.0, 15.0), (-20.0, 20.0), (-10.0, 15.0)]


@dataclass(frozen=True)
class BGNBDParametreleri:
    r: float
    alfa: float
    a: float
    b: float

    def dizi(self) -> np.ndarray:
        return np.array([self.r, self.alfa, self.a, self.b])


def _diziler(x, t_x, T):
    return (np.asarray(x, dtype=float), np.asarray(t_x, dtype=float), np.asarray(T, dtype=float))


def kanonik_sira(*diziler: np.ndarray) -> tuple[np.ndarray, ...]:
    """Müşteri dizilerini öncelik sırasıyla (ilk dizi birincil anahtar) sözlük sırasına dizer.

    Olabilirlik müşterilerin çoklu kümesinin fonksiyonudur; fit'ler girdiyi bu sıraya dizerek aynı veride, müşteri
    kimlikleri ve okuma sırası ne olursa olsun bit bit aynı parametreyi verir. Eşit satırlar aynı olduğundan bağlar
    sonucu etkilemez. Belirlenimcilik sağlar; tanımlanabilirliği (ör. a,b sırtı) çözmez.
    """
    sira = np.lexsort(diziler[::-1])
    return tuple(d[sira] for d in diziler)


def log_olabilirlik_bireysel(prm: BGNBDParametreleri, x, t_x, T) -> np.ndarray:
    """Her müşterinin log-olabilirlik katkısı."""
    x, t_x, T = _diziler(x, t_x, T)
    r, alfa, a, b = prm.r, prm.alfa, prm.a, prm.b
    a1 = gammaln(r + x) - gammaln(r) + r * np.log(alfa)
    a2 = betaln(a, b + x) - betaln(a, b) - (r + x) * np.log(alfa + T)
    tekrar = x > 0
    # x = 0 iken b + x − 1 ≤ 0 olabilir; o terim kullanılmadığından güvenli bir değerle hesaplanır.
    a3 = np.where(
        tekrar,
        betaln(a + 1, np.where(tekrar, b + x - 1, 1.0)) - betaln(a, b) - (r + x) * np.log(alfa + t_x),
        -np.inf,
    )
    return a1 + np.logaddexp(a2, a3)


def log_olabilirlik(prm: BGNBDParametreleri, x, t_x, T) -> float:
    return float(log_olabilirlik_bireysel(prm, x, t_x, T).sum())


def tetadan_parametre(teta) -> BGNBDParametreleri:
    """θ = (ln m, ln r, logit μ, ln κ) → (r, α, a, b).

    r = e^(ln r), α = r/m, a = κ·expit(logit μ), b = κ·expit(−logit μ).
    """
    ln_m, ln_r, logit_mu, ln_kappa = (float(d) for d in teta)
    r, kappa = float(np.exp(ln_r)), float(np.exp(ln_kappa))
    return BGNBDParametreleri(r=r, alfa=r / float(np.exp(ln_m)), a=kappa * float(expit(logit_mu)),
                              b=kappa * float(expit(-logit_mu)))


def parametreden_teta(prm: BGNBDParametreleri) -> np.ndarray:
    """(r, α, a, b) → θ: ln m = ln r − ln α, ln r, logit μ = ln a − ln b, ln κ = ln(a+b)."""
    return np.array([np.log(prm.r) - np.log(prm.alfa), np.log(prm.r), np.log(prm.a) - np.log(prm.b),
                     np.log(prm.a + prm.b)])


@dataclass(frozen=True)
class Onsel:
    """Independent normal prior on θ = (ln m, ln r, logit μ, ln κ), all four directions (cold start, K81-K82).

    Replaces the weak prior (log_onsel) when a business has too little data; learned from other businesses.
    """
    merkez: tuple[float, float, float, float]
    sapma: tuple[float, float, float, float]

    def log_yogunluk(self, teta) -> float:
        """Log density without the constant."""
        z = (np.asarray(teta, dtype=float) - np.asarray(self.merkez)) / np.asarray(self.sapma)
        return float(-0.5 * np.sum(z * z))


def log_onsel(teta) -> float:
    """Zayıf önselin log yoğunluğu (sabit hariç; K44, K45): yalnız ln κ = θ[3] ve ln r = θ[1]; m ve μ önselsiz."""
    return float(-0.5 * ((teta[3] - ONSEL_LN_KAPPA_MERKEZ) / ONSEL_LN_KAPPA_SAPMA) ** 2
                 - 0.5 * ((teta[1] - ONSEL_LN_R_MERKEZ) / ONSEL_LN_R_SAPMA) ** 2)


def fit(x, t_x, T, baslangic: BGNBDParametreleri | None = None) -> BGNBDParametreleri:
    """(r, α, a, b) MAP: θ uzayında −(log-olabilirlik + log_onsel(θ)) / n en küçüklenir (K45), iki başlangıçtan (K47).

    Girdi önce kanonik sıraya (x, t_x, T) dizilir: aynı veri hangi sırayla gelirse gelsin parametre bit bit aynıdır.
    """
    x, t_x, T = kanonik_sira(*_diziler(x, t_x, T))
    n = len(x)
    if n == 0:
        raise ValueError("BG/NBD uyumu için en az bir müşteri gerekli")
    if baslangic is None:
        baslangic = BGNBDParametreleri(r=1.0, alfa=max(float(np.mean(T)), 1.0), a=1.0, b=1.0)

    def amac(teta):
        deger = -(log_olabilirlik(tetadan_parametre(teta), x, t_x, T) + log_onsel(teta)) / n
        return deger if np.isfinite(deger) else 1e300

    return tetadan_parametre(map_iki_baslangic(amac, parametreden_teta(baslangic), x, n, "BG/NBD"))


def map_iki_baslangic(amac, baslangic_teta: np.ndarray, x: np.ndarray, n: int, ad: str) -> np.ndarray:
    """θ'da iki başlangıçtan MAP (K47); amacı küçük olan çözüm döner.

    B1 verilen başlangıçtır. B2, B1 çözümünün (ln m, ln r)'sini alır; μ'yü tek seferlik payına (x = 0 oranı,
    [0.02, 0.98]'e kırpılmış), ln κ'yı −2'ye koyar: p'nin müşteriler arasında çok dağınık olduğu (bir kısmı hemen
    bırakan) çözüm, B1'den bir sırtla ayrılmış olabilir.
    """
    t1 = log_mle(amac, baslangic_teta, TETA_SINIRLARI, n, ad, MAP_SECENEKLERI)
    pay = min(max(float(np.mean(x == 0)), 0.02), 0.98)
    b2 = np.array([t1[0], t1[1], math.log(pay / (1 - pay)), -2.0])
    t2 = log_mle(amac, b2, TETA_SINIRLARI, n, ad, MAP_SECENEKLERI)
    return t2 if amac(t2) < amac(t1) else t1


def log_mle(amac, baslangic: np.ndarray, sinirlar: list, n: int, ad: str, secenekler: dict | None = None) -> np.ndarray:
    """amac (müşteri başına ortalama negatif log-olabilirlik ya da log-sonsal) L-BFGS-B ile en küçüklenir.

    secenekler L-BFGS-B'ye anahtar sözcük olarak geçer (ör. MAP_SECENEKLERI); verilmezse scipy varsayılanları.
    Olabilirlik bir yönde düzleşirse çizgi araması "ABNORMAL" ile durabilir; o zaman RuntimeWarning verilir ve aynı
    sınırlar içinde Nelder-Mead ile cilalanır. Cila da yakınsamazsa, toplam log-olabilirlik PLATO_LL_TOLERANS'tan az
    iyileştiyse nokta kabul edilir; değilse hata.
    """
    sonuc = minimize(amac, baslangic, method="L-BFGS-B", bounds=sinirlar, **(secenekler or {}))
    if sonuc.success:
        return sonuc.x
    warnings.warn(f"{ad}: L-BFGS-B yakınsamadı ({sonuc.message}); Nelder-Mead yedeğiyle cilalanıyor",
                  RuntimeWarning, stacklevel=2)
    cila = minimize(amac, sonuc.x, method="Nelder-Mead", bounds=sinirlar,
                    options={"xatol": 1e-8, "fatol": 1e-12, "maxiter": 20_000})
    if cila.success or (sonuc.fun - cila.fun) * n < PLATO_LL_TOLERANS:
        return cila.x
    raise RuntimeError(f"{ad} optimizasyonu yakınsamadı: {sonuc.message} / {cila.message}")


def _log_oran_terimi(prm: BGNBDParametreleri, x, t_x, T) -> np.ndarray:
    """ln[ a/(b+x−1) · ((α+T)/(α+t_x))^(r+x) ]; x = 0 için −∞."""
    tekrar = x > 0
    b_x = np.where(tekrar, prm.b + x - 1, 1.0)
    deger = np.log(prm.a) - np.log(b_x) + (prm.r + x) * (np.log(prm.alfa + T) - np.log(prm.alfa + t_x))
    return np.where(tekrar, deger, -np.inf)


def p_hayatta(prm: BGNBDParametreleri, x, t_x, T) -> np.ndarray:
    """P(hayatta | x, t_x, T) = 1 / [1 + 1{x>0} · a/(b+x−1) · ((α+T)/(α+t_x))^(r+x)]."""
    x, t_x, T = _diziler(x, t_x, T)
    return np.exp(-np.logaddexp(0.0, _log_oran_terimi(prm, x, t_x, T)))


def sonsal_oran(prm: BGNBDParametreleri, x, T) -> np.ndarray:
    """Hayattaysa beklenen günlük ziyaret oranı (λ'nın sonsal ortalaması): (r+x)/(α+T)."""
    x, T = np.asarray(x, dtype=float), np.asarray(T, dtype=float)
    return (prm.r + x) / (prm.alfa + T)


# a bu değere bu kadar yakınsa (veya c = a+b+x−1 ≤ 0 ise) kapalı formdaki (a−1) bölmesi kararsızdır;
# aynı beklenti sayısal integralle hesaplanır.
_A_BIR_TOLERANS = 1e-4


def beklenen_ziyaret(prm: BGNBDParametreleri, t: float, x, t_x, T) -> np.ndarray:
    """(T, T+t] aralığında beklenen ziyaret sayısı, E[Y(t) | x, t_x, T] (makale, denklem 10).

        E = (a+b+x−1)/(a−1) · [1 − ((α+T)/(α+T+t))^(r+x) · ₂F₁(r+x, b+x; a+b+x−1; t/(α+T+t))]
            / [1 + 1{x>0} · a/(b+x−1) · ((α+T)/(α+t_x))^(r+x)]
    """
    x, t_x, T = _diziler(x, t_x, T)
    return p_hayatta(prm, x, t_x, T) * hayattaysa_beklenen_ziyaret(prm, t, x, T)


def hayattaysa_beklenen_ziyaret(prm: BGNBDParametreleri, t: float, x, T) -> np.ndarray:
    """E[Y(t) | hayatta, x, T]: λ ~ Gamma(r+x, α+T), p ~ Beta(a, b+x) sonsalında.

        (a+b+x−1)/(a−1) · [1 − ((α+T)/(α+T+t))^(r+x) · ₂F₁(r+x, b+x; a+b+x−1; t/(α+T+t))]
    MBG/NBD aynı ifadeyi b yerine b+1 ile kullanır (sonsal p ~ Beta(a, b+x+1)).
    """
    x, T = np.asarray(x, dtype=float), np.asarray(T, dtype=float)
    r, alfa, a, b = prm.r, prm.alfa, prm.a, prm.b
    c = a + b + x - 1
    if abs(a - 1.0) < _A_BIR_TOLERANS or np.any(c <= 0):
        return _hayattaysa_beklenen_integral(prm, t, x, T)
    z = t / (alfa + T + t)
    kuvvet = np.exp((r + x) * (np.log(alfa + T) - np.log(alfa + T + t)))
    return (a + b + x - 1) / (a - 1) * (1.0 - kuvvet * hyp2f1(r + x, b + x, c, z))


def _hayattaysa_beklenen_integral(prm: BGNBDParametreleri, t: float, x, T) -> np.ndarray:
    """E[Y(t) | hayatta] = E_p[(1 − ((α+T)/(α+T+p·t))^(r+x)) / p],  p ~ Beta(a, b+x).

    (λ, p) sonsalında: E[Y(t) | λ, p, hayatta] = (1 − e^(−λ·p·t)) / p, λ ~ Gamma(r+x, α+T).
    Kapalı formla aynı nicelik; a ≈ 1 durumunda kullanılır.
    """
    sonuc = np.empty(len(x))
    for i, (xi, Ti) in enumerate(zip(x, T)):
        log_b = betaln(prm.a, prm.b + xi)

        def integrand(p, xi=xi, Ti=Ti, log_b=log_b):
            if p <= 0.0:
                return 0.0
            kalan = -np.expm1((prm.r + xi) * (np.log(prm.alfa + Ti) - np.log(prm.alfa + Ti + p * t)))
            yogunluk = np.exp((prm.a - 1) * np.log(p) + (prm.b + xi - 1) * np.log1p(-p) - log_b) if p < 1 else 0.0
            return kalan / p * yogunluk

        sonuc[i] = quad(integrand, 0.0, 1.0, limit=200)[0]
    return sonuc
