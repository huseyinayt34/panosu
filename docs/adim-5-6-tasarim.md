# Adım 5a + 6: Model kütüphanesi ve backtest (tasarım belgesi)

Genel kurallar için `CLAUDE.md`'ye bak. Bu belge proje sahibi tarafından onaylanmış matematik kararlarını
içerir; ajan bunları değiştirmez, bir sorun görürse durup raporlar.

## Sıralama değişikliği
Hangi modelin ürüne gireceğine backtest karar verecek. Bu yüzden:
1. **5a** Model kütüphanesi (veritabanı yok, saf Python/NumPy/SciPy)
2. **6** Backtest (sentetik veri, veritabanı yok)
3. **5b** Seçilen modelin `churn_skorlari`'na bağlanması (ayrı bir belgeyle, backtest sonucundan sonra)

`CLAUDE.md` yol haritası buna göre güncellenir: 5 → "5a Tamam / 5b Bekliyor" şeklinde.

## Alan bilgisi (proje sahibinin gözlemi; Faz 0 görüşmesiyle doğrulanacak)
Erkek berber müşterileri:
- Çoğunluk **ayda bir** gelir; aralık saç uzamasına bağlı olduğu için oldukça **düzenlidir**.
- Az sayıda müşteri **haftada bir** gelir; genellikle berberin yakın çevresindendir ve **daha çok harcar**.
- Bir kısmı **bir aydan uzun** aralıklarla gelir.
- (Genel bilgi) Bir kez gelip bir daha gelmeyen müşteriler de vardır.

## Modeller
### M0: V1 (mevcut)
`MusteriAnalizi.py`'deki model: aralıklar ~ N(μ, σ²), risk = Φ((r − μ)/σ_etkin), σ_etkin = max(σ, 0.25μ).
Karşılaştırma için "hayatta olma olasılığı" = 1 − risk. En az 3 ziyaret yoksa, eğitim verisindeki tüm
müşterilerin ortanca μ ve σ'sı kullanılır (V1'de "yetersiz veri" diye bırakılan durum; adil karşılaştırma için).

### M1: BG/NBD (Fader, Hardie & Lee, 2005)
- Hayattayken ziyaretler Poisson(λ); λ ~ Gamma(r, α).
- Her ziyaretten sonra bırakma olasılığı p; p ~ Beta(a, b).
- Müşteri başına veri: x (tekrar ziyaret sayısı), t_x (son ziyaretin ilk ziyarete göre zamanı), T (gözlem süresi).
  Zaman birimi: gün.
- Parametreler (r, α, a, b) en çok olabilirlik (MLE) ile tahmin edilir: log-olabilirlik makaledeki kapalı form;
  optimizasyon scipy.optimize.minimize, log-parametrelerde (pozitiflik için), L-BFGS-B, gammaln/betaln ile
  sayısal kararlılık.
- P(hayatta | x, t_x, T) = 1 / [1 + 1{x>0} · a/(b+x−1) · ((α+T)/(α+t_x))^(r+x)]
- Hayattaysa beklenen günlük oran (sonsal ortalama): (r+x)/(α+T).

### M2: Gamma-Gamma (Fader, Hardie & Lee, 2005, harcama modeli)
- Ziyaret başına harcama ~ Gamma(p, ν), ν ~ Gamma(q, γ). Parametreler MLE ile.
- Müşterinin beklenen sepet tutarı (sonsal): (γ + m̄·x)·p / (p·x + q − 1), x ≥ 1 için.
- **Bilinen varsayım: harcama ile ziyaret sıklığı bağımsızdır.** Alan bilgisi bunun berberde bozulabileceğini
  söylüyor (sık gelen daha çok harcıyor); S4 bunu test eder. Kütüphane, eğitim verisinde sıklık ile ortalama
  sepet arasındaki Pearson korelasyonunu raporlayan bir tanı fonksiyonu içerir.

### M3: MBG/NBD (Batislam, Denizel & Filiztekin, 2007) — backtest sonrası eklendi
Gerekçe: BG/NBD'de x = 0 müşterinin P(hayatta) değeri yapısal olarak 1; S2/S4'te tek seferlik grubun tamamı yanlış
sınıflandı. Hedef sektörde (güzellik salonları) ilk ziyaret sonrası kayıp çok yüksek.
- BG/NBD ile aynı varsayımlar (λ ~ Gamma(r, α), p ~ Beta(a, b)); tek fark: bırakma **ilk ziyaret dahil** her ziyaretten
  sonra mümkün (x + 1 fırsat).
- P(hayatta | x, t_x, T) = 1 / [1 + a/(b+x) · ((α+T)/(α+t_x))^(r+x)]  (x = 0 dahil; x = 0'da < 1).
- L = [Γ(r+x)α^r/Γ(r)] · [B(a, b+x+1)/B(a,b)] · (α+T)^(−(r+x)) · [1 + a/(b+x) · ((α+T)/(α+t_x))^(r+x)].
  Bireysel olabilirlik (1−p)^(x+1)·λ^x·e^(−λT) + p(1−p)^x·λ^x·e^(−λt_x)'den (λ, p) üzerinden integralle türetilerek doğrulandı.
- Beklenen ziyaret: hayattaysa sonsal p ~ Beta(a, b+x+1) olduğundan BG/NBD ifadesinin b → b+1 hâli:
  (a+b+x)/(a−1) · [1 − ((α+T)/(α+T+t))^(r+x) · ₂F₁(r+x, b+x+1; a+b+x; t/(α+T+t))] · P(hayatta).
- MLE BG/NBD ile aynı yapı (log-parametre, L-BFGS-B, `bgnbd.log_mle` plato yedeği). Kod: `analitik/mbgnbd.py`.
- Testler: x = 0'da P(hayatta) < 1; BG/NBD'deki monotonluk özellikleri; log-olabilirlik bağımsız hesapla; beklenen
  ziyaret doğrudan sayısal integralle; S0'da (5 000 müşteri) r ve α'nın geri kazanımı, eşik %15. a/(a+b) sınanmaz:
  S0 BG/NBD ile üretildiğinden M3 orada yanlış belirlenmiştir ve a/(a+b)'yi sistematik olarak ~%24 düşük tahmin eder.

### Riskteki Para (tanım)
- beklenen_aylik_ciro = 30 × (r+x)/(α+T) × beklenen_sepet
- riskteki_para = (1 − P(hayatta)) × beklenen_aylik_ciro
Para hesapları raporlamada Decimal'e çevrilir; model içi hesaplar float64 olabilir (istatistiksel model).

## Senaryolar (sentetik veri)
Her senaryoda: 2 yıl gözlem, 2 000 müşteri (edinim zamanları gözlem süresine düzgün dağılır), sabit tohum,
her senaryo 20 farklı tohumla tekrarlanır (sonuçlar ortalama ± standart sapma).
Mevcut `sentetik/` üreticisinin veri modeli genişletilir; veritabanına hiçbir şey yazılmaz.

| Kod | Ne bozulur | Üretim kuralı |
|---|---|---|
| S0 | Hiçbir şey | Veri BG/NBD varsayımlarıyla üretilir. Referans; tek başına kanıt sayılmaz. |
| S1 | Poisson | Hayattayken aralıklar ~ Gamma(şekil k=8, ortalama μ_i) (değişim katsayısı ≈ 0.35; saç uzaması düzeni). μ_i ~ Gamma, ortalaması 30 gün. Bırakma BG/NBD'deki gibi. |
| S2 | Gamma heterojenliği | Karışım (HİPOTEZ, berber görüşmesiyle güncellenecek): haftalık %5 (μ=7 g), aylık %65 (μ=30 g), seyrek %20 (μ=50 g), tek seferlik %10 (yalnızca ilk ziyaret). Gruplar içinde aralıklar S1'deki gibi düzenli. |
| S3 | Ziyaret sonrası bırakma | Bırakma ziyaretten bağımsız, sürekli zamanda: ömür ~ Üstel(ortalama 18 ay) (taşınma vb.). Ziyaretler Poisson. |
| S4 | Harcama–sıklık bağımsızlığı | S2'nin grupları; ortalama sepet grup sıklığıyla pozitif ilişkili (haftalık grup ×1.4, seyrek grup ×0.9; HİPOTEZ). |
| S5 | Güzellik salonu (backtest sonrası eklendi) | Müşterilerin %55'i tek seferlik (ilk ziyarette kayıp); kalanlar S1'deki gibi düzenli, ortalama aralık 35 gün; ortalama sepet 900 TL. HİPOTEZ: sektör raporlarındaki "ilk ziyaret sonrası müşterilerin yarısından fazlası dönmüyor" bulgusu. |

S1–S5'te belgede sayısı verilmeyen değerler (BG/NBD gerçek parametreleri, harcama parametreleri, μ_i'nin Gamma şekli vb.)
`backtest/senaryolar.py`'de sabittir ve `docs/backtest-sonuclari.md`'nin "Varsayımlar" bölümünde listelenir.
Backtest M0, M1 ve M3'ü karşılaştırır; S2, S4 ve S5'te tek seferlik grup ayrı satırda raporlanır.

## Değerlendirme
Her senaryoda gözlem süresi iki parçaya bölünür: kalibrasyon (ilk 18 ay) ve bekleme (son 6 ay).
Modeller yalnızca kalibrasyon verisiyle eğitilir.
- **Ayrım gücü:** kalibrasyon sonundaki gerçek hayatta/ölü etiketine karşı P(hayatta) için ROC AUC.
- **Kalibrasyon:** Brier skoru ve 10 kutulu güvenilirlik tablosu (tahmin edilen ortalama olasılık ile gerçek oran).
- **Ziyaret tahmini:** bekleme dönemindeki gerçek ziyaret sayısına karşı beklenen ziyaret sayısı; MAE ve toplam hata %.
- **Para:** bekleme dönemindeki gerçek ciroya karşı tahmini ciro (M1+M2); müşteri bazında MAE, toplamda hata %.
- **Segment kırılımı (S2, S4):** her metrik grup bazında da raporlanır.
- **Parametre geri kazanımı (yalnızca S0):** tahmin edilen (r, α, a, b) gerçek değerlere yakın mı (göreli hata).

## Kod yapısı
```
analitik/
  __init__.py
  v1.py              # M0 (MusteriAnalizi.py'den taşınır; eski dosya bu fonksiyonları içe aktaran ince bir kabuk olur)
  bgnbd.py           # M1: log-olabilirlik, fit, p_hayatta, beklenen_ziyaret, sonsal oran
  mbgnbd.py          # M3: MBG/NBD (bgnbd'nin parametre yapısı ve MLE'sini kullanır)
  gamma_gamma.py     # M2: log-olabilirlik, fit, beklenen_sepet, bagimsizlik_tanisi
  ozellikler.py      # ziyaret listesinden (x, t_x, T, m̄) çıkarımı
  riskteki_para.py   # tanımdaki formül
backtest/
  __init__.py
  senaryolar.py      # S0–S4 üreticileri (sentetik/ ile ortak kodu yeniden kullanır)
  metrikler.py
  calistir.py        # python -m backtest: tüm senaryolar × 20 tohum, sonuçları yazar
```
Çıktı: `docs/backtest-sonuclari.md` (tablolar, commit'lenir) ve `raporlar/backtest/` altında ham CSV'ler (commit'lenmez).
Grafik bu adımda yok; tablolar yeterli.

## Testler
- `ozellikler`: elle hesaplanmış küçük örneklerde x, t_x, T doğru; tek ziyaretli müşteride x=0.
- `bgnbd`: x=0 için P(hayatta)=1; aynı x ve T'de t_x büyüdükçe P(hayatta) artar; aynı x, t_x'te T büyüdükçe azalır;
  log-olabilirlik bilinen bir örnekte önceden hesaplanmış değerle eşleşir (tolerans 1e-6).
- `bgnbd` geri kazanım: S0'dan 40 000 müşteriyle üretilen veride tahmin edilen parametrelerin göreli hatası < %15.
  (İlk hâli 5 000 müşteriydi; a–b örneklem gürültüsü %15'i aşabildiğinden 2026-10-01'de proje sahibi kararıyla büyütüldü.)
- `gamma_gamma`: benzer geri kazanım testi (aynı veri, 40 000 müşteri); x=0 müşteri için beklenen sepet = popülasyon ortalaması.
- `riskteki_para`: P(hayatta)=1 → 0; P(hayatta)=0 → beklenen aylık ciro.
- Backtest'in tamamı testlerde çalıştırılmaz (yavaş); yalnızca 1 tohum × 200 müşteri ile duman testi.

## Paket onayı
`scipy` eklenmesi onaylıdır (requirements.txt'e sürümüyle). NumPy zaten üretici tarafından kullanılıyor.
Başka paket (lifetimes, pymc vb.) eklenmez: modeller sıfırdan yazılır.

## Kabul kriterleri
- Tam `pytest -q` yeşil.
- `python -m backtest` hatasız biter; `docs/backtest-sonuclari.md` üretilir.
- Rapor: her senaryo için M0 ve M1'in ROC AUC ve Brier değerleri (ortalama ± sd), S0 parametre geri kazanımı,
  S4'te bağımsızlık tanısının korelasyon değeri, talimattan her sapma.
- Rapordan sonra dur: hangi modelin ürüne gireceğine proje sahibi karar verir (5b).
