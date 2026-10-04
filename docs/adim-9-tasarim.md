# Adım 9: Web paneli: tasarım ve kararlar

## KARARLAR (proje sahibi onayı, 2026-10-01; 9b kararları 2026-10-02)

**K1 Teknoloji:** Web paneli FastAPI'nin içinde Jinja2 şablonları + HTMX ile yapılır (Next.js değil). Tek dil, tek
proje, tek yayına alma. JSON API (Bearer) aynen kalır.

**K2 Geçmiş ayda aktif üye ve başabaş farkı:** Tamamlanmış (geçmiş) bir ayda başabaş farkı ORTALAMA aktif üyeyle
ölçülür: basabas_farki_ortalama = ortalama_aktif_uye − basabas_uye_sayisi. Gerekçe: başabaş zaten
B = ⌈G / u⌉, u = R / ort ile tanımlı, yani B = ⌈G·ort / R⌉; bu yüzden ort − B ≥ 0 olması (yuvarlama payı hariç)
R ≥ G, yani o ayın kârda olması demektir. Ay sonu stoku bu tutarlılığı sağlamaz. Geçmiş ayda aktif_uye_sayisi
ayın SON GÜNÜNDEKİ aktif üyedir (bilgi amaçlı), basabas_farki ve zarar_icin_kayip_uye None'dır ("N üye
kaybederseniz" cümlesi yalnızca içinde bulunulan ayda anlamlı). İçinde bulunulan ay (ve ileri tarihli ay) için
davranış değişmez: bugünün aktif üyesi.

**K3 Web oturumu:** Erişim ve yenileme tokenları httpOnly + SameSite=Lax çerezlerde (Secure yalnızca ortam=uretim).
Durum değiştiren her web isteğinde CSRF tokenı (çift gönderim: çerez + form alanı veya X-CSRF-Token başlığı).
Yenileme yalnızca tam sayfa GET isteğinde yapılır; HTMX parça isteğinde erişim çerezi geçersizse 401 +
"HX-Refresh: true" döner. Neden: yenileme tokenı tek kullanımlık; iki paralel istek aynı tokenı yenilemeye
çalışırsa ikincisi "yeniden kullanım" sayılır ve oturum ailesi iptal olur.

**Bölümleme:** 9a iskelet + giriş + finans kutuları; 9b riskli ve sessiz üye tabloları + "neden riskli";
9c demo tazeleme, rapor, görünüm.

## 9a'da yapılanlar

**K2 (servis):** `servisler/finans_servisi.py` ve `semalar/panel.py`'de `gecmis_ay` ve `basabas_farki_ortalama`
alanları eklendi. `/panel/finans` yanıtı da bu iki alanı içerir.

**Uçlar** (`rotalar/web.py`, OpenAPI şemasında görünmez):

| Uç | Davranış |
|---|---|
| `GET /` | Geçerli oturum → 303 `/pano`; yoksa 303 `/giris` (eski JSON karşılama mesajı kaldırıldı) |
| `GET /giris` | Form (e-posta, parola, gizli csrf); geçerli oturum varsa 303 `/pano` |
| `POST /giris` | CSRF; hatalı giriş ve doğrulama hatası aynı mesaj ("E-posta veya parola hatalı", 401); başarıda çerezler + CSRF yenilenir; tek üyelik → `/pano`, değilse `/isletme` |
| `GET /isletme` | Kullanıcının üyelikleri; seçili işletme işaretli |
| `POST /isletme` | CSRF; üyelik sunucuda doğrulanır (`servis.isletme_sec`); başka işletme → 403 |
| `POST /cikis` | CSRF; oturum ailesi kapatılır, üç çerez silinir |
| `GET /pano?ay=YYYY-AA` | Finans kutuları; ay yok / geçersiz / ileri → içinde bulunulan ay; ay seçici son 12 ay |
| `GET /pano/finans?ay=` | Yalnızca `_finans.html` parçası (HTMX); yanıtta `HX-Push-Url: /pano?ay=…` |

- Rol: sahip ve yönetici finansı görür; çalışana finans hesaplanmaz, bilgi cümlesi gösterilir.
- Tüm web yanıtlarında `Cache-Control: no-store`.
- Kiracı oturumu, API ile ortak `bagimliliklar.kiraci_oturumu(kimlik)` context manager'ıyla açılır (RLS ve
  `after_begin` değişmedi). Token çözme API ile ortaktır (`token_kimligi`).

**Çerezler** (üçü de `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` yalnızca `ortam=uretim`):

| Çerez | İçerik | Ömür |
|---|---|---|
| `panosu_erisim` | Erişim tokenı (JWT) | `erisim_suresi_dk` |
| `panosu_yenileme` | Yenileme tokenı (tek kullanımlık) | `yenileme_suresi_gun` |
| `panosu_csrf` | `secrets.token_urlsafe(32)`; şablona sunucuda basılır, JS okumaz; girişte yenilenir | oturum çerezi |

**Dosyalar:** `rotalar/web.py`, `sablonlar/web/` (`taban.html`, `giris.html`, `isletme_sec.html`, `pano.html`,
`_finans.html`), `statik/htmx.min.js` (htmx 2.0.4, SHA-256
`e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447`), `statik/panel.css`,
`sentetik/demo_sunucu.py`, `servisler/bicim.py` (`ondalik`), `tests/test_web.py`.

## Adım 9b kararları (proje sahibi onayı, 2026-10-02)

**K4 Yer ve yetki:** /pano'da finans kutularının altında iki tablo: "Önümüzdeki 45 günde paketi bitenler" ve "Sessiz
üyeler". Tüm rollere açık (JSON API'de bu veri zaten tüm rollere açık; finans kutuları yine yalnızca
sahip/yönetici). Tablolar seçili aydan bağımsızdır ("bugün itibarıyla"); ay seçici yalnızca #finans'ı değiştirir.

**K5 Sıralama:** ikisi de riskteki para azalan (mevcut servis sıralaması). Riskteki para = beklenen kayıp; arama zamanı
kısıtlıyken beklenen kaybı en büyük olandan başlamak korunan beklenen ciroyu en büyük yapar. İlk 10 satır +
"Tümünü göster (N)". Sessiz eşiği 0,5 sabit (haftalık raporla aynı).

*K5 eki (2026-10-02):* Riskli tablo varsayılan olarak yalnızca P(yenileme) < %80 satırları gösterir; düşük riskliler
tek satırla özetlenir. Olasılıklar <%1 / >%99 biçiminde; p_aktif < %5 iken ayrıştırma (aktif × sürdürme) gösterilmez
(`AYRISTIRMA_MIN_P_AKTIF`). Gerekçe: q = p_yenileme / p_aktif, simülasyondaki yaklaşık 2000·p_aktif "aktif"
çekilişten tahmin edilir; %5'te bu yaklaşık 100 çekiliş, standart hata en fazla 5 puan; daha azında q güvenilmez.
K63 (2026-10-04): since the exact formula (K61) the Monte Carlo reason is gone; the threshold stays because q is
computed from values stored with 4 decimals.

**K6 Neden riskli = riskin iki çarpana ayrılması:** P(yenileme) = P(aktif şimdi) × P(sürdürme | aktif).
p_aktif = p_hayatta_simdi; q = min(p_yenileme / p_aktif, 1) (p_aktif = 0 ise q tanımsız).
A = −ln p_aktif, B = −ln q; −ln P(yenileme) = A + B. sessizlik_payi = A / (A + B).
A ≥ B → ana neden sessizlik; B > A → ana neden kalan süre (süre bazlı) / kalan hak (giriş bazlı).
**K60 (2026-10-04) addendum to K6:** the remaining-time / remaining-entries sentence starts with "Şu an düzenli
geliyor", so it is chosen only when p_aktif ≥ 0.5 (the same threshold as the panel's silent-members list); below that
the main reason is silence. Found in the demo: a member absent 66 days (p_aktif 0.0002) got p_yenileme 0 from the
Monte Carlo (≈0.4 active draws out of 2,000), so q = 0, B = ∞ and the old rule picked the remaining-time sentence.

**K7 Normal aralık:** m = (son ziyaret günü − ilk ziyaret günü) / (ziyaret sayısı − 1); sessiz gün s = hesaplama günü −
son ziyaret günü; kat k = s / m. Aktif üyede s gün hiç gelmeme olasılığı ≈ e^(−k). "Normal aralık" yalnızca en
az 4 ziyaret varsa söylenir (ortalamanın göreli hatası ≈ 1/√(n−1)).

**K8 Hesaplama tarihi:** Açıklamadaki sayılar riskin hesaplama_tarihi itibarıyla hesaplanır (modelin gördüğü veriyle aynı;
yenileme_hesapla ile aynı kesim: işletmenin yerel günüyle ziyaret günü ≤ hesaplama_tarihi). Hesaplama tarihi bugünden
eskiyse tablo üstünde not.

**K9 Sadakat:** açıklama yalnızca modelin kullandığı bilgiden (ziyaret sayısı, ilk/son ziyaret, kalan gün/giriş, iki
olasılık) türetilir; modelde olmayan sinyal (ör. "ritmi yavaşladı") yazılmaz. P(yenileme) ≥ 0,80 → "Düzenli
geliyor; belirgin bir risk yok." (gösterim eşiği).

**K10 Kapsam dışı:** JSON API, haftalık rapor (9c), mesaj/WhatsApp (Adım 10), migration.

## 9b'de yapılanlar

**Uçlar** (`rotalar/web.py`):

| Uç | Davranış |
|---|---|
| `GET /pano?ay=&riskli=tumu&sessiz=tumu` | Finans kutuları + iki tablo; `riskli`/`sessiz` yalnızca "tumu" değeriyle anlamlı (tam liste) |
| `GET /pano/riskli?tumu=1` | Yalnızca `_riskli.html` parçası ("Tümünü göster"); HX-Push-Url yok |
| `GET /pano/sessiz?tumu=1` | Yalnızca `_sessiz.html` parçası; HX-Push-Url yok |

- `/pano/finans` (ay seçici) risk listelerini hesaplamaz. Yeni uçlarda kimlik, işletme seçimi, HTMX 401 +
  HX-Refresh ve `Cache-Control: no-store` davranışı `/pano/finans` ile aynıdır (ortak gövde `_kiraci_sayfasi`).
- Tablolar tüm rollere açık; çalışan riskteki para tutarlarını görür, finans kutularını görmez
  (`test_pano_calisan_finans_gormez`'deki " TL" denetimi `#finans` parçasına daraltıldı: K4'ün tanım değişikliği).
- Riskli tablo: alt başlıkta riskli paket sayısı ve riskteki parası; tablonun altında "Ayrıca N paket düşük riskli
  (…)" ve "Tümünü göster (tüm paket sayısı)". Sessiz tablo: ilk 10 satır + "Tümünü göster (üye sayısı)".
- Hesaplama tarihi bugünden eskiyse tablo üstünde "Olasılıklar ve açıklamalar … verisiyle hesaplandı." notu.

**Açıklama kuralları** (`analitik/aciklama.py`, `neden_riskli`; ilk uyan kazanır):

| ana_neden | Koşul | Cümle |
|---|---|---|
| `dusuk_risk` | P(yenileme) ≥ 0,80 | Düzenli geliyor; belirgin bir risk yok. |
| `hic_gelmedi` | ziyaret yok | Paketi {tarih} tarihinde aldı, o günden beri hiç gelmedi ({gün} gün). |
| `az_gecmis` | (A ≥ B veya p_aktif < 0,5) ve (ziyaret < 4 veya m = 0) | Yalnızca {n} kez geldi; son ziyaret {s} gün önce (s = 0: son ziyareti hesaplama gününde). Geçmiş az, tahmin belirsiz. |
| `sessizlik` | (A ≥ B veya p_aktif < 0,5), ziyaret ≥ 4 | Normalde ~{m} günde bir geliyor; {s} gündür gelmiyor (normalin {k} katı). |
| `uzun_sure` | B > A ve p_aktif ≥ 0,5, süre bazlı | Şu an düzenli geliyor; risk, paketin bitmesine kalan {gün} günde bırakma ihtimalinden. |
| `kalan_hak` | B > A ve p_aktif ≥ 0,5, giriş bazlı | Şu an düzenli geliyor; risk, kalan {n} giriş hakkını kullanırken bırakma ihtimalinden. |

- p_aktif = 0 → A = ∞ (sessizlik ailesi, p_surdurme yok); q = 0 → B = ∞ (sessizlik_payi 0).
- Neden hücresinin altında (dusuk_risk ve hic_gelmedi dışında) gri satır: "Aktif olma … · bitişe kadar sürdürme … →
  yenileme …"; p_aktif < %5 ise yalnızca "Aktif olma …".
- Kalan gün / giriş açıklamada risk kaydındaki (hesaplama günü itibarıyla) değerdir; tablodaki "N gün kaldı" bugüne göre.

**Dosyalar:** `analitik/aciklama.py`, `servisler/risk_listeleri.py` (toplu sorgular: paket başlangıcı, risk kaydı, her
hesaplama tarihi için bir ziyaret özeti; elle isletme_id filtresi yok), `sablonlar/web/_riskli.html`,
`sablonlar/web/_sessiz.html`, `servisler/bicim.py` (`olasilik`), `statik/panel.css` (tablolar, `overflow-x: auto`),
`tests/test_analitik_aciklama.py`, `tests/test_web.py`, `tests/test_rapor.py` (`olasilik`).

## Adım 9c kararları (proje sahibi onayı, 2026-10-02)

**K11 Demo tazeleme = zaman kaydırma:** [DEMO] işletmelerin tüm tarihleri aynı d gün ileri kaydırılır. Yeniden üretim
yok (kimlikler, üyelikler, oturumlar korunur). Gerekçe: M3 ve yenileme simülasyonu zamanı yalnızca farklarla görür
(x, t_x, T, kalan gün); hepsi kaydırmada değişmez, yani model zaman ötelemesine göre değişmezdir: kaydırılmış demoda
bugün hesaplanan p_hayatta_simdi eskisiyle birebir aynıdır. p_yenileme yalnızca Monte Carlo hatası kadar oynar
(simülasyon tohumu hesaplama tarihine bağlı).

**K12 Kaydırma miktarı:** işletme başına d = (yerel bugün − 1) − en son ziyaretin yerel günü; d ≤ 0 → dokunma.
Tazelemeden sonra son ziyaret günü = dün. Ayrı "demo tarihi" saklanmaz. Kenar durum: gerçek son günde hiç ziyaret
yoksa bir kez 1 gün fazla kayar (olasılık e^(−λ), λ = günlük ziyaret; Butik'te ihmal edilebilir).

**K13 Kayanlar:** ziyaretler.ziyaret_zamani, musteri_paketleri.baslangic_tarihi/bitis_tarihi,
musteriler.olusturma_zamani, musteri_izinleri.kayit_zamani (+ d gün). yenileme_riskleri KAYMAZ (tekil anahtar
çakışır); bugün için yeniden hesaplanır. isletme_giderleri: işletmenin gider ayı sayısı L korunur: yerel bugünün ayı
gider aylarında yoksa, en son gider ayının satırları (kategori, tutar, aciklama) aradaki her yeni aya kopyalanır ve
eklenen ay sayısı kadar en eski ay silinir.

**K14 Denetim:** kaydırmanın ürettiği denetim_kayitlari satırları aynı işlemde silinir; yalnızca [DEMO] işletme
kimlikleri ve zaman = now() (işlem boyunca sabit). Gerçek işletmede denetim kaydı silinmez.

**K15 Güvenlik:** yalnızca adı "_demo" ile biten veritabanı (bağlantıdan önce doğrulanır) ve adı "[DEMO]" ile başlayan
işletmeler. Kaydırma yönetici bağlantısıyla, elle isletme_id filtresiyle (temizle() ile aynı belgelenmiş istisna).
Tüm [DEMO] işletmeler tek işlemde; işlem başında pg_advisory_xact_lock (iki eşzamanlı tazelemede ikincisi d = 0
görür). Risk yeniden hesabı commit'ten sonra, işletme başına uygulama rolüyle ve kiracı bağlamında
(yenileme_hesapla; RLS ve after_begin değişmez).

**K16 Çalışma zamanı:** `python -m sentetik.demo_tazele --veritabani panosu_demo` (--kuru: yalnızca rapor).
demo_sunucu açılışta tazeler ve açık kaldıkça her gece 03:00 (Europe/Istanbul) tekrar tazeler. Adım 8b'nin gece
hesabı yalnızca demo için.

**K17 Haftalık rapor = panelin yazdırılabilir hâli:** listeler risk_listeleri.riskli_uyeler / sessiz_uye_listesi'nden
(tumu=False). Riskli tablo yalnızca P(yenileme) < %80 ilk 10 + "Ayrıca N paket düşük riskli" satırı (tanım
değişikliği). "Neden" her üyenin altında tam genişlikte ikinci satır. Neden HTML'i tek makroda
(sablonlar/web/_neden.html), panel ve rapor ortak. Eskimiş notu raporda da.

**K18 Panelden rapora:** GET /pano/rapor (çerezli oturum, yalnızca sahip/yönetici, çalışana 403, no-store); /pano'da
"Haftalık rapor" bağlantısı (yeni sekme, yalnızca sahip/yönetici); raporda yazdırırken gizlenen "Yazdır / PDF"
düğmesi. Bearer /rapor/haftalik aynen kalır.

**K19 Görünüm:** ad, paket ve tarih hücreleri nowrap (panel + rapor); telefon tel: bağlantısı ve "+90 532 123 45 67"
biçimi (+90 dışı olduğu gibi); 600 px altında tablo satırları kart (yalnızca CSS, td'lerde data-etiket).

**Kapsam dışı:** Rao-Blackwell (ayrı model kararı), JSON API davranışı, migration, üreticiler, gerçek işletmeler için 8b.

## 9c'de yapılanlar

**Uçlar** (`rotalar/web.py`):

| Uç | Davranış |
|---|---|
| `GET /pano/rapor` | Haftalık rapor HTML'i (`rapor_servisi.haftalik_rapor`); yalnızca sahip/yönetici, çalışana 403 mesaj sayfası ("Haftalık rapor yalnızca işletme sahibi ve yöneticiye açıktır."); `Cache-Control: no-store`; oturumsuz → /giris, işletme seçilmemiş → /isletme, HTMX'te 401 + HX-Refresh (`_kiraci_sayfasi`, `sablon=None` → hazır HTML) |
| `GET /rapor/haftalik` (Bearer) | Davranışı değişmedi; içerik yeni şablonla |

**Demo tazeleme** (`sentetik/demo_tazele.py`, K11–K16):

```powershell
.\.venv\Scripts\python.exe -m sentetik.demo_tazele --veritabani panosu_demo --kuru   # yalnızca rapor, yazmaz
.\.venv\Scripts\python.exe -m sentetik.demo_tazele --veritabani panosu_demo          # kaydır + riskleri yeniden hesapla
.\.venv\Scripts\python.exe -m sentetik.demo_sunucu --tazeleme-yok                   # açılış ve gece tazelemesi yok
```

- Her işletme için bir satır: d, kayan satır sayıları, eklenen/silinen gider ayları, silinen denetim kaydı, risk durumu.
- demo_sunucu: açılışta bir kez, sonra arka plan iş parçacığında her gece 03:00 (Europe/Istanbul). Tazeleme hatası
  sunucuyu durdurmaz; yalnızca istisna türü yazılır (adres içerebilecek metin yazılmaz).
- `paket_uretici --gecmis-giderler` takvim başlangıcını (2026-03) kullanır; tazeleme sonrası çalıştırılırsa gider
  penceresini (K13, L ay) bozar.

**Sıralı okuma (deterministiklik düzeltmesi):** `yenileme_hesapla`'nın ziyaret sorgusu
`ORDER BY musteri_id, ziyaret_zamani` ile okur. M3 uyumu üye sırasına duyarlıdır; sıra olmadan kaydırmanın UPDATE'i
fiziksel satır sırasını değiştirip sonucu 4. ondalıkta oynatıyordu. Model değişikliği değil; MODEL_VERSIYONU aynı.
a ve b'nin ayrı ayrı gevşek belirlenmesi (a/(a+b) ≈ 0,0060 sabitken a+b 431–433) olabilirlik yüzeyindeki sırttan;
ortalama bırakma iyi, yayılım zayıf tanımlı (Adım 8a önseli bu yönü sabitler).

**Değişmezlik kontrolü** (panosu_demo, 2026-10-02; tazeleme öncesi riskler: hesaplama 2026-10-01, son ziyaret
2026-09-30; tazeleme d = 1; karşılaştırma bugünün yeniden hesabıyla):

| | Butik Reformer | Denge Pilates |
|---|---|---|
| Karşılaştırılan paket | 81 | 219 |
| p_hayatta_simdi farklı (sıralı okumadan önce) | 2 (en büyük fark 0,0001) | 10 (en büyük fark 0,0001) |
| p_hayatta_simdi farklı (sıralı okumayla) | 0 | 0 |
| kalan_gun / kalan_giris farklı | 0 | 0 |
| \|Δ p_yenileme\| ortalama / en büyük | 0,0055 / 0,0315 | 0,0063 / 0,0335 |

p_yenileme farkı Monte Carlo hatasıdır (tohum hesaplama tarihine bağlı; K11).

**Rapor ve görünüm (K17–K19):**
- Rapor başlıkları sayısız: "Önümüzdeki 45 günde yenilemesi en riskli paketler", "En değerli sessiz üyeler"; liste
  `risk_listeleri.TABLO_SATIRI`'ndan uzunsa alt satırın sonunda "(ilk 10 gösteriliyor)".
- Raporda her üye bir `<tbody class="uye">`: veri satırı + tam genişlik neden satırı (8 pt; ayrıştırma satırı gri);
  tbody sayfa arasında bölünmez. "Paket ücreti" sütunu korundu; olasılıklar `olasilik()` ile.
- Panel tablolarında her td'de `data-etiket`; 600 px altında satır kart, hücre iki sütunlu ızgara (etiket | değer;
  "N gün kaldı" değer sütununda tarihin altında), neden hücresi tam genişlik.
- Testlerde tablo satırı sayımı `<tr><td>` yerine etiketli ilk hücreyle (`SATIR`) yapılır (K19'un markup değişikliği).

**Dosyalar:** `sentetik/demo_tazele.py`, `sentetik/demo_sunucu.py`, `servisler/yenileme_servisi.py` (sıralı okuma),
`sablonlar/web/_neden.html`, `sablonlar/web/_riskli.html`, `sablonlar/web/_sessiz.html`, `sablonlar/web/pano.html`,
`sablonlar/haftalik_rapor.html`, `servisler/rapor_servisi.py`, `servisler/bicim.py` (`telefon`), `rotalar/web.py`,
`statik/panel.css`, `tests/test_demo_tazele.py`, `tests/test_yenileme_servisi.py`, `tests/test_rapor.py`,
`tests/test_web.py`.

**Testler:** 414 (9c'de 39 yeni).

## Sonraya kalanlar

- Fikir (model değişikliği, ayrı karar): yenileme simülasyonunda Rao-Blackwell, P(yenileme) = p_aktif ×
  ort(sürdürme | aktif); gürültüyü azaltır ve P(yenileme) ≤ P(aktif)'i garanti eder. Done: K61
  (`docs/adim-rao-blackwell-tasarim.md`).
