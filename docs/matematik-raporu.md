# Panosu matematik raporu: üye kaybı ve yenileme riski modeli

Hazırlayan: HuseyinAYT (tasarım ve matematik), kodlama desteği: Claude Code ajanı.
Sürüm: model `mbgnbd-map-v2` (commit `b8c5ea5`, 2026-10-03). Bütün sayılar **sentetik** (yapay üretilmiş) veriden gelir.
Gerçek bir işletmenin verisiyle henüz doğrulanmadı; bu, ilk pilotun işi (Bölüm 10).

**Bu rapor nasıl okunur?** Bölüm 1 matematik bilmeyen biri içindir (işletme sahibi, yazılım firması, vitrin sayfası).
Bölüm 2–8 modeli formülleriyle anlatır; her terim ilk geçtiği yerde açıklanır. Bölüm 9 mühendislik derslerini,
Bölüm 10 dürüst sınırları, Bölüm 11 mülakatta kullanılacak kısa cümleleri toplar. Sembol sözlüğü en sonda.

---

## 1. Sade dille özet (vitrin sayfasına taşınabilir)

Bir pilates stüdyosu düşünün. Her ay bazı üyeler "bırakıyor": paketini yenilemiyor, sessizce kayboluyor.
Stüdyo sahibi bunu genelde paket bittikten sonra fark ediyor; o noktada üyeyi geri kazanmak zor.

Panosu her gece, her üye için iki soruyu cevaplar:

1. **Bu üye hâlâ "bizimle" mi?** Yani düzenli gelme alışkanlığı sürüyor mu, yoksa çoktan bıraktı mı?
2. **Paketi bitince yenileyecek mi?** Bunun olasılığı yüzde kaç?

Sonra bu olasılığı paketin fiyatıyla çarpar ve **Riskteki Para**'yı çıkarır: "Önümüzdeki 45 günde, müdahale etmezseniz
kaybetmeyi beklediğiniz ciro." Liste en riskliden başlar ve her üyenin yanında sade bir gerekçe yazar, örneğin
"Normalde ~7 günde bir geliyor; 45 gündür gelmiyor (normalin 6,6 katı)."

**Nasıl çalışır, tek paragrafta:** Model iki basit gözleme dayanır. Birincisi, her üyenin kendine özgü bir gelme
hızı vardır (biri haftada üç, biri haftada bir gelir). İkincisi, her ziyaretten sonra üyenin bırakma ihtimali vardır.
Model bu iki özelliği, stüdyonun bütün üyelerinin geçmişinden öğrenir ve her üyenin kendi geçmişine uygular.
Sık gelen bir üyenin 10 günlük yokluğu alarm sebebidir; ayda bir gelen bir üyenin 10 günlük yokluğu normaldir.
Model bu farkı kendiliğinden görür.

**Bu bir yapay zekâ değil, istatistiksel bir olasılık modelidir.** Pazarlama ve satış araştırmalarında 20 yıldır
kullanılan, hakemli dergilerde yayımlanmış bir model ailesine dayanır (Fader, Hardie & Lee, 2005; Batislam,
Denizel & Filiztekin, 2007). Her sayının nereden geldiği açıklanabilir.

**Ne kadar iyi?** Sentetik bir stüdyo verisinde (2 yıllık, 1.500 üye, 20 tekrar), yenilemeyecek üyeleri
yenileyecek olanlardan ayırmada AUC **0,83** aldı (0,50 yazı-tura, 1,00 kusursuz demek). Basit kural
("son 21 günde en fazla 1 kez geldiyse riskli") 0,72'de kaldı. Toplam kayıp ciroyu %13 eksik tahmin etti;
basit kural %36 eksik. Bu sayılar sentetik veride ölçüldü; gerçek veride ölçüm ilk pilotla yapılacak.

---

## 2. Problem: elimizde ne var, neyi soruyoruz?

### 2.1 Veri: her üyeden üç sayı

Stüdyonun elinde ziyaret kayıtları var: "Ayşe, 3 Mart 18:15, giriş yaptı" gibi. Model bunu her üye için üç sayıya
indirir (`analitik/ozellikler.py`):

| Sembol | Anlamı | Ayşe örneği |
|---|---|---|
| $x$ | **Tekrar** ziyaret sayısı (ilk ziyaret sayılmaz) | 21 ziyaret yaptı → $x = 20$ |
| $t_x$ | Son ziyaretin, ilk ziyarete göre kaçıncı günde olduğu | ilk ziyaretten 160 gün sonra |
| $T$ | İlk ziyaretten bugüne geçen gün | 165 gün |

Bu üçlüye pazarlama literatüründe **RFM özeti** denir (Recency = yakınlık, Frequency = sıklık; M = para, burada
paket fiyatı ayrı tutulur). Ayşe'nin bugün kaç gündür gelmediği $T - t_x = 5$ gündür.

**Neden bu üç sayı yeter?** Bölüm 3'teki modelde bir üyenin olabilirliği (aşağıda tanımlanıyor) yalnızca
$(x, t_x, T)$'ye bağlı çıkar. Ziyaretlerin tam tarihleri ek bilgi taşımaz. İstatistikte buna **yeterli istatistik**
denir: veriyi bu özete indirmek hiçbir bilgi kaybettirmez.

### 2.2 Soru

"Hayatta olmak" (İngilizce *alive*) burada şu anlama gelir: üyenin gelme alışkanlığı hâlâ sürüyor. Bıraktıysa
"ölü"dür; bu teknik bir terimdir, kimseyi kırmak için değil. Zorluk şu: **bırakma gözlenmez.** Kimse "bıraktım" demez.
Elimizde yalnızca "45 gündür gelmedi" var. Bu sessizlik iki şekilde açıklanabilir:

- Üye bıraktı.
- Üye hâlâ hayatta ama bu sefer uzun bir ara verdi (tatil, hastalık, yoğun dönem).

Model bu iki açıklamayı olasılıkla tartar. Cevap bir sayıdır: $P(\text{hayatta} \mid x, t_x, T)$, yani "bu geçmişi
gördüğümüze göre üyenin hâlâ hayatta olma olasılığı". Dikey çizgi "verildiğinde" diye okunur.

---

## 3. Model: MBG/NBD

### 3.1 Hikâye: her üyenin bir zarı ve bir madeni parası var

Her üyenin cebinde iki şey olduğunu düşünün:

1. **Gelme hızı $\lambda$ (lambda):** "Günde ortalama kaç kez gelir." $\lambda = 0{,}14$ ise ortalama 7 günde bir gelir.
   Üye hayattayken ziyaretler rastgele zamanlarda gelir; bunu **Poisson süreci** ile modelliyoruz. Poisson süreci
   "olaylar birbirinden bağımsız, sabit bir ortalama hızla gelir" demektir (yağmur damlalarının çatıya düşmesi gibi).
2. **Bırakma olasılığı $p$:** Her ziyaretten sonra üye bir madeni para atar; $p$ olasılıkla "bıraktım" gelir ve bir
   daha hiç gelmez.

Bu iki sayı her üyede farklıdır. Ama tek tek üyelerin $\lambda$ ve $p$ değerlerini bilemeyiz, çünkü çoğu üyenin
birkaç ziyareti vardır. Bunun yerine "stüdyodaki üyelerin $\lambda$ ve $p$ değerleri nasıl dağılmış" sorusunu
modelliyoruz:

- $\lambda \sim \text{Gamma}(r, \alpha)$: gelme hızlarının dağılımı. **Gamma dağılımı** pozitif sayılar için esnek
  bir dağılımdır. Ortalaması $m = r/\alpha$ (stüdyonun ortalama gelme hızı). $r$ büyüdükçe üyeler birbirine benzer
  (dağılım daralır).
- $p \sim \text{Beta}(a, b)$: bırakma olasılıklarının dağılımı. **Beta dağılımı** 0 ile 1 arasındaki sayılar
  (olasılıklar) için kullanılır. Ortalaması $\mu = a/(a+b)$ (ortalama bırakma olasılığı). $\kappa = a + b$
  (kappa, "yoğunlaşma") büyüdükçe herkesin $p$'si ortalamaya yaklaşır; küçüldükçe üyeler bağlılıkta çok farklılaşır
  (bazıları hemen bırakır, bazıları hiç bırakmaz).

Yani bütün stüdyo **dört sayıyla** özetlenir: $(r, \alpha, a, b)$. Bunlar modelin **parametreleri**dir. Bu "önce
grubu öğren, sonra bireye uygula" yapısına **hiyerarşik model** denir. Faydası: 3 ziyaretli yeni bir üye hakkında
bile mantıklı konuşabiliriz, çünkü ona stüdyonun genel davranışından ödünç bilgi taşırız.

### 3.2 BG/NBD ile MBG/NBD arasındaki tek fark ve neden önemli

Literatürdeki ilk model **BG/NBD**'dir (Fader, Hardie & Lee, 2005). Orada para yalnızca **tekrar** ziyaretlerden sonra
atılır. Sonuç: ilk ziyaretten sonra hiç gelmeyen ($x = 0$) biri modele göre **asla bırakmamış** olur ve
$P(\text{hayatta}) = 1$ alır. Formüldeki $\mathbb{1}\{x>0\}$ göstergesi tam olarak bunu söyler:

$$P_{\text{BG}}(\text{hayatta}) = \frac{1}{1 + \mathbb{1}\{x>0\}\,\dfrac{a}{b+x-1}\left(\dfrac{\alpha+T}{\alpha+t_x}\right)^{r+x}}$$

**MBG/NBD** (Batislam, Denizel & Filiztekin, 2007) parayı **ilk ziyaret dahil** her ziyaretten sonra attırır
($x+1$ fırsat). Tek seferlik müşteri de bırakmış olabilir:

$$P_{\text{MBG}}(\text{hayatta}) = \frac{1}{1 + \dfrac{a}{b+x}\left(\dfrac{\alpha+T}{\alpha+t_x}\right)^{r+x}}$$

Bu küçük fark, güzellik salonu gibi müşterilerin yarısının bir kez gelip kaybolduğu işletmede her şeyi değiştirir
(Bölüm 8.2: BG/NBD'nin AUC'si 0,23, MBG/NBD'ninki 0,98).

### 3.3 Formülü okumak: bir oran, iki açıklama

Paydadaki kesir, Bölüm 2.2'deki iki açıklamanın **olasılık oranıdır**:

$$\frac{P(\text{bıraktı ve bu veri})}{P(\text{hayatta ve bu veri})} = \underbrace{\frac{a}{b+x}}_{\text{bırakma eğilimi}} \cdot \underbrace{\left(\frac{\alpha+T}{\alpha+t_x}\right)^{r+x}}_{\text{sessizliğin ağırlığı}}$$

- **Bırakma eğilimi** $a/(b+x)$: $x$ büyüdükçe küçülür. Çok kez gelmiş bir üye "bırakmayan tip" olduğunu
  kanıtlamıştır (Bayesçi güncelleme: her ziyaret, $p$'sinin küçük olduğuna dair kanıttır).
- **Sessizliğin ağırlığı**: sessizlik ($T - t_x$) uzadıkça 1'den büyür. Üs $r + x$ olduğu için **sık gelen birinin
  sessizliği çok daha ağır basar**. Bölüm 1'deki "sık gelenin 10 günlük yokluğu alarm" sezgisi bu üstür.

Sonra $P = 1/(1 + \text{oran})$: oran 0 ise $P = 1$, oran sonsuza giderse $P \to 0$.

**Elle hesaplanmış örnekler.** Parametreler, 29 üyeli test verisinin MAP tahmini (Bölüm 4): $r = 389{,}8$,
$\alpha = 2644$, $a = 0{,}58$, $b = 52{,}5$. Ortalama gelme hızı $m = r/\alpha = 0{,}147$/gün (yaklaşık 7 günde bir).

| Üye | $x$ | $t_x$ | $T$ | Sessizlik | MBG $P(\text{hayatta})$ | BG $P(\text{hayatta})$ |
|---|---|---|---|---|---|---|
| Ayşe | 20 | 160 | 165 | 5 gün | **0,98** | 0,98 |
| Burak | 20 | 120 | 165 | 45 gün | **0,14** | 0,14 |
| Can | 20 | 90 | 165 | 75 gün | **0,002** | 0,002 |
| Deniz (bir kez geldi) | 0 | 0 | 30 | 30 gün | **0,53** | **1,00** |

Ayşe ile Burak'ın ziyaret sayısı aynı; fark yalnızca sessizlikte. Deniz satırı BG/NBD'nin kör noktasını gösterir:
30 gündür gelmeyen tek seferlik birini "kesin hayatta" sayar.

---

## 4. Parametreleri bulmak: olabilirlik, önsel, MAP

### 4.1 Olabilirlik

**Olabilirlik (likelihood)** şu sorunun cevabıdır: "Parametreler $(r, \alpha, a, b)$ olsaydı, gördüğümüz veriyi görme
olasılığımız ne olurdu?" İyi parametre, gerçekte olanı "en az şaşırtıcı" kılan parametredir. MBG/NBD'de bir üyenin
katkısı, $\lambda$ ve $p$ üzerinden integral alınarak kapalı formda çıkar (`analitik/mbgnbd.py`):

$$L_i = \frac{\Gamma(r+x)\,\alpha^r}{\Gamma(r)} \cdot \frac{B(a,\,b+x+1)}{B(a,b)} \cdot (\alpha+T)^{-(r+x)} \left[1 + \frac{a}{b+x}\left(\frac{\alpha+T}{\alpha+t_x}\right)^{r+x}\right]$$

$\Gamma$ gamma fonksiyonu (faktöriyelin genellemesi), $B$ beta fonksiyonudur. Üyeler bağımsız kabul edildiği için
toplam olabilirlik çarpımdır; çarpım çok küçük sayılar ürettiği için logaritmasını toplarız:
$\ell = \sum_i \ln L_i$. Bunu en büyük yapan parametreye **en çok olabilirlik tahmini (MLE)** denir.

### 4.2 Sorun: veri bazı yönleri belirlemiyor

Dört parametrenin ikisi veriyle çok iyi belirlenir, ikisi neredeyse hiç:

| Nicelik | Anlamı | Veri belirliyor mu? |
|---|---|---|
| $m = r/\alpha$ | Ortalama gelme hızı | Evet, çok iyi |
| $\mu = a/(a+b)$ | Ortalama bırakma olasılığı | Evet |
| $\kappa = a+b$ | Üyeler bağlılıkta ne kadar farklı? | **Hayır**, küçük veride |
| $r$ | Üyeler gelme hızında ne kadar farklı? | **Hayır**, küçük ve türdeş veride |

**Analoji:** Bir sınıfın not ortalamasını 29 öğrenciden iyi tahmin edersiniz. Ama "notlar ne kadar dağınık, ve bu
dağınıklık kaç alt gruptan geliyor" gibi ikinci dereceden bir soruyu 29 öğrenciyle güvenle cevaplayamazsınız.

Bu durumun matematiksel adı **zayıf tanımlanabilirlik**tir. Olabilirlik yüzeyi o yönde neredeyse düz bir **sırt**
oluşturur: sırt boyunca yürüdükçe olabilirlik hemen hemen hiç değişmez. Bu raporda bunu ölçtük
(29 üyeli test verisi, `tests/test_analitik_map.py` içindeki tarif; diğer üç parametre her $\kappa$ için yeniden
en iyiye ayarlandı, buna **profil olabilirlik** denir; iç optimizasyon merkezi fark türevi, sıkı tolerans ve 7 farklı
başlangıçla yapıldı, çünkü düz sırtta varsayılan ayarlar erken duruyor):

| $\kappa$ | 5 | 10 | 53 | 200 | 1.000 | 10.000 | 100.000 |
|---|---|---|---|---|---|---|---|
| $-\ell$ (küçük daha iyi) | 1935,40 | 1934,43 | 1933,10 | 1932,77 | 1932,67 | 1932,65 | 1932,65 |

$\kappa$ 53'ten 100.000'e, yani 1.900 kat büyüyünce olabilirlik yalnızca 0,45 birim (nat) iyileşiyor. Üstelik bu profilde
$r$ de 3 milyona kaçıyor: ikinci düz yön de aynı anda görünüyor. İstatistikte
2 nat'tan küçük farklar genelde "veri ayırt edemiyor" diye okunur. Saf MLE bu yüzden $\kappa \to \infty$'a kaçar ve
nerede duracağını bilgisayardaki 15. ondalık basamaktaki yuvarlama belirler.

**Bunu nasıl fark ettik?** Bir yazılım testiyle. CSV içe aktarma testi aynı veriyi dışarı yazıp geri okuyor ve
"sonuç aynı mı" diye bakıyordu. Veri aynıydı ama 29 üyeli veride $\kappa$ 29 ile 155.800 arasında oynadı; bir üyenin
$P(\text{hayatta})$ değeri 0,049 değişti. Hata kodda değil, modelin matematiğindeydi.

### 4.3 Hessian ile görmek

Bir fonksiyonun bir noktadaki **Hessian**'ı ikinci türevlerinin matrisidir; o noktadaki eğriliği ölçer.
Özdeğerleri (eigenvalue), yüzeyin her ana yöndeki dikliğidir. Büyük özdeğer: dik vadi, parametre iyi belirli.
Sıfıra yakın özdeğer: düz sırt. $\theta = (\ln m, \ln r, \operatorname{logit}\mu, \ln\kappa)$ koordinatlarında,
aynı 29 üyeli veride, $-\ell$'nin Hessian özdeğerleri (bu rapor için hesaplandı):

| Yön (baskın bileşen) | Yalnız olabilirlik | Olabilirlik + önsel |
|---|---|---|
| $\ln m$ | 604,6 | 604,6 |
| $\operatorname{logit}\mu$ | 5,60 | 5,60 |
| $\ln r$ | 0,61 | 0,86 |
| $\ln\kappa$ | **0,34** | **0,59** |

En dik yön ile en düz yön arasında yaklaşık **1.800 kat** fark var. Sağ sütunda $\ln r$ ve $\ln\kappa$ özdeğerlerinin
yaklaşık **0,25** arttığına dikkat ($\ln r$ +0,250, $\ln\kappa$ +0,244): bu, aşağıdaki önselin $1/\sigma^2 = 1/2^2$
katkısıdır. Önsel Hessian'ın köşegenine tam 0,25 ekler; $\ln\kappa$ yönü $\operatorname{logit}\mu$ ile biraz karıştığı
için o özdeğer tam 0,25 kaymaz, ama özdeğerlerin toplamı (matrisin izi) tam +0,50 artar.

### 4.4 Düzeltme 1: yeniden parametreleme

Optimizasyonu $(r, \alpha, a, b)$ yerine $\theta = (\ln m,\ \ln r,\ \operatorname{logit}\mu,\ \ln\kappa)$ üzerinde
yapıyoruz. Bu, aynı modeli farklı koordinatlarla yazmaktır (Kartezyen yerine kutupsal koordinat kullanmak gibi):
model değişmez, ama iyi belirlenen yönler ($m$, $\mu$) ile kötü belirlenen yönler ($r$, $\kappa$) ayrı eksenlere
oturur. Dönüşüm:

$$r = e^{\ln r},\quad \alpha = r/m,\quad a = \kappa\cdot\operatorname{expit}(\operatorname{logit}\mu),\quad b = \kappa\cdot\operatorname{expit}(-\operatorname{logit}\mu)$$

(`expit`, logit'in tersidir: $1/(1+e^{-z})$.) Ayrıntı: $b = (1-\mu)\kappa$ yazımı $\mu$ çok küçükken 1e-9 düzeyinde
hata verirken $\kappa\cdot\operatorname{expit}(-\operatorname{logit}\mu)$ yazımı 1e-15 hassasiyetle tersinirdir. Logaritma
ve logit kullanmanın bir faydası da pozitiflik ve (0, 1) kısıtlarını kendiliğinden sağlamasıdır.

### 4.5 Düzeltme 2: zayıf önsel ve MAP

**Önsel (prior)**, veriyi görmeden önceki makul inancımızdır. Düz sırtta veri karar veremediği için küçük bir
"tercih" ekliyoruz:

$$\ln\kappa \sim \mathcal{N}(\ln 10,\ 2^2), \qquad \ln r \sim \mathcal{N}(\ln 30,\ 2^2)$$

$m$ ve $\mu$'ye önsel yok; onlara veri zaten karar veriyor. Tahmin artık **MAP (en büyük sonsal)**: olabilirlik ile
önselin çarpımını en büyük yapan nokta. Logaritmada bu bir toplamdır:

$$\hat\theta_{\text{MAP}} = \arg\max_\theta \Big[\ \ell(\theta) \;-\; \tfrac{1}{2}\Big(\tfrac{\ln\kappa - \ln 10}{2}\Big)^2 \;-\; \tfrac{1}{2}\Big(\tfrac{\ln r - \ln 30}{2}\Big)^2\ \Big]$$

**Ridge regresyonu bağlantısı.** Ceza terimleri ikinci dereceden; bu, ridge regresyonundaki L2 cezasıyla aynı
fikirdir. Ceza fonksiyona sabit bir eğrilik ($1/\sigma^2 = 0{,}25$) ekler; düz yöndeki sıfıra yakın özdeğer
sıfırdan uzaklaşır ve optimizasyonun durduğu nokta tek ve kararlı olur (Bölüm 4.3 tablosu).

**Önsel neden veriyi ezmiyor?** Olabilirlik $n$ üyenin toplamıdır, önsel tek bir terimdir. Üye sayısı arttıkça
olabilirliğin eğriliği $n$ ile büyür, önselinki sabit kalır. 29 üyede önsel düz yönü sabitler; 40.000 üyede
etkisi görünmez olur. Ölçüm: 40.000 müşterili geri kazanım testinde parametre hataları eski kodda
$r$ −%0,91, $\alpha$ −%1,31, $a$ +%0,51, $b$ +%3,21; yeni kodda −%0,90, −%1,30, +%0,49, +%3,18.

**Sayılarla:** Bölüm 4.2'deki örnekte $\kappa = 53$'ten $\kappa = 100.000$'e gitmek olabilirliği 0,45 nat iyileştirir,
ama önsel cezasını $\tfrac12\big(\tfrac{\ln 10^5-\ln 10}{2}\big)^2 - \tfrac12\big(\tfrac{\ln 53-\ln 10}{2}\big)^2 \approx 10{,}6 - 0{,}35 = 10{,}25$
nat artırır. Önsel kazanır, $\kappa$ 53'te kalır. Veri gerçekten büyük $\kappa$ isteseydi (yüzlerce üye ve net bir
sinyal), olabilirlik farkı 10 nat'ı kolayca aşardı.

**$\sigma = 2$ ne kadar "zayıf"?** $\pm 2\sigma$ aralığı $\kappa$ için 0,2 ile 550, $r$ için 0,5 ile 1.600 arasıdır.
Yani önsel neredeyse her makul değere izin verir; yalnızca "sonsuza kaçma"yı engeller.

### 4.6 Önselin merkezini deneyle seçmek

Merkezleri ($\kappa = 10$, $r = 30$) sezgiyle değil deneyle seçtik:

- 6 sentetik senaryo (S0–S5, Bölüm 8), 3 stüdyo büyüklüğü (30, 80, 200 müşteri), 40'tan fazla önsel ayarı.
- Seçim 100 rastgele tohumla yapıldı, sonuç **bağımsız 100 yeni tohumla** doğrulandı. (Tohum, rastgele sayı
  üretecinin başlangıç değeridir; farklı tohum = farklı sahte stüdyo.) Aynı veriyle hem seçip hem ölçmek,
  sınava çalıştığın soruları sınavda görmek gibidir; bağımsız tohumlar bunu önler.
- Ölçüt: **Brier puanı**, yani tahmin edilen olasılık ile gerçekleşen sonuç (1 = hayatta, 0 = değil) arasındaki
  farkın karesinin ortalaması. Brier bir **uygun puanlama kuralıdır**: en iyi puanı, gerçek inancını söyleyen
  tahminci alır. "Abartılı emin" olmak ödüllendirilmez.

**İlk sezgi yanlış çıktı.** İlk taslakta $\kappa = 100$, $r = 1$ vardı. Müşterilerinin %55'i tek seferlik olan
senaryoda (S5) bu önsel, modeli "tek seferlikler bıraktı" yerine "tek seferlikler çok yavaş geliyor" açıklamasına
itti. 30 müşteride Brier 0,081'den 0,398'e kötüleşti. Deney olmasa bu hata koda girecekti.

Seçilen önselin eski koda (saf MLE) göre Brier farkı ($\times 10^{-3}$, eksi iyi demek, ± standart hata):

| Önsel | 30 müşteri | 80 müşteri | 200 müşteri |
|---|---|---|---|
| İlk taslak ($\kappa=100$, $r=1$) | +55,4 ± 6,6 (kötü) | +20,7 ± 4,3 (kötü) | −0,1 ± 0,3 |
| Seçilen ($\kappa=10$, $r=30$), seçim tohumları | −0,9 ± 1,4 | −0,4 ± 0,9 | **−0,59 ± 0,04** |
| Seçilen, bağımsız doğrulama tohumları | −2,0 ± 1,1 | +0,9 ± 1,6 | **−0,55 ± 0,04** |

Seçilen önsel hiçbir büyüklükte anlamlı biçimde kötü değil, 200 müşteride anlamlı biçimde iyi.
**Bilinen bedel:** gelme hızları çok farklı üyelerden oluşan veride ($r = 0{,}5$) 30 müşteride Brier
$+12{,}7\times10^{-3}$ kötüleşiyor. Daha agresif seçenekler bu bedeli ikiye katladığı için en kötü durumu en küçük
tutan dengeli seçim yapıldı.

### 4.7 Düzeltme 3: sayısal analiz dersleri

Optimizasyon (en iyi noktayı bulma) scipy'ın L-BFGS-B yöntemiyle yapılır. İki tuzak bulundu:

1. **İleri fark türevi.** Optimizasyon türev ister; scipy varsayılan olarak türevi $\frac{f(\theta+h)-f(\theta)}{h}$
   ile yaklaşıklar. Hatası $O(h)$'dir. Düz bölgede gerçek türev zaten çok küçük olduğundan bu hata türevin
   **işaretini** bile çevirebilir ve optimizasyon yanlış noktada "başarıyla bitti" der. Sentetik stüdyoların
   20'de 6'sında oldu; Riskteki Para %10–55 şişti. **Merkezi fark** $\frac{f(\theta+h)-f(\theta-h)}{2h}$ hatayı
   $O(h^2)$'ye indirir (Taylor açılımında birinci dereceden hata terimleri birbirini götürür). Sonra 4.000 fitte
   yanlış bitiş 0 oldu.
2. **İki tepe.** Tek seferlikler ile çok sık gelenlerin karıştığı veride amaç fonksiyonunun iki yerel tepesi var:
   "tek seferlikler bıraktı" ve "tek seferlikler hayatta ama yavaş". Tek başlangıç bazen alçak tepede kalıyordu
   (tek seferliklere $P = 1$). Çözüm: ikinci başlangıç noktası ($\mu$ = tek seferlik payı, $\kappa$ küçük) ve iki
   sonuçtan iyi olanı almak. İki başlangıçla doğru tepe 40 nat daha iyi ve tek seferliklere $P \approx 3\times10^{-8}$.
   Gerçekçi 240 veri setinin yalnızca 1'inde ikinci başlangıç kazandı; yani maliyet düşük, sigorta değerli.

**Sonuç (29 üyeli test, 10 tekrar):** $\kappa$ artık 53,08'de sabit, $r$ 389,8'de sabit. Bir üyenin
$P(\text{hayatta})$ değerindeki oynama 0,049'dan 0,00000001'e indi.

---

## 5. Yenileme olasılığı: kesin formül

$P(\text{hayatta})$ "şu an" ile ilgilidir. Stüdyonun asıl sorusu "paket bitince yenileyecek mi"dir. Tanımımız:
**üye paketi bittiği anda hâlâ hayattaysa yeniler.** (Bu davranışsal bir ilk sürümdür; gerçek yenileme verisiyle
kalibre edilmedi, Bölüm 10.)

Model şöyle (`analitik/yenileme.py`):

1. **Şu an hayatta mı?** $P(\text{hayatta})$ olasılıkla evet.
2. **Bu üyenin kendi $\lambda$ ve $p$'si.** Üyenin geçmişini gördükten sonra (sonsal dağılım):
   $\lambda \sim \text{Gamma}(r+x,\ \alpha+T)$, $p \sim \text{Beta}(a,\ b+x+1)$.
   Türetme: "hayatta + bu veri" olabilirliği $(1-p)^{x+1}\lambda^x e^{-\lambda T}$; önsellerle çarpınca
   $\lambda$ ve $p$ ayrı çarpanlara ayrılır ve tanıdık dağılımlar çıkar (**eşlenik önsel**: önsel ile sonsal aynı
   aileden). Gelme sayısı $x$, Gamma'nın şeklini büyütür (daha emin oluruz); gözlem süresi $T$ oranını büyütür.
3. **Paketin geri kalanı.** Kalan $w$ günde $K \sim \text{Poisson}(\lambda w)$ ziyaret gelir; üye bunların
   hepsinden sonra bırakmazsa, yani $(1-p)^K$ olasılıkla, paket sonunda hâlâ hayattadır.
   - Giriş bazlı pakette son kullanma yoksa üs kalan hak sayısı $R$'dir; varsa $\min(K, R)$.

Yani $P(\text{yenileme}) = P(\text{hayatta}) \cdot E\big[(1-p)^{\text{üs}}\big]$. Kısaltmalar: $s = r + x$,
$\beta = \alpha + T$ ve $M(k) = E[(1-p)^k] = B(a,\ b+x+1+k) / B(a,\ b+x+1)$ (Beta fonksiyonu oranı). Beklenti
üç paket türünde de kapalı biçimde hesaplanır:

- **Süre bazlı paket ($D$ gün kaldı):** Önce $\lambda$ üzerinden: Gamma'nın moment üreten fonksiyonu
  $E[e^{-\lambda p D}] = (1 + pD/\beta)^{-s}$ verir. Sonra $p$ üzerinden: Euler integrali bu beklentiyi
  hipergeometrik fonksiyona çevirir:
  $$E\big[(1-p)^K\big] = {}_2F_1\big(s,\ a;\ a+b+x+1;\ -D/\beta\big).$$
  Sayısal kararlılık için Pfaff dönüşümüyle argüman $[0, 1)$ aralığına taşınarak hesaplanır.
- **Giriş bazlı, son kullanma yok:** $M(R)$.
- **Giriş bazlı, son kullanma $E$ gün sonra:** $\lambda$'yı integralle çıkarınca $K$ negatif binom dağılımına
  uyar: $K \sim \text{NBD}\big(s,\ \theta = \beta/(\beta + E)\big)$ (Gamma karışımlı Poisson). O zaman
  $$E\big[(1-p)^{\min(K,R)}\big] = \sum_{k<R} P(K=k)\, M(k) + P(K \ge R)\, M(R).$$

**Örnek** (Bölüm 3.3 parametreleri, paketin bitmesine 20 gün): Ayşe $P(\text{hayatta}) = 0{,}98$,
$P(\text{yenileme}) = 0{,}96$. Burak $0{,}14$ ve $0{,}14$ (kesin değer 0,1395).

### 5.1 Simülasyondan kesin formüle: Rao-Blackwell

İlk sürüm (v2'ye kadar) bu beklentiyi **Monte Carlo** ile hesaplıyordu: üyenin geleceğini 2.000 kez "oynatıp"
kaçında hayatta bittiğini sayıyordu. "Bunun kapalı formülü yok" diye düşünmüştük; yanlışmış.

**Rao-Blackwell teoremi:** bir tahmincide rastgele bir çekilişi, o çekilişin koşullu beklentisiyle değiştirmek
varyansı asla artırmaz (toplam varyans formülü: $\operatorname{Var} X = E[\operatorname{Var}(X\mid Y)] +
\operatorname{Var}(E[X\mid Y])$, ilk terimi atıyoruz). İlk adım, "şu an hayatta mı" yazı-turasını olasılığıyla
değiştirmekti: $\hat P = p_{\text{aktif}} \cdot \frac1N \sum_j (1-p_j)^{K_j}$. Bu, demo paketlerinde standart
sapmayı yaklaşık beşte birine indirdi. Aynı hamleyi $K$, $\lambda$ ve $p$ için de yapınca geriye hiç rastgelelik
kalmıyor: varyans tam sıfır. Bunu mümkün kılan, önsellerin eşlenik olmasıdır (Gamma-Poisson → negatif binom,
Beta momentleri → Beta fonksiyonu).

**Ne değişti (model sürümü `mbgnbd-map-v3`, K61):**
- Eski Monte Carlo hatası paket başına $\sqrt{P(1-P)/N}$, $N = 2000$'de en fazla ±1,1 puandı; artık 0.
- Aynı veri her zaman bit bit aynı sonucu verir; tohuma (rastgele sayı başlangıcına) gerek kalmadı.
- Çok sessiz bir üyede eski yöntem 2.000 oynatmanın hiçbirinde "aktif" çekmeyip $P(\text{yenileme}) = 0$
  diyebiliyordu (K60 hatasının tetikleyicisi). Kesin formül, $P(\text{hayatta}) > 0$ iken her zaman
  $0 < P(\text{yenileme}) \le P(\text{hayatta})$ verir.
- Doğrulama: formül 300 rastgele parametre setinde 200.000 oynatmalı simülasyonla tutuyor (en büyük sapma 3,7
  standart hata; 300 normal değişkenin beklenen en büyüğü ≈ 3); süre bazlı formül tek boyutlu sayısal integralle
  $10^{-10}$ düzeyinde aynı. Simülasyon kodu, testlerde bu karşılaştırma için referans olarak duruyor.
- Sonuç değişmedi, yalnızca gürültü gitti: S6 backtest AUC 0,8271 → 0,8272, Riskteki Para hatası −%13,19 → −%13,19.
  Demo, 45 günlük Riskteki Para: Butik Reformer 22.359,40 → 22.051,95 TL (−%1,4), Denge Pilates −%0,4; ikisi de
  eski yöntemin tohumdan tohuma oynamasının içinde.

---

## 6. Riskteki Para

$$\text{Riskteki Para}_{\text{paket}} = \big(1 - P(\text{yenileme})\big) \times \text{paket fiyatı}$$

Bu, o paketten **beklenen kayıp cirodur**. Stüdyonun toplam Riskteki Parası bunların toplamıdır. Toplamın anlamlı
olmasının nedeni **beklentinin doğrusallığıdır**: rastgele değişkenler bağımsız olmasa bile
$E[\sum X_i] = \sum E[X_i]$. Yani "her paketin beklenen kaybını topla" ile "toplam kaybın beklentisi" aynı şeydir.

Örnek: 2.500 TL'lik paketi olan Burak için $(1 - 0{,}14) \times 2500 = 2.150$ TL; Ayşe için
$(1-0{,}96)\times 2500 = 100$ TL. Panel bu tutarları büyükten küçüğe sıralar. Böylece stüdyo sahibi sınırlı
zamanını en çok parayı kurtaracağı üyeye harcar.

Veritabanında olasılık 4 haneye (`numeric(5,4)`), tutar kuruşa yuvarlanır; hesap kodu ve SQL aynı yuvarlamayı yapar
(`analitik/riskteki_para.py`).

---

## 7. "Neden riskli?" açıklaması

Bir sayı tek başına güven vermez; stüdyo sahibi "neden?" diye sorar. Yenileme olasılığını iki çarpana ayırıyoruz
(`analitik/aciklama.py`):

$$P(\text{yenileme}) = \underbrace{P(\text{şu an aktif})}_{p_{\text{aktif}}} \times \underbrace{P(\text{sürdürme} \mid \text{aktif})}_{q}$$

Logaritma alınca çarpım toplama döner: $-\ln P(\text{yenileme}) = A + B$, burada $A = -\ln p_{\text{aktif}}$
(sessizlikten gelen risk) ve $B = -\ln q$ (kalan sürede bırakma riskinden gelen risk). Hangisi büyükse ana neden odur:

- $A \ge B$: **sessizlik.** "Normalde ~7 günde bir geliyor; 45 gündür gelmiyor (normalin 6,6 katı)."
  Normal aralık $= (\text{son} - \text{ilk ziyaret}) / (\text{ziyaret sayısı} - 1)$. Aktif bir üyenin $k$ normal aralık
  boyunca hiç gelmeme olasılığı Poisson'dan yaklaşık $e^{-k}$'dır; $k = 6{,}6$'da bu binde 1,4.
  Normal aralık yalnızca en az 4 ziyaret varsa söylenir, çünkü ortalamanın göreli hatası yaklaşık
  $1/\sqrt{n-1}$'dir (3 ziyarette %71, kabul edilemez).
- $B > A$: **kalan süre / kalan hak.** "Şu an düzenli geliyor; risk, paketin bitmesine kalan 60 günde bırakma
  ihtimalinden."

**Sadakat kuralı:** açıklama yalnızca modelin gerçekten kullandığı bilgiden türetilir. Modelde olmayan bir sinyal
("fiyattan şikâyet etti" gibi) asla yazılmaz.
**Güvenilirlik eşiği:** $q = P(\text{yenileme}) / p_{\text{aktif}}$, veritabanında 4 haneye yuvarlanmış iki sayıdan
hesaplanır. $p_{\text{aktif}} < 0{,}05$ iken bu oran anlamsızlaşır (ör. 0,0000 / 0,0002); bu durumda ayrıştırma
gösterilmez (K63). v2'ye kadar asıl neden Monte Carlo hatasıydı.

---

## 8. Doğrulama: model gerçekten işe yarıyor mu?

### 8.1 Nasıl ölçtük: backtest

**Backtest**, geçmişte bir noktada durup "o gün modeli çalıştırsaydık ne derdi" diye bakmak, sonra gerçekte ne
olduğuyla karşılaştırmaktır. Sentetik veride "gerçek" bilinir (üreteç kimin ne zaman bıraktığını kaydeder), bu
yüzden kesin ölçüm yapılabilir. Kurulum (`docs/backtest-sonuclari.md`): her senaryoda 20 tohum × 2.000 müşteri,
2 yıl; model ilk 18 ayla eğitilir, son 6 ayda sınanır.

İki ölçüt:

- **AUC (ayrım gücü):** rastgele bir "hayatta" ve rastgele bir "ölü" üye seçersek, modelin hayatta olana daha yüksek
  olasılık verme olasılığı. 0,50 yazı-tura, 1,00 kusursuz.
- **Brier (kalibrasyon dahil):** Bölüm 4.6'daki puan; küçük daha iyi. AUC yalnızca sırayı ölçer; Brier
  "%30 dediğinde gerçekten %30'u mu oluyor" sorusunu da ölçer.

Senaryolar, modelin varsayımlarını bilerek bozar: S0 hiçbir şey bozmaz; S1 düzenli aralıklar (Poisson değil);
S2 grup karışımı; S3 ziyaretten bağımsız sürekli zamanda bırakma; S4 harcama ile sıklık ilişkili; S5 güzellik salonu
(%55 tek seferlik); S6 stüdyo yenilemesi.

### 8.2 En önemli bulgu: BG/NBD'nin kör noktası

| Senaryo | M0 (basit kural) AUC | M1 (BG/NBD) AUC | M3 (MBG/NBD) AUC | M1 Brier | M3 Brier |
|---|---|---|---|---|---|
| S0 | 0,911 | 0,935 | 0,926 | 0,082 | 0,087 |
| S2 | 0,953 | 0,698 | 0,953 | 0,177 | 0,078 |
| S3 | 0,943 | 0,836 | 0,958 | 0,117 | 0,073 |
| **S5** | 0,961 | **0,229** | **0,977** | 0,596 | 0,057 |

S5'te BG/NBD'nin AUC'si **0,23**: yazı-turadan (0,50) **kötü**. Sebep Bölüm 3.2'deki göstergedir: müşterilerin
%55'ini oluşturan tek seferliklerin hepsi ölü, ama BG/NBD hepsine $P = 1$ veriyor; yani en emin olduğu grup tam ters.
MBG/NBD aynı veride 0,98 alıyor. Varsayımların bozulmadığı S0'da ise iki model neredeyse eşit; yani MBG/NBD'yi
seçmenin bedeli küçük, getirisi büyük. Ürüne bu yüzden MBG/NBD (M3) girdi.

### 8.3 AUC yüksek ama kalibrasyon kötü olabilir

M0, kişinin kendi ziyaret aralıklarının Normal dağıldığını varsayan basit kuraldır (projenin ilk sürümü). AUC'si
iyi görünüyor (S0'da 0,91), ama S0 güvenilirlik tablosunda "%0–10 hayatta" dediği 12.558 müşterinin gerçekte
**%30'u** hayattaydı. MBG/NBD aynı kutuda %1,8 dedi, gerçek %2,1 çıktı. Brier: M0 0,240, M3 0,087. Ders: sıralama
iyi olabilir ama olasılığın kendisi yanlışsa Riskteki Para (olasılık × fiyat) yanlış çıkar. Bu yüzden iki ölçüte
birden bakıyoruz.

### 8.4 Stüdyo senaryosu (S6): ürünün asıl ölçümü

20 tohum × 1.500 üye, 2 yıl; kalibrasyon tarihinde aktif olup 60 gün içinde biten paketler değerlendirildi.

| | M3 + yenileme formülü | Basit kural ("son 21 günde ≤ 1 giriş") |
|---|---|---|
| AUC | **0,827 ± 0,034** | 0,720 ± 0,021 |
| Brier | **0,153** | 0,241 |
| Riskteki Para hatası | **−%13,2 ± 4,5** | −%36,0 ± 4,8 |

**−%13 nereden geliyor? (çıkarım, ölçülmedi):** S6 üretecinde hayatta olan üye bile %10 olasılıkla yenilemiyor
(fiyat, taşınma gibi davranış dışı nedenler). Model bunu bilmez; "hayattaysa yeniler" der. Gerçek yenileme oranı
0,582 ise hayatta olanların oranı yaklaşık $0{,}582/0{,}9 \approx 0{,}647$, bu nedenle kaybolan paketlerin
yaklaşık $0{,}647 \times 0{,}1 / 0{,}418 \approx$ %15'i model dışı nedenden geliyor. Bu, −%13'lük eksik tahminin
neredeyse tamamını açıklıyor (paket sayısıyla, fiyat ağırlığı olmadan kaba hesap). CLAUDE.md'deki 5c satırı da
nedeni bu varsayıma bağlıyor; buradaki hesap, büyüklüğün tuttuğunu gösteriyor. Yani modelin davranışsal kısmı iyi
çalışıyor; eksik kalan, verisi olmayan kısım. Gerçek veride bu oran kalibrasyonla öğrenilecek (5c).

### 8.5 (μ, κ) düzeltmesi büyük veride hiçbir şeyi bozmadı

Backtest yeni kodla baştan üretildi. Kabul ölçütü her senaryoda AUC ve Brier farkı ≤ 0,005 idi. Ölçülen en büyük
AUC farkı 0,00017, Brier farkı 0,0004. S6 AUC 0,8272 → 0,8271; Riskteki Para hatası −13,17 → −13,19
(kullanıcının Windows makinesinde). Bu beklenen sonuçtur: 2.000 müşteride veri önseli bastırır (Bölüm 4.5).
Önselin işe yaradığı yer küçük stüdyodur.

Demo stüdyolarda etki: Butik Reformer 45 günlük Riskteki Para 24.287 → 23.107 TL (−%4,9), Denge Pilates +%0,1.
Riskli üye listesinin sırası değişmedi.

---

## 9. Mühendislik ve sayısal dersler

1. **Zaman ötelemesine değişmezlik.** Model zamanı yalnızca farklar olarak görür ($x$, $t_x$, $T$, kalan gün).
   Bütün tarihleri $d$ gün kaydırmak bu farkların hiçbirini değiştirmez; bu yüzden canlı demo her gece yeniden veri
   üretmek yerine tarihleri bugüne kaydırır ve $P(\text{hayatta})$ birebir aynı kalır. v3'ten beri $P(\text{yenileme})$
   de birebir aynı kalır (kesin formül; v2'de tohum hesaplama tarihine bağlı olduğu için Monte Carlo hatası kadar
   oynuyordu).
2. **Kanonik sıra.** Olabilirlik bir toplamdır; matematikte toplamanın sırası önemsizdir ama bilgisayarda değildir
   (kayan nokta toplaması birleşmeli değildir: $(a+b)+c \ne a+(b+c)$ olabilir). Düz sırtta bu en son basamak farkı
   bile parametreyi uzaklara taşıyordu. Fit, girdiyi her zaman $(x, t_x, T)$ sırasına dizer; aynı veri hangi
   sırayla gelirse gelsin sonuç bit bit aynıdır. Bu **belirlenimciliği** sağlar, tanımlanabilirliği değil; onu
   önsel çözdü.
3. **Linux ve Windows farkı.** Canlı sitede (Linux) Butik Reformer'ın 45 günlük Riskteki Parası 22.379,85 TL,
   yerel bilgisayarda (Windows) 22.380,70 TL çıkmıştı. Aynı veriye $10^{-15}$ göreli gürültü eklemek eski kodda bu
   toplamı 180 TL oynatıyordu; yeni kodda 0 TL. Kesin formülle (v3) simülasyon kaynaklı kuruş farkları da kalktı:
   demo toplamları Windows ve Linux'ta kuruşu kuruşuna aynı çıktı (Butik Reformer 22.051,95 TL, 2026-10-04).
4. **Tekrarlanabilirlik testi, model hatası buldu.** Zayıf tanımlanabilirliği bir istatistik testi değil, "dışarı
   yaz, geri oku, aynı mı?" diyen bir yazılım testi yakaladı. Ders: sonuçları bit bit karşılaştıran testler,
   matematikteki kararsızlığın erken uyarı sistemidir.
5. **"Başarılı" bitiş kanıt değildir.** Optimizasyonun "başarıyla bitti" demesi, doğru noktada olduğunu
   göstermez (Bölüm 4.7). Kontrol: farklı başlangıçlar, merkezi fark, sonucu bilinen veride geri kazanım testi.

---

## 10. Sınırlar ve açık konular (dürüstlük bölümü)

1. **Yalnızca sentetik veri.** Bütün ölçümler yapay veride. Gerçek veride ilk ölçüm bir firmanın anonimleştirilmiş
   verisiyle yapılacak (4b-2): zaman bölmeli test (ilk 18 ayla eğit, son 6 ayda sına).
2. **Yenileme kalibre edilmedi.** "Hayattaysa yeniler" varsayımı davranış dışı nedenleri yok sayar (Bölüm 8.4).
   Gerçek yenileme verisi gelince kalibrasyon eklenecek (5c).
3. **Önsel merkezleri sentetik veride seçildi.** Gerçek veride yeniden ayarlanmalı.
4. **Asgari veri koruması (8a ile eklendi, 2026-10-10).** En az 30 üye ikinci kez gelmediyse ya da geçmiş 60 günden
   kısaysa zayıf önselin yerine diğer işletmelerden öğrenilmiş önsel kullanılır ve sonuç "ön tahmin" diye işaretlenir.
   Önsel bugün 5 sentetik demo işletmesinden öğrenildi. Ayrıntı: `docs/adim-8a-tasarim.md`.
5. **Gelecek ziyaretleri fazla tahmin.** S5'te M3 gelecek ziyaretleri %11, S2'de seyrek gelenlerde %21 fazla
   tahmin etti. Yenileme olasılığı aynı eğilimi taşıyabilir.
6. **Parametre belirsizliği yenileme olasılığına taşınmıyor.** Hesap tek bir MAP noktası kullanır; "parametrelerden de
   emin değiliz" bilgisi kayboluyor. Küçük stüdyoda olasılıklar olması gerekenden biraz daha emin görünebilir.
   Çözüm adayı tam Bayes (parametreleri de örneklemek).
7. **Rao-Blackwell: yapıldı (v3, Bölüm 5.1).** Simülasyonun yerini kesin formül aldı; gürültü sıfır, sonuçlar aynı.
8. **Gamma-Gamma (harcama modeli).** Backtest'te ciro tahmini için kullanılır, stüdyo akışında kullanılmaz (paket
   fiyatı bilinir). Onda da benzer bir sırt var ($q \to \infty$); dokunulmadı.
9. **Sentetik üretici kusurları.** Butik Reformer'da üyelerin %2'si günde birden fazla geliyor; demo sayıları bunu
   içerir.

---

## 11. Mülakat ve sunum için kısa cümleler

- **Tek cümle:** "Tekrarlanabilirlik testi bir yazılım hatası değil, modelin zayıf tanımlanabilirliğini ortaya
  çıkardı; belirlenmeyen yönü yeniden parametreleyip zayıf bir önselle sabitledim ve önselin merkezini bağımsız
  tohumlarla doğrulanmış bir deneyle seçtim."
- **Model seçimi:** "Ders kitabındaki BG/NBD, güzellik salonu senaryosunda AUC 0,23 aldı, yazı-turadan kötü, çünkü
  bir kez gelip kaybolanları sonsuza dek hayatta sayıyor. MBG/NBD aynı veride 0,98 aldı."
- **Matematik geçmişinin avantajı:** düz sırt = Hessian'ın sıfıra yakın özdeğeri; önsel = ridge'deki L2 cezası, o
  yöne $1/\sigma^2$ eğrilik ekler ve veri büyüdükçe etkisi kaybolur; ileri fark $O(h)$, merkezi fark $O(h^2)$;
  Brier uygun puanlama kuralıdır; Riskteki Para toplamı beklentinin doğrusallığına dayanır.
- **Rao-Blackwell:** "Yenileme olasılığını 2.000 oynatmalı simülasyonla hesaplıyordum. Rao-Blackwell ile zarları koşullu
  beklentileriyle değiştirdim; sonuna kadar götürünce eşlenik önseller sayesinde kapalı formül çıktı (hipergeometrik
  fonksiyon ve negatif binom). Gürültü sıfır, sonuçlar aynı; 'kapalı formül yok' varsayımım yanlışmış."
- **Dürüstlük cümlesi:** "Kodu bir yapay zekâ ajanıyla yazdım; tasarım ve matematik kararları benim, her parçasını
  açıklayabilirim. Sonuçlar sentetik veride; gerçek veride ilk ölçüm pilotun işi."

---

## Ek A. Sembol sözlüğü

| Sembol | Okunuşu | Anlamı |
|---|---|---|
| $x$ | | Tekrar ziyaret sayısı |
| $t_x$ | | Son ziyaretin ilk ziyarete göre günü |
| $T$ | | İlk ziyaretten bugüne gün |
| $\lambda$ | lambda | Bir üyenin günlük gelme hızı |
| $p$ | | Bir üyenin her ziyaretten sonra bırakma olasılığı |
| $r, \alpha$ | r, alfa | Gelme hızlarının Gamma dağılımı parametreleri |
| $a, b$ | | Bırakma olasılıklarının Beta dağılımı parametreleri |
| $m = r/\alpha$ | | Ortalama gelme hızı |
| $\mu = a/(a+b)$ | mü | Ortalama bırakma olasılığı |
| $\kappa = a+b$ | kappa | Bağlılıktaki türdeşlik (büyük = herkes benzer) |
| $\theta$ | teta | Optimizasyon koordinatları $(\ln m, \ln r, \operatorname{logit}\mu, \ln\kappa)$ |
| $\ell$ | | Log-olabilirlik |
| $\sigma$ | sigma | Önselin standart sapması (burada 2) |
| $N$ | | Eski simülasyon sayısı (2.000; v3'te kullanılmıyor) |
| $K$ | | Kalan sürede gelecek ziyaret sayısı (rastgele değişken) |
| $B(\cdot,\cdot)$ | Beta fonksiyonu | $M(k)$ oranında kullanılır |
| ${}_2F_1$ | hipergeometrik fonksiyon | Süre bazlı paketin kesin formülü |

## Ek B. Kaynaklar

- Fader, P. S., Hardie, B. G. S. & Lee, K. L. (2005). "Counting Your Customers" the Easy Way: An Alternative to the
  Pareto/NBD Model. *Marketing Science*, 24(2), 275–284.
- Batislam, E. P., Denizel, M. & Filiztekin, A. (2007). Empirical validation and comparison of models for customer
  base analysis. *International Journal of Research in Marketing*, 24(3), 201–209.
- Depo belgeleri: `docs/adim-5-6-tasarim.md` (model seçimi, backtest), `docs/adim-5b-tasarim.md` (yenileme
  modeli), `docs/adim-9-tasarim.md` (açıklama, zaman kaydırma), `docs/adim-mu-kappa-tasarim.md` (K42–K52),
  `docs/adim-rao-blackwell-tasarim.md` (K61–K63), `docs/backtest-sonuclari.md`.

## Ek C. Bu rapordaki yeni hesapların yeniden üretimi

Bölüm 3.3 örnekleri, 4.2 profil olabilirliği ve 4.3 Hessian özdeğerleri bu rapor için
`b8c5ea5` üzerinde, `tests/test_analitik_map.py::_a_verisi_ozellikleri` verisiyle Linux'ta hesaplandı ve Windows'ta
aynı sonuçlarla doğrulandı (Hessian:
$h = 10^{-3}$ ile merkezi ikinci fark, toplam negatif log-olabilirlik). Diğer bütün sayılar depo belgelerinden alındı.
Bölüm 5 örnekleri v3 kodu üzerinde 2026-10-04'te hesaplandı (Linux bulut ve Windows'ta aynı); 5.1'deki doğrulama
ölçümleri (300 rastgele parametre seti, standart sapmanın beşte birine inmesi) Linux bulutta yapıldı, Windows'ta
testler aynı karşılaştırmayı geçiyor.
