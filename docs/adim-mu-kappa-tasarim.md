# Adım: Model düzeltmesi (μ, κ): tasarım

İlk taslak 2026-10-02, son hâl ve uygulama 2026-10-03. Durum: **Uygulandı.**
Her karar deneyle seçildi. Bölüm 1–3'teki deney sayıları kodun bir kopyası üzerindeki Linux prototipinden
(Python 3.11, numpy 2.4, scipy 1.17); uygulamanın Windows ölçümleri Bölüm 6'da.

## 1. Sorun
MBG/NBD'nin dört parametresi var: ziyaret hızı için Gamma(r, α), bırakma olasılığı için Beta(a, b).
Veri ikisini iyi belirliyor: ortalama ziyaret hızı **m = r/α** ve ortalama bırakma olasılığı **μ = a/(a+b)**.
"Üyeler birbirinden ne kadar farklı" bilgisini ise, yani **κ = a+b**'yi ve küçük, türdeş veride **r**'yi, neredeyse hiç
belirlemiyor. Olabilirlik o yönde düz bir sırt oluşturuyor. Bu yüzden 1e-15'lik kayan nokta farkları bile sonucu taşıyor.

Ölçüm (29 üyeli test verisi, `tests/test_ice_aktarma_db.py` a_verisi tarifi; T'ye 10 kez 1e-15 göreli gürültü):
| | κ aralığı | r aralığı | Bir üyenin P(hayatta) farkı |
|---|---|---|---|
| Eski kod (Linux) | 29 – 155.800 | 5.100 – 24.000 | 0,049 |
| Yeni kod (Linux) | 53,08 (sabit) | 389,8 (sabit) | 0,00000001 |

## 2. Neler denendi (özet)
- **Prototip:** İlk tasarım (K0 = 100, R0 = 1, tek başlangıç, ileri fark türevi) çalışan kod olarak yazıldı ve 56 analitik testte denendi.
- **Önsel seçimi:** 6 backtest senaryosu (S0–S5) ve 3 stüdyo büyüklüğü (30, 80, 200 müşteri) kullanıldı. Seçim
  100 tohumla yapıldı, sonuç bunlardan bağımsız **100 yeni tohumla** doğrulandı. Ek olarak S6, demo benzeri veri ve
  iki zorlama ailesi denendi. 40'tan fazla önsel ayarı karşılaştırıldı.
  - Ölçüt: kalibrasyon sonunda "gerçekten hayatta mı" sorusunda Brier ve log-kayıp. Bunlar uygun puanlama kuralları,
    yani dürüst olasılığı ödüllendiren puanlar.
- **Ürün etkisi:** S6 yenileme backtest'i ve Butik Reformer demo üreticisi 20 tohumla çalıştırıldı. Toplam Riskteki
  Para ve riskli üye listesi karşılaştırıldı.
- **Sağlamlık:** Beş büyüklükte (15–400) ve uç durumlarda denendi. Uç durumlara örnekler: herkes bir kez gelmiş;
  kimse bırakmıyor; tek üye; tek seferlikler ile çok düzenli üyelerin karışımı.

**İlk tasarımda bulunan üç gerçek hata (deneyler olmasa koda girecekti):**
1. **Önsel merkezleri (100, 1) zararlıydı.** Tek seferlik müşterisi çok olan veride (S5, %55 tek seferlik) model
   "tek seferlikler bıraktı" yerine "tek seferlikler yavaş geliyor" açıklamasını seçiyordu.
   - Brier, 30 müşteride 0,081'den 0,398'e, 80 müşteride 0,062'den 0,185'e kötüleşti.
2. **Türev gürültüsü.** scipy'ın varsayılan ileri fark türevi, r veya κ büyükken yön değiştiriyor. Optimizasyon yanlış
   noktada "başarıyla bitti" diyor.
   - S6'da 20 tohumun 6'sında, 40 demo stüdyosunun 3'ünde oldu. Riskteki Para %10–55 şişti.
3. **İki tepe.** Tek seferlikler ile ağır kullanıcıların karıştığı veride amaç fonksiyonunun iki tepesi var. Tek
   başlangıç bazen alçak olanda kalıyordu (tek seferliklere P(hayatta) = 1 veriyordu; doğrusu ≈ 0).

## 3. Kararlar

**K42 Yeniden parametreleme (yalnızca fit'in içinde).**
- Optimizasyon değişkeni: θ = (ln m, ln r, logit μ, ln κ).
- Dönüşüm: α = r/m, a = κ·expit(logit μ), b = κ·expit(−logit μ). Bu yazım 1e-15 hassasiyetle tersinir;
  (1−μ)·κ yazımı 1e-9'a kadar hata veriyor.
- Ters yön: logit μ = ln a − ln b, ln κ = ln(a+b), ln m = ln r − ln α.
- Dışarıya açılan `BGNBDParametreleri(r, alfa, a, b)` aynı kalır. p_hayatta, simülasyon ve panel kodu değişmez.

**K43 Kapsam: M3 (MBG/NBD) ve M1 (BG/NBD) birlikte; Gamma-Gamma (M2) kapsam dışı.**
- M1 ve M3 aynı `log_mle`'yi paylaşıyor; backtest de ikisini karşılaştırıyor.
- M2 stüdyo akışında kullanılmıyor, çünkü ziyaret tutarı 0.

**K44 Zayıf önseller: ln κ ~ Normal(ln 10, 2²), ln r ~ Normal(ln 30, 2²).**
- *κ = 10'un anlamı:* üyeler bağlılık bakımından belirgin biçimde farklı olabilir. Bu, "tek seferlik müşteri gerçekten
  bıraktı" açıklamasına izin verir.
- *r = 30'un anlamı:* üyelerin ziyaret hızları ortalamaya yakındır (değişim katsayısı 1/√30 ≈ 0,18). Paketli
  stüdyolarda bu makul bir varsayım.
- *Genişlik σ = 2:* ±2σ aralığı κ için 0,2–550, r için 0,5–1.600. Veri güçlü olduğunda veri kazanır.

Kanıt (S0–S5 birleşik, eski koda göre Brier farkı ×10⁻³, eşleştirilmiş, ± standart hata):
| Önsel | 30 müşteri | 80 müşteri | 200 müşteri |
|---|---|---|---|
| İlk taslak (κ=100, r=1) | +55,4 ± 6,6 (kötü) | +20,7 ± 4,3 (kötü) | −0,1 ± 0,3 |
| **Seçilen (κ=10, r=30)**, seçim tohumları | −0,9 ± 1,4 | −0,4 ± 0,9 | **−0,59 ± 0,04** (iyi) |
| **Seçilen**, bağımsız doğrulama tohumları | −2,0 ± 1,1 | +0,9 ± 1,6 | **−0,55 ± 0,04** (iyi) |
| Yalnız κ önseli (r'ye önsel yok) | +58,6 (kötü) | +24,9 (kötü) | (r sınıra kaçıyor, beklenen ziyaret NaN) |

- Seçilen önsel hiçbir büyüklükte eski koddan kötü değil; 200 müşteride anlamlı biçimde iyi.
- AUC 30 müşteride +0,002, hold-out ziyaret hatası da hafif iyileşiyor.
- S6 ve demo ailelerinde fark yok (±0,1×10⁻³).
- Doğru κ = 20 olan S0'da da, κ = 291 olan demo benzeri veride de çalışıyor.
- **Bilinen bedel:** Ziyaret hızları çok farklı olan veride (r = 0,5, zorlama ailesi) 30 müşteride Brier +12,7×10⁻³
  (taban 113). Daha agresif seçenekler (r = 100 ya da σ = 1,5), S0–S5'te biraz daha iyi ama bu bedeli ikiye
  katlıyor. Seçilen değer, en kötü durumu en küçük tutan dengeli seçim.

**K45 Tahmin yöntemi: MAP (en büyük sonsal).**
- Amaç = −(log-olabilirlik + log önsel) / n. Önsel toplam olabilirliğe bir kez eklenir.
- Üye sayısı arttıkça önselin etkisi kendiliğinden azalır. Kanıt: 40.000 müşterili BG/NBD geri kazanım testinde gerçeğe göre hatalar
  eski kodda r −%0,91, α −%1,31, a +%0,51, b +%3,21; yeni kodda −%0,90, −%1,30, +%0,49, +%3,18.
- Tam Bayes (parametre belirsizliğini simülasyona taşımak) bu adımda yok; Rao-Blackwell ile birlikte açık konu.

**K46 Optimizasyon ayarı: merkezi fark türevi + sıkı tolerans.**
- `log_mle`'ye isteğe bağlı bir `secenekler` argümanı eklenir. BG/NBD ve MBG/NBD
  `MAP_SECENEKLERI = {"jac": "3-point", "options": {"ftol": 1e-12}}` geçirir. Gamma-Gamma değişmez
  (ona uygulanınca backtest'te yedek devreye girdi).
- Kanıt: yanlış "başarılı" bitişler 4.000 fitte 0'a indi. Fit süresi yaklaşık 1,5 kat arttı (stüdyo başına ≈ 0,1 sn).
- Nelder-Mead yedeği kalır ama devreye girerse `RuntimeWarning` verir. Ölçülen hiçbir veride devreye girmedi.

**K47 İki başlangıç.** `map_iki_baslangic` yardımcısı MAP'i iki noktadan çözer ve amacı küçük olanı alır
(eşitlikte ilki).
- B1: mevcut başlangıç (r = 1, α = max(ort T, 1), a = b = 1). `baslangic` argümanı verilirse onun yerine geçer.
- B2: B1 sonucunun ln m ve ln r'si; logit μ = logit(x = 0 payı; 0,02–0,98 arasına kırpılmış); ln κ = −2.
- Kanıt: tek seferlik + ağır kullanıcı verisinde tek başlangıç 40 nat geride kalıyor (tek seferliklere P = 1).
  İki başlangıçla P = 3e-8 ve amaç 40 nat iyi. Gerçekçi veride (S0, S2, S5; 30 ve 80 müşteri; 240 veri seti) ikinci başlangıç yalnızca 1'inde kazanıyor;
  sonuç yine yalnızca verinin fonksiyonu.

**K48 Sınırlar ve boş girdi.**
- θ sınırları: ln m ∈ [−15, 10], ln r ∈ [−10, 15], logit μ ∈ [−20, 20], ln κ ∈ [−10, 15]. Gerçekçi veride optimum
  her sınırdan en az 8 birim içeride. logit μ = −20 yalnızca "kimse bırakmıyor" verisinde değiyor; doğru davranış.
- Boş girdide (n = 0) eski kod ZeroDivisionError veriyordu; artık anlaşılır bir ValueError verilir.

**K49 Model sürümü: `mbgnbd-sim-v1` → `mbgnbd-map-v2`.**
- Panel iki sürümü karıştırmaz. `v_yenileme_paneli` ve `v_sessiz_uyeler` her paket için en yeni satırı alır
  (`ORDER BY hesaplama_tarihi DESC, hesaplanma_zamani DESC LIMIT 1`, alembic/sql/0002 ve 0003).
- Aynı gün v1 ve v2 satırları birlikte olsa bile yeni olan görünür. Çift sayım yok, açıklama boş kalmaz.

**K50 Testler (yeni dosya `tests/test_analitik_map.py`; mevcut test dosyalarına dokunulmaz).**
| Test | Ne sınar | Eski kod | Yeni kod |
|---|---|---|---|
| a) Dönüşüm | θ ↔ (r, α, a, b) gidiş-dönüş < 1e-12 (değerler 10^±3) | – | geçer |
| b) Kararlılık | a_verisi tarifi + 10 gürültü: ΔP < 1e-4, ln κ ve ln r aralığı < 1e-3, yedek uyarısı yok | **kırmızı** (ΔP 0,049) | yeşil (ΔP 8e-9) |
| c) İki tepe | 15 tek seferlik + 15 ağır kullanıcı: tek seferliklerde P < 0,01, ağırlarda P > 0,99 | yeşil | yeşil (tek başlangıçlı ara sürüm kırmızı) |
| d) Yanlış bitiş koruması | S6 tohum 1/2/8: 15 < κ < 80 ve 0,04 < μ < 0,065; S5 tohum 0 (tam boy): κ < 1 | yeşil | yeşil (ileri farklı ara sürüm kırmızı) |
| e) Önsel | log_onsel yalnız ln κ ve ln r'ye bağlı; σ = ∞ önseli kapatır | – | geçer |
| f) Boş girdi | n = 0 → ValueError | ZeroDivisionError | geçer |

- Mevcut 543 testin hepsi değişmeden geçmeli; geri kazanım testleri dahil.
- Eskiden aralıklı düşen test 20 kez çalıştırılır. Bu kanıt değil, yalnızca sağlama: girdisi kanonik sıradan beri
  sabit. Asıl kanıt test b).

**K51 Backtest yeniden üretimi ve kabul ölçütü.** Önce eski kodla `raporlar/backtest-eski.md` üretilir, sonra yeni
kodla `docs/backtest-sonuclari.md`.
- Kabul: her senaryo (S0–S5) ve model (M1, M3) için ortalama AUC ve Brier farkı ≤ 0,005. S6 "Tümü" satırında M3-sim
  AUC farkı ≤ 0,005 ve Riskteki Para hata % farkı ≤ 1 puan.
- Prototipte ölçülen en büyük fark: AUC 0,002 (S6 12 Giriş), Brier 0,001. S6 Tümü AUC 0,827 → 0,827, Riskteki Para hatası
  −13,2 → −13,2. README'deki "AUC 0.83" ve "kural 0.72" ile CLAUDE.md ve docs/adim-7-tasarim.md'deki "%13" geçerli kalıyor.
- Sebep: 2.000 müşteride veri önseli bastırıyor. Önselin işe yaradığı yer küçük stüdyo.

**K52 Demo ve canlı yayın etkisi.** Ölçüm Butik Reformer üreticisi, 20 tohum üzerinde yapıldı:
- Tüm aktif paketlerin Riskteki Parası medyan −%2,3 (aralık −%5,6 ile −%0,8). Panelin 45 günlük toplamı medyan
  −%1,2 (−%7,5 ile +%0,7).
- Riskli listenin sırası 20 stüdyonun 19'unda aynı. Paket başına P(yenileme) en çok 0,10 değişiyor.
- Canlı demo (tohum 2026) 45 günlük toplamı yaklaşık −%2,6 değişir (22.656 → 22.075 TL; yerel benzetim).
- Canlıda değişiklik push'tan sonraki gece tazelemesinde (03:00) görünür; Render risk hesaplamaz.
- Linux ile Windows arasındaki 0,85 TL'lik fark için: aynı veriye 1e-15 gürültüyle 45 günlük toplamın oynaması
  eski kodda 180 TL, merkezi fark türevli MAP'te 0 TL (tohum 2026). Kuruşu kuruşuna eşitlik garanti değil: tek bir simülasyon çekilişi bir paketi
  0,0005 × fiyat oynatabiliyor.

## 4. Kapsam dışı (CLAUDE.md "Açık konular"a yazılır)
1. Önsel merkezlerinin gerçek veride ayarı: 4b-2'de zaman bölmeli testle.
2. Asgari veri koruması: herkes tek ziyaretli veya 1 günlük geçmişte model emin ama anlamsız cevap veriyor; eski kodda
   da böyle. Eşikler proje sahibinin kararı.
3. Gamma-Gamma'da benzer sırt (q → ∞); yalnızca backtest'te kullanılıyor.
4. Sentetik üretici: Butik Reformer'da üyelerin %2'si günde birden fazla ziyaret yapıyor (6,2/güne kadar).
5. Tam Bayes / Rao-Blackwell.

## 5. Matematik raporu için hikâye (mülakatta anlatılacak)
1. Tekrarlanabilirlik testi bir yazılım hatası değil, zayıf tanımlanabilirlik buldu: düz sırt, Hessian'ın bir
   özdeğerinin sıfıra yakın olması.
2. Yeniden parametreleme, iyi ve kötü belirlenen yönleri ayırdı.
3. Zayıf önsel, ridge regresyonundaki L2 cezası gibi o yöne eğrilik ekledi.
4. Önsel merkezini tahminle değil, bağımsız tohumlarla doğrulanmış out-of-sample Brier ile seçtik. İlk sezgimiz
   (κ=100, r=1) tek seferlik müşterisi çok olan işletmede zararlıydı. Bunu deney yakaladı.
5. Sayısal analiz dersi: ileri fark türevinin gürültüsü ve çok tepeli amaç, "başarılı" görünen yanlış sonuç
   üretebiliyor.

## 6. Sonuçlar (Windows, 2026-10-03)
Ortam: Python 3.14.6, numpy 2.5.2, scipy 1.18.1. Yerel panosu_test ve panosu_demo.

**Testler.** Tam takım 554 geçti (543 mevcut + 11 yeni). Eskiden aralıklı düşen test 20/20 geçti.
Tam takımda, backtest'te ve demo hesabında hiç `RuntimeWarning` yok (Nelder-Mead yedeği hiç devreye girmedi).

**Kararlılık (test b, 11 fit):**
| | P(hayatta) farkı | κ | r |
|---|---|---|---|
| MBG/NBD eski | 0,0297 | 28,6 – 3.880 | 9.713 – 24.003 |
| MBG/NBD yeni | 1,1e-8 | 53,08 | 389,81 |
| BG/NBD eski | 0,0155 | 74,5 – 2.637 | 8.380 – 24.071 |
| BG/NBD yeni | 2,1e-8 | 49,93 | 390,16 |

**Geri kazanım (BG/NBD, 40.000 müşteri, gerçeğe göre hata r, α, a, b):** eski −%0,82, −%1,19, +%0,59, +%3,19;
yeni −%0,90, −%1,30, +%0,47, +%3,16.

**Backtest (eski koda göre, 20 tohum).** S0–S5'te en büyük fark AUC 0,00017, Brier 0,00040 (S5 M1). S6 Tümü: M3-sim
AUC 0,8272 → 0,8271, Riskteki Para hatası −%13,17 → −%13,19. Kural modeli ve Gamma-Gamma birebir aynı.
S0'da M3 kestirimleri daha kararlı: a 3,56 ± 4,74 → 2,26 ± 1,07; b 95 ± 136 → 58 ± 31.

**Demo (yerel, 2026-10-03):**
| | Butik Reformer | Denge Pilates Stüdyosu |
|---|---|---|
| 45 günlük Riskteki Para | 24.286,75 → 23.106,95 TL (−%4,9) | 83.345,60 → 83.455,40 TL (+%0,1) |
| Tüm aktif paketler | 58.283,15 → 54.792,95 TL (−%6,0) | 164.511,60 → 164.656,60 TL (+%0,1) |
| İlk 10 riskli üye | 3/3 aynı, sıra aynı | 10/10 aynı, sıra aynı |
| En büyük P(yenileme) değişimi | 0,100 | 0,017 |

Butik Reformer küçük ve türdeş bir stüdyo; önselin en çok çalıştığı yer burası. Denge Pilates daha büyük; veri önseli
bastırıyor. Panel görünümleri aynı gün v1 ve v2 satırı varken her paket için yalnızca v2'yi seçti; çift satır, boş
açıklama ya da toplam hatası yok.
