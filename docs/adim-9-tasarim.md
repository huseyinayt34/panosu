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
9c haftalık rapor bağlantısı, mobil cila, demo cilası.

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

**K6 Neden riskli = riskin iki çarpana ayrılması:** P(yenileme) = P(aktif şimdi) × P(sürdürme | aktif).
p_aktif = p_hayatta_simdi; q = min(p_yenileme / p_aktif, 1) (p_aktif = 0 ise q tanımsız).
A = −ln p_aktif, B = −ln q; −ln P(yenileme) = A + B. sessizlik_payi = A / (A + B).
A ≥ B → ana neden sessizlik; B > A → ana neden kalan süre (süre bazlı) / kalan hak (giriş bazlı).

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
| `az_gecmis` | A ≥ B ve (ziyaret < 4 veya m = 0) | Yalnızca {n} kez geldi; son ziyaret {s} gün önce (s = 0: son ziyareti hesaplama gününde). Geçmiş az, tahmin belirsiz. |
| `sessizlik` | A ≥ B, ziyaret ≥ 4 | Normalde ~{m} günde bir geliyor; {s} gündür gelmiyor (normalin {k} katı). |
| `uzun_sure` | B > A, süre bazlı | Şu an düzenli geliyor; risk, paketin bitmesine kalan {gün} günde bırakma ihtimalinden. |
| `kalan_hak` | B > A, giriş bazlı | Şu an düzenli geliyor; risk, kalan {n} giriş hakkını kullanırken bırakma ihtimalinden. |

- p_aktif = 0 → A = ∞ (sessizlik ailesi, p_surdurme yok); q = 0 → B = ∞ (sessizlik_payi 0).
- Neden hücresinin altında (dusuk_risk ve hic_gelmedi dışında) gri satır: "Aktif olma … · bitişe kadar sürdürme … →
  yenileme …"; p_aktif < %5 ise yalnızca "Aktif olma …".
- Kalan gün / giriş açıklamada risk kaydındaki (hesaplama günü itibarıyla) değerdir; tablodaki "N gün kaldı" bugüne göre.

**Dosyalar:** `analitik/aciklama.py`, `servisler/risk_listeleri.py` (toplu sorgular: paket başlangıcı, risk kaydı, her
hesaplama tarihi için bir ziyaret özeti; elle isletme_id filtresi yok), `sablonlar/web/_riskli.html`,
`sablonlar/web/_sessiz.html`, `servisler/bicim.py` (`olasilik`), `statik/panel.css` (tablolar, `overflow-x: auto`),
`tests/test_analitik_aciklama.py`, `tests/test_web.py`, `tests/test_rapor.py` (`olasilik`).

## 9c'ye kalanlar

- Haftalık rapor bağlantısı, mobil cila, demo cilası.
- Haftalık rapora "neden" sütunu ve panelden rapor bağlantısı.
- Demo verisinin bugüne kaydırılması + her gece yenileme riskinin yeniden hesaplanması (eskimiş notu böylece kalkar;
  CLAUDE.md "Açık konular").
- Tablolarda üye adı ve paket sütunları satır kırmasın (nowrap).
- Fikir (model değişikliği, ayrı karar): yenileme simülasyonunda Rao-Blackwell, P(yenileme) = p_aktif ×
  ort(sürdürme | aktif); gürültüyü azaltır ve P(yenileme) ≤ P(aktif)'i garanti eder.
