# Rapor (dosya değişikliği yok, `panosu`'ya yazma yok)

Tarih: 2026-10-01

`CLAUDE.md` ve `docs/adim-4a.md` dosyalarını okudum. Yalnızca testler `panosu_test`'e yazdı, onlar da kendi verilerini sildi (koşudan sonra tüm tablolar 0 satır).

## 1. `sentetik/` klasörü

| Dosya | Ne yapıyor |
|---|---|
| `__init__.py` | Paket tanımı, içinde yalnızca açıklama metni var. |
| `katalog.py` | 4 sektörün hizmet kataloğunu, BG/NBD parametrelerini (r, ortalama aralık, bırakma olasılığı) ve isim listelerini tutuyor. |
| `uretici.py` | Veritabanına dokunmadan numpy ile müşteri, ziyaret, kalem ve izin verisini, her müşterinin gizli gerçek parametreleriyle birlikte üretiyor. |
| `degerlendirme.py` | V1 churn modelini (`MusteriAnalizi.py`) gerçek kayıp etiketlerine karşı ROC AUC ile ölçüyor. |
| `yukleyici.py` | Üretilen veriyi PostgreSQL'e yüklüyor, `[DEMO]` verisini silebiliyor, CSV'yi yazıyor. |
| `__main__.py` | `python -m sentetik` komut satırı aracı: üretiyor, özetliyor, değerlendiriyor ve `--sadece-uret` verilmediyse yüklüyor. |

**`yukleyici.py`'nin bağlantıları:**
- **İş verisi:** `PANOSU_VERITABANI_URL` → `postgresql+psycopg2://panosu_app:***@localhost:5432/panosu`. `panosu_app` rolüyle, RLS altında yazıyor.
- **Yönetici işleri:** `PANOSU_MIGRASYON_URL` → `postgresql+psycopg2://postgres:***@localhost:5432/panosu`. Süper kullanıcı. Demo sahibi kullanıcıyı oluşturuyor ve `--temizle` ile silme yapıyor.
- Yükleyicinin veritabanı adını kontrol eden bir koruması yok. `.env` canlıyı gösterdiği için canlıya yazdı.

**`veri/gercek_degerler.csv`'yi kim üretiyor:** `sentetik/yukleyici.py` içindeki `gercek_degerleri_yaz()`. Bu fonksiyonu `sentetik/__main__.py` yüklemeden sonra çağırıyor.

## 2. Canlı `panosu`, salt-okunur sayım

`SET TRANSACTION READ ONLY` ile sorguladım.

| Tablo | Satır |
|---|---|
| isletmeler | 4 |
| musteriler | 1.600 |
| ziyaretler | 31.604 |
| ziyaret_kalemleri | 41.158 |
| hizmetler | 25 |
| churn_skorlari | 0 |

İşletmeler, 2026-10-01 00:02:44 ile 00:02:48 arasında oluşturulmuş:
- `[DEMO] Usta Berber` (berber)
- `[DEMO] Nazlı Kuaför` (kuafor)
- `[DEMO] Işıltı Güzellik Merkezi` (guzellik)
- `[DEMO] Denge Pilates Stüdyosu` (spor_salonu)

Canlıda gerçek işletme verisi yok, satırların hepsi sentetik.

## 3. Adım 4a'nın durumu

**Karşılananlar:**
- Tanımdaki 8 dosyanın hepsi var ve `main.py`'ye bağlanmış.
- `python -c "import main"` hatasız çalışıyor.
- OpenAPI'de **Hizmetler 4 uç**, **Ziyaretler 5 uç** görünüyor. Uçlar, roller ve durum kodları tanımla birebir aynı.
- Servis kuralları uygulanmış: Decimal hesap, tek işlem, liste fiyatının devralınması, uyumsuz toplamda 422, negatif kalemde 422, 5 dakikalık gelecek toleransı, saat dilimsiz zamanın `isletmeler.saat_dilimi` ile yorumlanması, pasif hizmetin kabul edilmesi, `musteri_getir` ile 404.
- 409 kısıt adı `e.orig.diag.constraint_name` üzerinden `hizmetler_isletme_id_ad_key` olarak okunuyor.
- Özet `v_musteri_ozet` view'ından `text()` ile alınıyor. View `security_invoker=true` olduğu için RLS geçerli.
- Tanımın 3. bölümündeki her test maddesi için bir test var. Ayrıca fazladan testler de eklenmiş.

**Tanımdan farklı olanlar (onayınız gereken yorumlar):**
1. **`GET /hizmetler?aktif=`:** Sorgu parametresi olarak null gönderilemiyor. Bu yüzden boş değer "tümü" (`None`) olarak yorumlanmış. Tanım "None gönderilirse tümü" diyor ama bunun nasıl gönderileceğini söylemiyor.
2. **Hizmet kalemdeki 422 mesajı:** `"1. kalem: Hizmet bulunamadı"`. Tanımda yalnızca `"Hizmet bulunamadı"` var, sıra öneki eklenmiş.
3. **Tanımda olmayan ek doğrulamalar:**
   - `HizmetGuncelle`'de `ad: null` ve `aktif_mi: null` → 422.
   - `ZiyaretGuncelle`'de `durum: null` → 422.
   - `KalemGirdi.aciklama` kırpılıyor ve en az 1 karakter olmalı.
   - `birim_fiyat` ve `indirim_tutari` için 12 basamak / 2 ondalık sınırı var. Tanım bunu yalnızca `liste_fiyati` için söylüyor.
4. **Kapsam dışı yeniden düzenleme:** Adım 3 kodu değiştirilmiş.
   - Yeni `semalar/ortak.py` (`KismiGuncelleme`, `Para`) ve `servisler/ortak.py` (`kaydet`) oluşturulmuş.
   - `semalar/musteri.py` ve `servisler/musteri_servisi.py` bunları kullanacak şekilde düzenlenmiş.
   - `calisan` fixture'ı `test_musteri_api.py`'den `conftest.py`'ye taşınmış ve `lock_timeout` eklenmiş.
   - Müşteri testleri yeşil, ama bu değişiklikler tanımda istenmemişti.
5. **`ZiyaretYanit.durum` tipi:** `Literal` yerine `str` olarak tanımlanmış (küçük bir fark).

**Eksikler:**
- `CLAUDE.md` yol haritası güncellenmedi. Adımın onayı beklendiği için bu doğru.
- Commit yok.
- `.gitignore`'a `veri/` satırı çalışma kopyasında eklenmiş ama commit'lenmemiş.

## 4. `pytest -v` (`panosu_test`)

```
======================== 81 passed, 1 warning in 8.23s ========================
```
- **Kırmızı test yok.** FAILED, ERROR, SKIPPED ya da XFAIL görünmüyor.
- **Uyarı:** `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`. Giderilmesi yeni bir paket gerektiriyor, bu yüzden onayınız lazım.
- **Çalıştırma yöntemi (talimattan sapma):** `PANOSU_TEST_APP_URL` ve `PANOSU_TEST_ADMIN_URL` hiçbir yerde tanımlı değil (ne `.env`'de ne kullanıcı ortamında). Bu URL'leri `.env`'deki iki bağlantıdan yalnızca veritabanı adını `panosu_test` yaparak, sadece bu işlem için ürettim. Hiçbir dosyaya yazılmadı, parolalar çıktıda maskelendi. `conftest.py`'nin `_test` son eki koruması da devredeydi.

Burada duruyorum. Adım 4a'yı tamamlamak ve veritabanını temizlemek için onayınızı bekliyorum. Özellikle 3. bölümdeki 1–4 numaralı maddeleri kabul edip etmediğinizi bildirin.
