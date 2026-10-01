# Adım 8: Gerçek kimlik doğrulama ve işletme kaydı (tasarım belgesi)

Genel kurallar için `CLAUDE.md`'ye bak. Bu belgedeki ürün, güvenlik ve matematik kararları (K1–K9) proje sahibi
tarafından 2026-10-01'de onaylandı; ajan bunları değiştirmez, sorun görürse durup raporlar. Sıralama kararı
(2026-10-01): 4b gerçek Faz 0 verisi gelene kadar bekler; Adım 8 şimdi yapılır.

## Amaç
Bugün kimlik, istemcinin gönderdiği `X-Kullanici-Id` / `X-Isletme-Id` başlıklarından alınıyor
(`bagimliliklar.py: kimlik_al`). Bu başlıklar sahteleştirilebilir; bu yüzden `uretim` ortamında her kiracı ucu
501 döndürür. Yani **API şu an canlıya çıkamaz.** Adım 8 bunu kapatır:
1. Bir stüdyo sahibi hesap açıp işletmesini kaydedebilsin.
2. E-posta + parola ile giriş yapıp imzalı bir token alsın; her istekte kimlik ve işletme bu tokendan gelsin.
3. Sahip, personelini (yönetici / çalışan) davet edebilsin.
4. Adım 9'daki canlı demo için `panosu_demo`'da giriş yapılabilen bir demo kullanıcısı olsun.

## Mevcut durumdan çıkan kısıtlar (depodan okundu)
- `kullanicilar` tablosunda parola sütunu yok; `dis_kimlik_id` (Clerk/Auth0 için) var ve boş.
- `panosu_app` rolünün `kullanicilar` üzerinde INSERT yetkisi yok (yalnızca SELECT, UPDATE). Kayıt için yeni bir yol gerekir.
- `kullanicilar` RLS politikası: yalnızca kendi kaydın + aktif işletmenin üyeleri görünür. Girişte henüz kim
  olduğumuzu bilmediğimiz için e-postayla kullanıcı **bulunamaz**. Bu da yeni bir yol gerektirir.
- `isletme_olustur(ad, kullanici_id, sektor)` SQL fonksiyonu hazır: işletme + sahip üyeliği + ücretsiz abonelik
  oluşturur. Kayıtta aynen kullanılır.
- `kiraci_db` her istekte üyeliği ve rolü veritabanından okuyor. Bu korunur: rol ve üyelik değişiklikleri anında
  geçerli olur, token'a rol yazılmaz.
- `sektor` listesinde 'pilates' yok; stüdyolar `spor_salonu` olarak kaydedilir (liste bu adımda değişmez).

## Kararlar (proje sahibi onaylı, 2026-10-01)
| # | Konu | Öneri | Alternatif | Gerekçe |
|---|---|---|---|---|
| K1 | Kimlik sağlayıcı | **Kendi sistemimiz**: Argon2id parola özeti + JWT | Clerk / Auth0 | Kullanıcı verisi yurt dışına çıkmaz (KVKK'da yurt dışı aktarım ayrı yükümlülük); testler internetsiz çalışır; portföyde güvenlik tasarımını gösterir. `dis_kimlik_id` ileride harici sağlayıcı için boş kalır. |
| K2 | Yeni paketler (Kural 8) | `argon2-cffi`, `PyJWT` | `pwdlib`, `python-jose` | İkisi de küçük, yaygın, bakımı süren paketler. `cffi` zaten kurulu. Sürümler kurulumda belirlenip `requirements.txt`'e sabitlenir ve rapora yazılır. |
| K3 | Token modeli | **Kısa erişim tokenı (JWT, 15 dk) + uzun yenileme tokenı (30 gün, opak, her kullanımda yenilenir)** | Tek JWT, 8 saat | Çıkış yapınca oturum gerçekten kapanır; çalınan yenileme tokenı tekrar kullanılırsa tüm oturum ailesi iptal edilir. Tek JWT'de "çıkış" yalnızca istemcinin tokenı silmesidir. |
| K4 | Token taşıma | Adım 8'de JSON gövdede; erişim tokenı `Authorization: Bearer` başlığında | Yenileme tokenı httpOnly çerezde | Çerez kararı web paneliyle (Adım 9, Next.js) birlikte verilir; o zaman CSRF de ele alınır. |
| K5 | Açık kayıt | `PANOSU_ACIK_KAYIT` ayarı: geliştirmede açık, **üretimde kapalı**; pilot işletmeleri sen komutla açarsın | Herkese açık kayıt | Canlı demoda yabancıların işletme açması (çöp veri, kötüye kullanım) önlenir. Satış görüşmesi modeline de uyar. |
| K6 | Personel ekleme | **Tek kullanımlık davet kodu** (7 gün geçerli). Kod/bağlantıyı sahip WhatsApp'tan gönderir | Sahip, personele geçici parolayla hesap açar | E-posta gönderimi yok (Adım 10/11). Geçici parola sahibin personelin parolasını bilmesi demektir; davet kodunda bilmez. |
| K7 | E-posta doğrulama, parola sıfırlama | **Kapsam dışı** (Adım 11'e) | Bu adımda | E-posta altyapısı gerektirir. Pilotta kullanıcı sayısı küçük. |
| K8 | Geçici başlık kimliği | **Tamamen kaldırılır**; testler gerçek token kullanır | Geliştirmede bırakılır | İki kimlik yolu, ileride yanlışlıkla açık kalan bir arka kapı demektir. |
| K9 | Kural 3'ün yorumu | `isletme_id` yalnızca **imzalı tokendan** okunur. İşletme seçme ucunda istemci bir `isletme_id` önerir; sunucu üyeliği doğrular ve yeni token imzalar. Doğrulanmamış hâliyle hiçbir sorguya girmez. | — | Kural 3'ün amacı (istemciye güvenmemek) korunur. Onayın gerekir çünkü kural metni "asla istemciden alınmaz" diyor. |

## Bölüm 1: Migration 0004 (`alembic/sql/0004_kimlik.sql`, `alembic/versions/0004_kimlik.py`)
Önceki migration'larla aynı kalıp (SQL dosyası `no_parameters=True`; downgrade bu migration'ın nesnelerini siler).
`faz1_sema.sql` ve 0001–0003 DEĞİŞMEZ.

### `kullanici_kimlik_bilgileri` (parola özetleri ayrı tabloda)
| Sütun | Tip | Kural |
|---|---|---|
| kullanici_id | uuid PK | FK kullanicilar ON DELETE CASCADE |
| parola_ozeti | text NOT NULL | Argon2id PHC dizgesi (`$argon2id$v=19$m=...`) |
| parola_degisme_zamani | timestamptz NOT NULL DEFAULT now() | |
| basarisiz_giris | integer NOT NULL DEFAULT 0 | ≥ 0 |
| kilit_bitis | timestamptz | |

- RLS ENABLE + FORCE, **hiç politika yok** ve `panosu_app`'e **hiç yetki yok**. Uygulama bu tabloya yalnızca
  aşağıdaki fonksiyonlarla dokunur.
- Neden ayrı tablo: `kullanicilar` üzerinde `panosu_app`'in SELECT yetkisi var ve politika aktif işletmenin
  diğer üyelerini de gösteriyor. Parola özeti orada bir sütun olsaydı, koddaki tek bir hata bir yöneticinin
  çalışma arkadaşlarının parola özetlerini okumasına yol açabilirdi.

### `oturumlar` (yenileme tokenları)
| Sütun | Tip | Kural |
|---|---|---|
| oturum_id | uuid PK | |
| kullanici_id | uuid NOT NULL | FK kullanicilar ON DELETE CASCADE |
| aile_id | uuid NOT NULL | ilk girişte oluşur; yenilemelerde aynı kalır |
| token_ozeti | bytea NOT NULL UNIQUE | SHA-256(yenileme tokenı) |
| secili_isletme_id | uuid | FK isletmeler; adı bilerek `isletme_id` değil (kiracı tablosu değildir) |
| olusturma_zamani | timestamptz NOT NULL DEFAULT now() | |
| son_kullanma | timestamptz NOT NULL | |
| kullanilma_zamani | timestamptz | yenilendiğinde dolar (token bir kez kullanılır) |
| iptal_zamani | timestamptz | |
- RLS ENABLE + FORCE, politika yok, `panosu_app`'e yetki yok. Yalnızca fonksiyonlarla erişilir.

### `davetler`
| Sütun | Tip | Kural |
|---|---|---|
| davet_id | uuid PK | |
| isletme_id | uuid NOT NULL | DEFAULT aktif_isletme(), FK isletmeler |
| rol | text NOT NULL | 'yonetici' veya 'calisan' ('sahip' davet edilemez) |
| kod_ozeti | bytea NOT NULL UNIQUE | SHA-256(davet kodu) |
| olusturan_kullanici_id | uuid NOT NULL | DEFAULT aktif_kullanici() |
| son_kullanma | timestamptz NOT NULL | olusturma + 7 gün |
| kullanilma_zamani, kullanan_kullanici_id, iptal_zamani | | |
| olusturma_zamani | timestamptz NOT NULL DEFAULT now() | |
- RLS ENABLE + FORCE + `tenant_izolasyonu`; `panosu_app`'e SELECT, INSERT, UPDATE; denetim trigger'ı.

### SECURITY DEFINER fonksiyonları
Hepsi: `SECURITY DEFINER`, `SET search_path = public, pg_temp`, `REVOKE ALL ... FROM PUBLIC`,
`GRANT EXECUTE ... TO panosu_app`. Parola **düz metni veritabanına hiç gitmez**; özet Python'da hesaplanır.
| Fonksiyon | Görev |
|---|---|
| `kullanici_kaydet(p_eposta citext, p_ad_soyad text, p_parola_ozeti text) RETURNS uuid` | `kullanicilar` + `kullanici_kimlik_bilgileri` satırını tek seferde ekler. E-posta varsa tekillik hatası yükselir (uç 409'a çevirir). |
| `giris_bilgisi(p_eposta citext) RETURNS TABLE(kullanici_id uuid, parola_ozeti text, kilit_bitis timestamptz)` | E-postayla kullanıcıyı bulur (RLS'nin girişte engellediği tek okuma). |
| `giris_sonucu_yaz(p_kullanici_id uuid, p_basarili boolean)` | Başarılıysa sayaç sıfırlanır, `son_giris_zamani` yazılır. Başarısızsa sayaç artar; **5'e ulaşınca 15 dk kilit**. |
| `parola_ozeti_guncelle(p_kullanici_id uuid, p_yeni_ozet text)` | Yalnızca özet yeniden hesaplandığında (parametre yükseltme) çağrılır. |
| `oturum_ac(p_kullanici_id uuid, p_ozet bytea, p_isletme uuid, p_sure interval) RETURNS uuid` | Yeni aile ve oturum. |
| `oturum_yenile(p_eski_ozet bytea, p_yeni_ozet bytea, p_sure interval) RETURNS TABLE(kullanici_id uuid, secili_isletme_id uuid)` | Eski token geçerli ve kullanılmamışsa: kullanıldı işaretle, aynı ailede yeni oturum aç. **Kullanılmış token tekrar gelirse tüm aileyi iptal et ve boş dön** (çalıntı token tespiti). Süresi geçmiş/iptal → boş. |
| `oturum_kapat(p_ozet bytea)` | Ailenin tamamını iptal eder. |
| `oturum_isletme_degistir(p_ozet bytea, p_isletme uuid)` | İşletme seçimi yenileme oturumuna da yazılır. |
| `davet_kabul(p_kod_ozeti bytea, p_kullanici_id uuid) RETURNS TABLE(isletme_id uuid, rol text)` | Geçerli davette: kullanıldı işaretle + `uyelikler`'e ekle (tek işlem). Kullanıcı zaten üyeyse 409'a çevrilecek hata. |

Doğrulama: her veritabanında politika / view / trigger / RLS açık tablo sayıları ve `version_num = 0004`
raporlanır. 0003 sonrası 18/9/16/17 idi; ajan 0004 sonrası beklenen sayıları **önce hesaplayıp gerekçesiyle
yazar**, sonra ölçer. Uygulama sırası önceki adımlarla aynı: `panosu_test` sıfırdan → tam pytest → `panosu_demo`
→ her şey yeşilse canlı `panosu` (onaylı).

## Bölüm 2: Kimlik altyapısı (`servisler/kimlik.py`; FastAPI import etmez)
### Parola
- `argon2.PasswordHasher()` varsayılanları (RFC 9106'nın düşük bellek profili: Argon2id, 64 MiB, 3 geçiş,
  4 paralel). Ajan sunucuda bir özetin süresini ölçüp rapora yazar (hedef 50–500 ms).
- Kural (NIST SP 800-63B): **en az 10, en çok 128 karakter**; büyük harf/rakam/özel karakter zorunluluğu yok.
  E-posta adresinin kendisi parola olamaz.
- Girişte `check_needs_rehash` doğruysa `parola_ozeti_guncelle` çağrılır.
- **Zamanlama eşitliği:** e-posta yoksa da sabit bir sahte özete karşı doğrulama yapılır; "e-posta yok" ile
  "parola yanlış" aynı sürede ve aynı yanıtla (401, "E-posta veya parola hatalı") döner. Kilitli hesapta da
  aynı yanıt.

### Tokenlar
- Erişim tokenı: JWT, HS256. Alanlar: `sub` (kullanici_id), `isl` (seçili isletme_id veya yok), `typ`="erisim",
  `iat`, `exp` (15 dk). Çözümlemede `algorithms=["HS256"]` sabit (alg=none saldırısı), `exp`, `sub`, `typ` zorunlu.
- İmza anahtarı: `PANOSU_JWT_GIZLI`, en az 32 bayt rastgele (`python -c "import secrets; print(secrets.token_urlsafe(32))"`).
  Yoksa veya kısaysa uygulama **açılmaz**. `.env`'e yazılır, hiçbir çıktıda görünmez (Kural 7).
- Yenileme tokenı: `secrets.token_urlsafe(32)` (256 bit), veritabanında yalnızca SHA-256 özeti. 30 gün.
- Davet kodu: `secrets.token_urlsafe(16)` (128 bit), yalnızca SHA-256 özeti saklanır; kod yalnızca oluşturma
  yanıtında bir kez görünür.

### `config.py` eklemeleri
`jwt_gizli: SecretStr`, `erisim_suresi_dk: int = 15`, `yenileme_suresi_gun: int = 30`, `acik_kayit: bool = False`
(geliştirme `.env`'inde `PANOSU_ACIK_KAYIT=true`).

### `bagimliliklar.py`
- `kimlik_al` (başlık tabanlı) **silinir**. Yerine `kimlik_dogrula`: `Authorization: Bearer` okur, tokenı doğrular,
  `Kimlik(kullanici_id, isletme_id | None)` döner. Eksik/geçersiz/süresi geçmiş → 401 (`WWW-Authenticate: Bearer`).
- `kiraci_db`: `isletme_id` yoksa 403 "İşletme seçilmedi". Mevcut üyelik/rol kontrolü **aynen kalır**. Ek olarak
  işletmenin `durum`'u 'aktif' değilse 403.
- `kullanici_db` (yeni): yalnızca `app.kullanici_id` ayarlı oturum (işletme seçmeden önceki uçlar için).
- `database.py`'deki `after_begin` mekanizmasına dokunulmaz.

## Bölüm 3: Uçlar (`rotalar/kimlik.py`, `rotalar/davetler.py`; şemalar `semalar/kimlik.py`)
| Uç | Kim | Davranış |
|---|---|---|
| `POST /kayit` | herkes, yalnız `acik_kayit` açıkken (kapalıysa 404) | {eposta, ad_soyad, parola, isletme_adi, sektor?} → tek işlemde `kullanici_kaydet` + `isletme_olustur` → 201 + token çifti (işletme seçili). E-posta var → 409. |
| `POST /oturum/giris` | herkes | {eposta, parola} → 200 + token çifti. Tek üyelik varsa o işletme seçili gelir; 0 veya birden fazlaysa `isl` boş, yanıtta üyelik listesi. Hata → 401 (tek tip mesaj). |
| `POST /oturum/yenile` | herkes | {yenileme_tokeni} → yeni çift (eskisi bir daha kullanılamaz) \| 401. |
| `POST /oturum/cikis` | herkes | {yenileme_tokeni} → 204 (aile iptal). |
| `POST /oturum/isletme-sec` | giriş yapmış | {isletme_id, yenileme_tokeni} → üyelik doğrulanır, seçim yenileme oturumuna da yazılır (`oturum_isletme_degistir`) → yeni erişim tokenı \| 403. |
| `GET /ben` | giriş yapmış | kullanıcı bilgisi + üyelikler (işletme adı, rol). |
| `POST /davetler` | sahip, yonetici | {rol} → 201 {kod, son_kullanma}. Yönetici yalnızca 'calisan' davet eder (aksi 403). |
| `GET /davetler` | sahip, yonetici | açık davetler (kod yok). |
| `POST /davetler/{davet_id}/iptal` | sahip, yonetici | 204. |
| `POST /davetler/kabul` | giriş yapmış | {kod} → üyelik eklenir \| 404 (geçersiz/süresi geçmiş/kullanılmış, tek tip) \| 409 zaten üye. |
| `POST /kayit/davet` | herkes (`acik_kayit`'tan bağımsız) | {kod, eposta, ad_soyad, parola} → kullanıcı + üyelik → 201 + token çifti. |
| `GET /uyeler` | sahip, yonetici | işletmenin üyeleri ve rolleri. |
| `DELETE /uyeler/{kullanici_id}` | sahip | üyeliği siler (sahip kendini silemez; son sahip silinemez → 409). |

Token çifti yanıtı: `{erisim_tokeni, yenileme_tokeni, token_turu: "bearer", erisim_bitis_sn, isletme_id | null}`.

## Bölüm 4: Komutlar
- `python -m servisler.isletme_ac --veritabani <ad> --eposta <e> --ad-soyad <a> --isletme <ad> [--sektor spor_salonu]`:
  pilot işletme ve sahibini açar. Parola `getpass` ile sorulur, hiçbir çıktıya yazılmaz. Kilit: yalnızca `_demo`/`_test`;
  canlı `panosu` için ayrı onay ve `--canli-onay` bayrağı ile (ajan canlıda **çalıştırmaz**).
- `python -m sentetik.demo_kullanici --veritabani panosu_demo`: `demo@panosu.local` kullanıcısını [DEMO] Denge
  Pilates ve [DEMO] Butik Reformer'a **sahip** olarak bağlar. Parola `PANOSU_DEMO_PAROLA`'dan veya `getpass`'ten.
  Yükleyici kilidi geçerli (yalnızca `_demo`). Tekrar çalıştırmak idempotent (parolayı günceller).

## Bölüm 5: Testlerin geçişi
- `tests/conftest.py`: `pytest_configure` test için rastgele bir `PANOSU_JWT_GIZLI` ayarlar (yoksa).
  `basliklar(kiraci)` artık `{"Authorization": "Bearer <kiraci için imzalanmış token>"}` döner. Mevcut testlerin
  çağrıları değişmez; yalnızca bu fonksiyonun içi değişir. `_kiraci_temizle`'ye `davetler` eklenir
  (oturumlar ve kimlik bilgileri CASCADE ile silinir).
- `test_guvenlik_bekcisi.py` ve `test_izolasyon_db.py` değişmez ve yeşil kalır.

## Testler (yeni: `tests/test_kimlik_api.py`, `tests/test_kimlik_db.py`, `tests/test_davet_api.py`)
Kimlik ve token:
- Kayıt → 201; aynı e-posta (büyük/küçük harf farkıyla) → 409; `acik_kayit` kapalıyken 404; kısa parola 422.
- Kayıt sonrası kullanıcı işletmenin 'sahip'i ve ücretsiz aboneliği var.
- Giriş: doğru parola 200; yanlış parola ve olmayan e-posta **aynı** gövde ve 401.
- 5 hatalı denemeden sonra doğru parola da 401; kilit süresi geçince (saat ilerletilerek / `kilit_bitis` geçmişe çekilerek) 200.
- Token: imzası bozuk, süresi geçmiş, `alg=none`, `typ` yanlış, başlıksız → 401. Eski `X-Kullanici-Id` başlıkları → 401.
- Token'daki `isl`, kullanıcının üyesi olmadığı bir işletmeyse → 403 (kiraci_db).
- Üyelik silindikten sonra **aynı token** ile istek → 403 (rolün her istekte DB'den okunduğunun kanıtı).
- Yenileme: yeni çift alınır; eski yenileme tokenı ikinci kez → 401 **ve** o ailedeki yeni token da artık 401.
- Çıkış sonrası yenileme → 401.
- İşletme seçme: üye olunan işletme 200; olunmayan 403.
Veritabanı:
- `panosu_app` `kullanici_kimlik_bilgileri` ve `oturumlar` tablolarını SELECT edemez (yetki hatası).
- Tüm yeni SECURITY DEFINER fonksiyonlarında `search_path` ayarlı (`pg_proc.proconfig` kontrolü) ve PUBLIC'in EXECUTE yetkisi yok.
- Veritabanında hiçbir yerde düz parola yok: kayıttan sonra özet `$argon2id$` ile başlıyor ve parolayı içermiyor.
Davet:
- Sahip 'yonetici' ve 'calisan' davet eder; yönetici 'yonetici' davet edemez (403); calisan davet oluşturamaz (403).
- Kod bir kez kullanılır; ikinci kullanım 404; süresi geçmiş 404; iptal edilmiş 404.
- Başka kiracının davetini listeleyemez/iptal edemez (404).
- `/kayit/davet` ile gelen kullanıcı doğru rolle üye olur.
- Son sahip silinemez (409).

## Kapsam dışı (bilerek)
E-posta doğrulama, parola sıfırlama (Adım 11); çerez + CSRF (Adım 9); iki adımlı doğrulama; işletme sahipliği
devri; IP bazlı hız sınırı (yalnızca hesap bazlı kilit var); partner firmalar için API anahtarı (aşağıdaki nota bak).

## CLAUDE.md güncellemeleri
- Yol haritası: 8 "Tamam". 4b satırındaki "(Faz 0'dan gerçek veri formatı gelince, 8'den önce)" ifadesi
  "(gerçek Faz 0 verisi gelince; 8'e bağlı değil)" olarak değişir.
- Komutlar bölümüne `isletme_ac` ve `demo_kullanici`.
- Değiştirilemez kurallar 3'e ek: "`isletme_id` yalnızca imzalı erişim tokenından okunur; işletme seçme ucunda
  istemcinin önerdiği değer üyelik doğrulanmadan kullanılmaz."
- Kural 7'ye ek: "`PANOSU_JWT_GIZLI` ve demo parolası hiçbir çıktıda görünmez."
- README'deki uçlar tablosuna kimlik uçları ve "Durum" satırının güncellenmesi.

## Kabul kriterleri ve rapor
- Tam `pytest -q` yeşil, skip/xfail yok; `python -c "import main"` hatasız; `/docs`'ta "Kimlik" ve "Davetler" grupları.
- Rapor (`raporlar/rapor-8.md`; sohbette yalnızca özet):
  1. Kurulan paketler ve sürümleri.
  2. Üç veritabanında migration sonrası sayılar (beklenen ve ölçülen) ve `version_num`.
  3. Sunucuda bir Argon2id özetinin ölçülen süresi.
  4. `panosu_demo`'da demo kullanıcıyla giriş → `/ben` → `/panel/finans` akışının çıktısının özeti (token yazılmaz).
  5. Talimattan her sapma.
- Commit ve push onaylı (raporlar/, veri/, .env hariç).

## Matematik notu (savunabilmen için)
1. **Neden parola için yavaş özet, token için SHA-256 yeterli?** Güvenlik, saldırganın deneme sayısı ile arama
   uzayının oranıdır. İnsanların seçtiği parolalar düşük entropilidir (sık kullanılan 10 000 parola listesi
   ≈ 13 bit). Veritabanı sızarsa saldırgan çevrimdışı dener; Argon2id her denemeyi 64 MiB bellek gerektiren bir
   işe çevirir: 24 GB'lık bir ekran kartı aynı anda en fazla 24·1024/64 ≈ 384 deneme yürütebilir. Yenileme tokenı
   ise 256 bit rastgeledir: tek denemede tutturma olasılığı 2⁻²⁵⁶. Burada yavaşlatmaya gerek yok; hızlı ve
   tek yönlü bir özet yeter.
2. **Kilit neden tek başına yetmez?** 15 dakikada 5 deneme = günde en fazla 480 deneme. Parola en sık 10 000
   parola arasından (eşit olasılıkla) seçilmişse, saldırganın bir günde bulma olasılığı ≈ 480/10 000 ≈ %4.8;
   yaklaşık 10 günde %50'ye, 3 haftada %100'e ulaşır. Bu yüzden kilit + en az 10 karakter kuralı birlikte çalışır.
3. **Erişim tokenı neden 15 dakika?** İptal gecikmesi = token ömrü. Ama rol ve üyelik her istekte veritabanından
   okunduğu için yetki değişiklikleri zaten anında geçerli. Token ömrü yalnızca "çıkış yaptım ama çalınmış token
   15 dk daha çalışır" riskini belirler. Ömür kısaldıkça yenileme isteği artar: 8 saatlik iş gününde
   480/15 = 32 yenileme isteği, ihmal edilebilir yük.
4. **Çalıntı yenileme tokenı nasıl yakalanır?** Her token tek kullanımlık. Aynı token iki kez geliyorsa iki
   taraftan biri (kullanıcı veya saldırgan) eski kopyayı kullanıyor demektir; hangisi olduğunu bilemeyiz, bu
   yüzden aileyi tümden iptal ederiz. Gerçek kullanıcı bir kez yeniden giriş yapar, saldırgan dışarıda kalır.

## Ürün notu: firmalara modül olarak sunarken
Stuvio, GymKod, BulutGym gibi firmalar Panosu'yu kendi yazılımlarına **modül** olarak bağlarsa, onların
sunucusu sizin API'nize kullanıcı parolasıyla değil, **firma başına API anahtarıyla** (makineden makineye)
bağlanır. Bu adımın token altyapısı bunun temelidir ama API anahtarı ayrı bir adımdır; ilk ciddi görüşmeden
sonra, firmanın entegrasyon biçimi netleşince tasarlanmalıdır.

## Uygulama notları (2026-10-01)
Aşama 1'de proje sahibince kabul edilen sapmalar:
1. `argon2-cffi`, zorunlu bağımlılığı `argon2-cffi-bindings`'i de getirir; o da `requirements.txt`'e sabitlendi.
2. `kullanici_kimlik_bilgileri.parola_ozeti` için `CHECK (parola_ozeti LIKE '$argon2id$%')`: düz parola yazılamaz.
3. `oturumlar.secili_isletme_id` FK'si `ON DELETE SET NULL` (demo temizliği işletme silebilir).
4. `oturum_ac` ve `oturum_isletme_degistir` üyeliği veritabanında da denetler (savunma derinliği).
5. Beşinci hatalı girişte 15 dk kilitle birlikte sayaç sıfırlanır ("15 dakikada en fazla 5 deneme").

Karar (çelişki çözümü): `POST /oturum/isletme-sec` gövdesi `{isletme_id, yenileme_tokeni}`; `oturum_isletme_degistir`
fonksiyon imzası değişmez.

Adım 11 notu: politikasız FORCE RLS tablolarına (`kullanici_kimlik_bilgileri`, `oturumlar`) SECURITY DEFINER
fonksiyonları bugün yalnızca sahipleri (postgres) süper kullanıcı olduğu için erişebilir. Canlıda migration/fonksiyon
sahibi süper kullanıcı değilse bu role BYPASSRLS gerekir (aksi hâlde fonksiyonlar hiçbir satır görmez).
