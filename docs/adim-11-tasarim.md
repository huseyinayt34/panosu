# Adım 11: Minimum yayın (canlı demo): tasarım ve kararlar

## Adım 11 kararları (proje sahibi onayı, 2026-10-02)

**K20 Barındırma:** Render ücretsiz web servisi (Docker, Frankfurt) + Neon ücretsiz PostgreSQL (Frankfurt) + GitHub
Actions (gece tazeleme ve kurulum). Maliyet 0, kart yok. Render 15 dk trafik yoksa uyur; CPU 0,1.
Alternatifler: Hetzner VPS (~4–5 €/ay, sunucu yönetimi), Oracle Always Free (kart, kapasite), Render PostgreSQL
(30 günde siliniyor, elendi).

**K21 Yayında tek veritabanı:** Neon'da `panosu_demo`. Canlı `panosu` yayına alınmaz. `_demo` korumaları yayında da
geçerli.

**K22 En az yetki:** web sunucusu (Render) yalnızca `panosu_app` ile bağlanır; yönetici adresi yalnızca GitHub Actions
gizlilerinde. PANOSU_ORTAM=uretim iken uygulama şu durumlarda açılmaz: veritabanı kullanıcısı panosu_app değil;
PANOSU_MIGRASYON_URL tanımlı; PANOSU_ACIK_KAYIT açık. Yönetici, panosu_app ve JWT gizlileri yereldekilerden farklı
ve güçlü. Ön koşul: Neon yönetici rolünde rolbypassrls = true (proje sahibi SQL ile doğrular).

**K23 Gece tazeleme yayında GitHub Actions'ta:** demo-tazele.yml, her gün 00:00 UTC (03:00 İstanbul) + elle
çalıştırma. Gerekçe: yönetici adresi web sunucusuna girmez; uyuyan Render'da iş parçacığı çalışmaz; Monte Carlo 0,1
CPU'da yavaş. Kaçan gece ertesi gece d = 2 ile telafi edilir (K11 değişmezliği). demo_sunucu yerel kullanım için aynen
kalır.

**K24 Kurulum yeniden üretilebilir:** sentetik/demo_kur.py yereldeki panosu_demo'yu kuran sırayı tek komutta, sabit
tohumlar ve referans günü 2026-10-01 ile çalıştırır; sonunda demo kullanıcısı ve tazeleme. Yayına demo-kur.yml ile
(elle, onay kelimesi "KUR") uygulanır: alembic upgrade head → panosu_app parolası → demo_kur. pg_dump ile kopyalama
yok. Doğrulama: yerelde boş veritabanına kurulum, aynı gün tazelenmiş panosu_demo ile işletme başına birebir eşitlik.

**K25 Salt okunur demo:** PANOSU_SALT_OKUNUR=true iken GET/HEAD/OPTIONS serbest; yazma yalnızca POST /giris, /cikis,
/isletme, /oturum/giris, /oturum/yenile, /oturum/cikis, /oturum/isletme-sec uçlarında; gerisi 403
{"detail": "Bu demo salt okunur; veri değiştirilemez."}.

**K26 Kamuya açık demo parolası:** PANOSU_DEMO_GIRIS_EPOSTA ve PANOSU_DEMO_GIRIS_PAROLA ikisi de tanımlıysa giriş formu
dolu gelir ve "Bu bir demo; Giriş'e basmanız yeterli." notu görünür. Parola kodda, testte (sabit değer olarak gerçek
parola), çıktıda ve commit'te yer almaz. Kural 7'ye ek: yayındaki demo parolası kamuya açıktır ve yerel parolalardan
farklıdır. Kilit (5 yanlış → 15 dk) kabul edilen risk.

**K27 HTTPS Render'da:** uretim ⇒ Secure çerez; uvicorn --proxy-headers --forwarded-allow-ips='*'. Üretimde başlıklar:
Strict-Transport-Security: max-age=31536000; X-Content-Type-Options: nosniff; Referrer-Policy: same-origin;
X-Frame-Options: DENY. Uyku önleme (isteğe bağlı UptimeRobot) ve Render sağlık kontrolü /statik/panel.css'e gider;
/saglik veritabanını uyandırır, Neon'un 100 CU-saatlik aylık hakkı aşılırdı.

**K28 requirements-uretim.txt** (yalnızca çalışma anı paketleri, requirements.txt'teki sürümlerle) + Dockerfile
(python:3.14-slim, root olmayan kullanıcı) + .dockerignore. İmajı Render derler.

## Yapılanlar

**Üretim modu (Bölüm 1)**
- `config.py`: yeni alanlar `salt_okunur`, `demo_giris_eposta`, `demo_giris_parola` (SecretStr). `ortam` yalnızca
  `"gelistirme"` | `"uretim"`. `model_validator`: uretim'de kullanıcı panosu_app değilse, PANOSU_MIGRASYON_URL
  tanımlıysa veya açık kayıt açıksa uygulama açılmaz (K22). `hide_input_in_errors=True`: doğrulama hatası girdi
  değerlerini (adres, parola) basmaz; hata metinleri adres ve parola içermez.
- `rotalar/ara_katman.py` (main.py'de kayıtlı): salt okunur mod (K25; yol eşleşmesi tam eşitlik, `/giris/` 403) ve
  üretimde dört güvenlik başlığı (K27). Ayarlar her istekte okunur.
- `rotalar/web.py` + `sablonlar/web/giris.html`: K26 demo girişi. İki değişkenden biri eksikse form boş. Başarısız
  girişte kullanıcının yazdığı parola sayfaya geri basılmaz; parola alanı yalnızca demo parolasıyla dolabilir.
- `requirements-uretim.txt`: 34 paket, `requirements.txt` sürümleriyle. fastapi 0.142'nin bağımlılığı
  `opentelemetry-api` dahil; `colorama` yalnızca Windows'ta (click). `httpx` yalnızca test bağımlılığıdır, dosyada yok.
  Temiz sanal ortamda (yalnızca bu dosya + pytest + test için httpx) tam test paketi geçti.
- `Dockerfile` (python:3.14-slim, uid 10001 `panosu` kullanıcısı, `${PORT:-8000}`, `--proxy-headers`) ve
  `.dockerignore` (ek olarak `**/__pycache__/`, `**/*.pyc`). Yerelde Docker yok; imaj derlenmedi, ilk derleme Render'da.
- Yerel sürümler: Python 3.14.6, PostgreSQL 18.6; `panosu_demo` 117 MB.

**Yeniden üretilebilir kurulum (Bölüm 2)**
- `sentetik/demo_kur.py`: üreticileri değiştirmeden, yereldeki panosu_demo'nun sırasıyla çağırır:
  1. temizlik (tüm [DEMO]),
  2. sentetik işletmeler (referans 2026-10-01, 400 müşteri, 730 gün, tohum 42, enflasyon 0, tüm sektörler),
  3. Denge Pilates paketleri (tohum 42, bugün 2026-10-01; sonunda çift sayım düzeltmesi),
  4. Denge Pilates giderleri (2026-03 … 2026-10),
  5. Butik Reformer (tohum 2026, BUGUN 2026-10-01),
  6. demo kullanıcısı (parola yalnızca PANOSU_DEMO_PAROLA'dan; yoksa veya kurala uymuyorsa veri silinmeden hata),
  7. demo tazeleme.

  Reçete, mevcut panosu_demo'nun müşteri, ziyaret ve paket kimlikleriyle birebir doğrulandı.
  `--uygulama-parolasi-ayarla` (yalnızca yayında): `ALTER ROLE panosu_app WITH LOGIN PASSWORD` (psycopg2.sql.Literal);
  hata olursa yalnızca istisna türü yazılır. `butik_reformer.BUGUN` referans gününden farklıysa kurulum başlamaz.
  Gerçek değer CSV'si (veri/) yazılmaz; veritabanı durumunun parçası değildir.
- K24 karşılaştırması (2026-10-02): boş `panosu_kurulum_demo` (alembic upgrade head + demo_kur) ile aynı gün tazelenmiş
  `panosu_demo`. 5 [DEMO] işletme, 0 fark. Karşılaştırılan ölçüler: üye, ziyaret, son ziyaret günü, aktif paket, gider
  ayı sayısı ve aralığı, bu ayın geliri, aktif üye, başabaş üye, riskli paket (P(yen) < 0,80), sessiz üye, toplam
  Riskteki Para (45 gün), risk hesap günü. Örneğin Riskteki Para Denge Pilates'te 79.874,40 TL, Butik Reformer'da
  22.380,70 TL; iki veritabanında aynı. `panosu_kurulum_demo` doğrulamadan sonra silindi.
- Süreler (yerel): demo_kur toplam 33,1 sn. Adımlar:
  - [1/7] temizlik 0,1 sn
  - [2/7] sentetik 12,9 sn
  - [3/7] Denge paketleri 4,9 sn
  - [4/7] Denge giderleri 0,2 sn
  - [5/7] Butik Reformer 2,9 sn
  - [6/7] demo kullanıcısı 0,3 sn
  - [7/7] tazeleme 11,7 sn (d = 1; Butik 4,0 sn, Denge 5,3 sn)

  `panosu_demo`'da kaydırma ve risk hesabı gerektirmeyen tazeleme (d = 0, riskler zaten bugün) 3,3 sn sürdü.
  Neon'da ve 0,1 CPU'lu Render'da süreler daha uzun olabilir; tazeleme GitHub Actions'ta çalışır (K23).

**GitHub Actions (Bölüm 3)**
- `.github/workflows/demo-tazele.yml`: cron `0 0 * * *` + elle; `contents: read`; eşzamanlılık grubu
  `demo-veritabani` (iptal yok); 30 dk.
- `.github/workflows/demo-kur.yml`: yalnızca elle, `onay` = `KUR`; aynı grup; `alembic upgrade head` →
  `demo_kur --uygulama-parolasi-ayarla`; 45 dk. PANOSU_DEMO_PAROLA yalnızca kurulum adımının ortamında.
- İkisinde de PANOSU_JWT_GIZLI her çalıştırmada rastgele üretilir ve maskelenir (Ayarlar doğrulaması için; kullanılmaz).
- İki YAML PyYAML ile ayrıştırıldı; iş akışları yerelde çalıştırılamaz, ilk gerçek çalıştırma GitHub'da.

**Testler:** `tests/test_uretim.py`, 21 test: ayar doğrulayıcısı, salt okunur, başlıklar, demo giriş formu, demo_kur
korumaları (ağır kurulum pytest'te çalışmaz). Tam paket 435 test.

## Yayın ortam değişkenleri

Değerler burada yazılmaz; yalnızca ad ve anlam.

| Yer | Değişken | Anlam |
|---|---|---|
| Render | PANOSU_VERITABANI_URL | Neon `panosu_demo`, kullanıcı `panosu_app` (`postgresql+psycopg2://…?sslmode=require`) |
| Render | PANOSU_JWT_GIZLI | Erişim tokenı imza anahtarı; yerelden farklı, en az 32 bayt |
| Render | PANOSU_ORTAM | `uretim` |
| Render | PANOSU_ACIK_KAYIT | `false` |
| Render | PANOSU_SALT_OKUNUR | `true` |
| Render | PANOSU_DEMO_GIRIS_EPOSTA | Demo giriş e-postası (demo@panosu.local) |
| Render | PANOSU_DEMO_GIRIS_PAROLA | Kamuya açık demo parolası; PANOSU_DEMO_PAROLA ile aynı, yerel parolalardan farklı (K26) |
| GitHub gizlisi | PANOSU_MIGRASYON_URL | Neon yönetici rolü, veritabanı `panosu_demo` (DDL; rolbypassrls = true) |
| GitHub gizlisi | PANOSU_VERITABANI_URL | Render'dakiyle aynı adres (`panosu_app`); kurulumda parolası ALTER ROLE ile atanır |
| GitHub gizlisi | PANOSU_DEMO_PAROLA | demo@panosu.local parolası (demo_kur) |

Notlar:
- PANOSU_MIGRASYON_URL Render'da TANIMLANMAZ; tanımlıysa uygulama açılmaz (K22).
- Migration'lar `citext` eklentisini, `CREATE ROLE panosu_app` ve SECURITY DEFINER fonksiyonlarını içerir; fonksiyon
  sahibi Neon yönetici rolüdür. RLS'li tablolarda doğru çalışmaları K22 ön koşuluna (rolbypassrls) bağlıdır.
- Sunucuda `log_statement` `ddl` veya `all` ise `ALTER ROLE … PASSWORD` satırı veritabanı günlüğüne düşebilir;
  Neon'da kontrol edilmeli.

Canlı adres: https://panosu.onrender.com (2026-10-02'de yayına alındı)
- Web: Render Free, Frankfurt, Docker; ilk deploy ea685ca. Health check: /statik/panel.css.
- Veritabanı: Neon Free, AWS eu-central-1 (Frankfurt), PostgreSQL 18.6; veritabanı panosu_demo, yönetici rolü panosu_demo_owner.
- Uyanık tutma: UptimeRobot, 5 dakikada bir /statik/panel.css (veritabanına dokunmaz; Neon boşta uyumaya devam eder).
- Doğrulama (2026-10-02): /saglik {"durum":"ok"}; [DEMO] Butik Reformer 79 aktif üye, başabaş 63; çerezler Secure ve
  HttpOnly; POST /musteriler -> 403 "Bu demo salt okunur"; GitHub Actions "Demo kurulumu" (205,9 sn) ve "Demo tazeleme"
  (5 işletmede d = 0) yeşil.
- Kurulumda öğrenilenler:
  (a) SQLAlchemy 2.1, öneksiz postgresql:// adresinde psycopg 3 sürücüsünü arar. Yayın paketinde psycopg2 olduğundan
      GitHub gizlilerindeki ve Render'daki adresler postgresql+psycopg2:// ile başlar.
  (b) PANOSU_VERITABANI_URL gizlisindeki kullanıcı panosu_app olmalıdır; değilse
      demo_kur --uygulama-parolasi-ayarla veri silmeden durur.
- Not: Riskteki Para (Butik Reformer, 45 gün) canlıda 22.379,85 TL, yerel karşılaştırmada 22.380,70 TL (fark 0,85 TL).
  Muhtemel neden (doğrulanmadı): Windows ile Linux numpy/scipy derlemeleri arasındaki kayan nokta farkı ve MBG/NBD'de
  a+b'nin zayıf belirlenmesi (sırt). Matematik raporu ve (mu, kappa) yeniden parametreleme kararı ile birlikte ele alınacak.
  (μ, κ) adımıyla kök neden giderildi; bkz. docs/adim-mu-kappa-tasarim.md K52.
