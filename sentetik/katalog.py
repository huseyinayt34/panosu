"""Sektör profilleri: hizmet katalogları ve müşteri davranışının gizli parametreleri.

Her sektörün davranışı BG/NBD modelinin (Fader, Hardie & Lee, 2005) iki dağılımıyla tanımlanır:

    λ ~ Gamma(şekil = r, oran = α)    müşterinin günlük geliş hızı (kişiden kişiye değişir)
    p ~ Beta(a, b)                    her ziyaretten sonra müşteriyi kaybetme olasılığı

Okunabilirlik için parametreler "yorumlanabilir" biçimde verilir ve α, a, b bunlardan türetilir:
    ort_aralik_gun   : E[λ] = 1 / ort_aralik_gun olacak şekilde α = r * ort_aralik_gun
    r                : küçük r = müşteriler arası fark büyük (heterojen kitle)
    ort_birakma      : E[p] = a / (a + b)
    birakma_yogunluk : a + b; büyük değer = herkesin p'si ortalamaya yakın
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HizmetTanimi:
    ad: str
    kategori: str
    fiyat: int            # TRY, liste fiyatı (referans tarihindeki)
    sure_dk: int
    ana_mi: bool          # True: ziyaretin asıl sebebi | False: ek hizmet (sepete eklenir)
    agirlik: float = 1.0  # ana hizmet: popülerlik | ek hizmet: sepete eklenme olasılığı


@dataclass(frozen=True)
class SektorProfili:
    sektor: str                       # isletmeler.sektor CHECK kısıtındaki değerlerden biri
    isletme_adi: str
    r: float
    ort_aralik_gun: float
    ort_birakma: float
    birakma_yogunluk: float
    kadin_orani: float                # müşteri isimleri için
    kapali_gunler: frozenset[int]     # 0 = Pazartesi ... 6 = Pazar
    calisma_saatleri: tuple[int, int]
    hizmetler: tuple[HizmetTanimi, ...] = field(default_factory=tuple)

    @property
    def alfa(self) -> float:
        return self.r * self.ort_aralik_gun

    @property
    def beta_a(self) -> float:
        return self.ort_birakma * self.birakma_yogunluk

    @property
    def beta_b(self) -> float:
        return (1 - self.ort_birakma) * self.birakma_yogunluk


H = HizmetTanimi

PROFILLER: dict[str, SektorProfili] = {
    "berber": SektorProfili(
        sektor="berber", isletme_adi="[DEMO] Usta Berber",
        r=3.0, ort_aralik_gun=21, ort_birakma=0.05, birakma_yogunluk=20,
        kadin_orani=0.03, kapali_gunler=frozenset({6}), calisma_saatleri=(9, 21),
        hizmetler=(
            H("Saç Kesimi", "Kesim", 350, 30, True, 5.0),
            H("Saç + Sakal", "Kesim", 500, 45, True, 3.0),
            H("Sakal Tıraşı", "Tıraş", 200, 20, True, 1.5),
            H("Çocuk Saç Kesimi", "Kesim", 250, 20, True, 0.8),
            H("Yıkama & Fön", "Bakım", 150, 15, False, 0.25),
            H("Cilt Bakımı", "Bakım", 400, 30, False, 0.08),
            H("Kaş Düzeltme", "Bakım", 100, 10, False, 0.15),
        ),
    ),
    "kuafor": SektorProfili(
        sektor="kuafor", isletme_adi="[DEMO] Nazlı Kuaför",
        r=2.5, ort_aralik_gun=35, ort_birakma=0.06, birakma_yogunluk=15,
        kadin_orani=0.95, kapali_gunler=frozenset({6}), calisma_saatleri=(10, 20),
        hizmetler=(
            H("Kesim & Fön", "Kesim", 600, 60, True, 4.0),
            H("Fön", "Şekillendirme", 300, 30, True, 3.0),
            H("Dip Boya", "Boya", 1500, 90, True, 1.5),
            H("Röfle", "Boya", 2500, 150, True, 0.7),
            H("Keratin Bakım", "Bakım", 3500, 120, True, 0.3),
            H("Saç Bakım Maskesi", "Bakım", 400, 20, False, 0.2),
            H("Manikür", "Tırnak", 400, 30, False, 0.15),
        ),
    ),
    "guzellik": SektorProfili(
        sektor="guzellik", isletme_adi="[DEMO] Işıltı Güzellik Merkezi",
        r=2.0, ort_aralik_gun=28, ort_birakma=0.07, birakma_yogunluk=12,
        kadin_orani=0.90, kapali_gunler=frozenset({6}), calisma_saatleri=(10, 20),
        hizmetler=(
            H("Cilt Bakımı", "Cilt", 900, 60, True, 3.0),
            H("Lazer Epilasyon Seansı", "Epilasyon", 1500, 45, True, 2.5),
            H("İpek Kirpik", "Kirpik", 1200, 90, True, 1.2),
            H("Kaş Alımı", "Kaş", 200, 15, True, 2.0),
            H("Manikür", "Tırnak", 400, 30, False, 0.25),
            H("Pedikür", "Tırnak", 500, 45, False, 0.12),
        ),
    ),
    "spor_salonu": SektorProfili(
        sektor="spor_salonu", isletme_adi="[DEMO] Denge Pilates Stüdyosu",
        r=4.0, ort_aralik_gun=5, ort_birakma=0.015, birakma_yogunluk=40,
        kadin_orani=0.80, kapali_gunler=frozenset(), calisma_saatleri=(7, 22),
        hizmetler=(
            H("Grup Pilates Dersi", "Ders", 350, 50, True, 5.0),
            H("Reformer Pilates", "Ders", 600, 50, True, 3.0),
            H("Özel Ders", "Ders", 1200, 60, True, 0.6),
            H("Protein İçeceği", "Bar", 150, 5, False, 0.20),
            H("Havlu Kiralama", "Diğer", 40, 1, False, 0.10),
        ),
    ),
}

# ---------------------------------------------------------------------------------------------
# İsim havuzları (rastgele birleştirilir; gerçek kişilerle eşleşme amaçlanmaz)
# ---------------------------------------------------------------------------------------------
ERKEK_ADLARI = (
    "Ahmet", "Mehmet", "Mustafa", "Ali", "Hüseyin", "Hasan", "İbrahim", "Murat", "Emre", "Burak",
    "Can", "Deniz", "Eren", "Furkan", "Kerem", "Onur", "Serkan", "Tolga", "Yusuf", "Oğuz",
    "Barış", "Cem", "Efe", "Gökhan", "Kaan", "Mert", "Ozan", "Selim", "Umut", "Volkan",
)
KADIN_ADLARI = (
    "Ayşe", "Fatma", "Zeynep", "Elif", "Emine", "Merve", "Büşra", "Esra", "Seda", "Ceren",
    "Derya", "Ebru", "Gizem", "İrem", "Melis", "Nazlı", "Özge", "Pınar", "Selin", "Tuğba",
    "Aslı", "Buse", "Damla", "Ece", "Hande", "Kübra", "Nur", "Sibel", "Yasemin", "Zehra",
)
SOYADLARI = (
    "Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Yıldırım", "Öztürk", "Aydın", "Özdemir",
    "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara", "Koç", "Kurt", "Özkan", "Şimşek",
    "Polat", "Erdoğan", "Güneş", "Aksoy", "Korkmaz", "Tekin", "Aktaş", "Bulut", "Keskin", "Ünal",
)
