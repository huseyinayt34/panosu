# Panosu: Müşteri Davranış Panosu (çok kiracılı SaaS)

Küçük işletmeler (berber, kuaför, kafe, spor salonu) için geri kazanma motoru: her müşterinin churn
riskini ve **Riskteki Para**'yı (kaybedilmek üzere olan ciro) hesaplar, işletmeye "şu kişilere yaz"
listesi verir, mesajdan sonra geri kazanılan ciroyu ölçer. Stok/muhasebe/adisyon (ERP) kapsam dışı.

Rol dağılımı: mimari, ürün mantığı ve matematik kararları proje sahibinindir (Hüseyin). Ajan kodu
yazar. Tasarım kararı gerektiren bir belirsizlikte tahminle ilerleme; sor.

## Teknoloji
Python 3.14, FastAPI, SQLAlchemy 2.0 (Mapped/mapped_column), Pydantic v2, PostgreSQL 15+, Alembic,
pytest. Windows + PowerShell. Sanal ortam: `.venv`.

## Dosya yapısı ve bağımlılık yönü
```
main.py → rotalar/ → (bagimliliklar.py, servisler/, semalar/) → models.py → database.py → config.py
```
- `rotalar/`: HTTP katmanı. Servis istisnalarını HTTP kodlarına çevirir. `rotalar/web.py`: web paneli HTML uçları
  (çerezli oturum, CSRF; `docs/adim-9-tasarim.md`).
- `servisler/`: iş kuralları. FastAPI import ETMEZ, HTTPException fırlatmaz.
- `semalar/`: Pydantic istek/yanıt şemaları.
- `models.py`: yalnızca sütunları yansıtır. Şemanın tek kaynağı SQL'dir.
- `faz1_sema.sql`: okunabilir şema kaynağı. `alembic/sql/0001_faz1_sema.sql`: aynısı, BEGIN/COMMIT'siz.
- `sentetik/`: BG/NBD tabanlı sentetik veri üreticisi. Yükleyici yalnızca adı `_demo` ile biten veritabanına yazar.
  `demo_tazele`: [DEMO] işletmelerin tarihlerini bugüne kaydırır (K11–K16, `docs/adim-9-tasarim.md`).
- `analitik/`: modeller (V1, BG/NBD, MBG/NBD, Gamma-Gamma, yenileme simülasyonu), açıklama (neden riskli); veritabanı bilmez.
- `backtest/`: sentetik senaryolarda model karşılaştırması (S0–S6); veritabanı yok.
- `sablonlar/`: Jinja2 HTML şablonları (haftalık rapor). `sablonlar/web/`: web paneli şablonları.
- `statik/`: web paneli statik dosyaları (htmx.min.js 2.0.4, panel.css); `/statik` altında sunulur.

## Değiştirilemez kurallar
1. `create_all` / `drop_all` / `reflect` kullanılmaz. `alembic/` dışında DDL yazılmaz.
   `tests/test_guvenlik_bekcisi.py` bunu denetler.
2. `faz1_sema.sql`, `alembic/sql/*`, `tests/test_guvenlik_bekcisi.py`, `tests/test_izolasyon_db.py`
   değiştirilmez.
3. Kiracı izolasyonu PostgreSQL RLS ile sağlanır. `isletme_id` asla istemciden alınmaz; sorgulara elle
   `isletme_id` filtresi eklenmez. `database.py`'deki `after_begin` olayı her işlemde
   `app.isletme_id` / `app.kullanici_id` bağlamını ayarlar; bu mekanizma bozulmaz. `isletme_id` yalnızca imzalı
   erişim tokenından okunur; işletme seçme ucunda istemcinin önerdiği değer üyelik doğrulanmadan kullanılmaz.
4. Uygulama `panosu_app` rolüyle bağlanır (RLS'ye tabi, DDL yetkisi yok). Migration'lar
   `PANOSU_MIGRASYON_URL` (DDL yetkili rol) ile çalışır. Autogenerate kullanılmaz; migration'lar elle yazılır.
5. Para hesapları yalnızca `Decimal` ile yapılır, float kullanılmaz.
6. Test silme, zayıflatma, `skip`/`xfail` yok. Güvenlik/izolasyon testi kırmızıysa düzeltmeye çalışma:
   dur ve raporla.
7. Parolalar hiçbir çıktıda, raporda veya commit'te görünmez. `.env` asla commit'lenmez. `PANOSU_JWT_GIZLI` ve demo
   parolası hiçbir çıktıda görünmez.
8. Yeni paket eklemek onay gerektirir.
9. Push (GitHub) yalnızca açık onayla yapılır.
10. Talimatta olmayan yeniden düzenleme (refactor) veya yeni dosya/klasör önce sorulur.

## Veritabanları
| Ad | Amaç | Kural |
|---|---|---|
| `panosu` | Canlı; yalnızca gerçek işletme verisi | Yalnızca salt-okunur sorgu. Her yazma işlemi açık onay ister. `alembic upgrade` asla çalıştırılmaz (yalnızca onaylı `stamp`). |
| `panosu_test` | pytest | Silinip `alembic upgrade head` ile yeniden kurulabilir |
| `panosu_demo` | Sentetik veri, demo, backtest | Kuruldu; 5 [DEMO] işletme, sentetik veri; [DEMO] Denge Pilates'te üyelik paketleri, yenileme riskleri ve 2026-03'ten itibaren her ay 330.000 TL demo gideri (Panosu'ya geçiş ayı) (paket dönemi ziyaret tutarları 0); [DEMO] Butik Reformer: Faz 0 demosu (p ~ Beta(1, 290), ayda 5 yeni üye; ~75 aktif üye, 18 ay paket/ziyaret geçmişi, her ay gider). Yükleyici yalnızca _demo adlarına yazar. Demo sunucusunun her açılışında ve her gece 03:00'te bugüne kaydırılır (K11). |

Sentetik veri ASLA `panosu`'ya yazılmaz.

## Komutlar
```powershell
.\.venv\Scripts\python.exe -m pytest -v          # tam test paketi (panosu_test)
.\.venv\Scripts\python.exe -c "import main"      # import kontrolü
uvicorn main:app --reload                        # geliştirme sunucusu, /docs

.\.venv\Scripts\python.exe -m sentetik --sadece-uret                    # veritabanına dokunmadan üret + V1 ROC AUC
.\.venv\Scripts\python.exe -m sentetik --veritabani panosu_demo          # üret ve panosu_demo'ya yükle
.\.venv\Scripts\python.exe -m sentetik --veritabani panosu_demo --temizle  # eski [DEMO] verisini silip yeniden yükle

.\.venv\Scripts\python.exe -m backtest                  # 6 senaryo × 20 tohum; docs/backtest-sonuclari.md + raporlar/backtest/*.csv
.\.venv\Scripts\python.exe -m backtest --tohum-sayisi 2 # hızlı deneme

.\.venv\Scripts\python.exe -m sentetik.paket_uretici --veritabani panosu_demo    # demo stüdyoya paket (bir kez)
.\.venv\Scripts\python.exe -m sentetik.paket_uretici --veritabani panosu_demo --giderler 2026-10   # demo giderleri
.\.venv\Scripts\python.exe -m sentetik.paket_uretici --veritabani panosu_demo --gecmis-giderler   # 2026-03'ten (ya da ilk ziyaret ayından) bugüne eksik aylar
.\.venv\Scripts\python.exe -m sentetik.paket_uretici --veritabani panosu_demo --gecmis-giderler --guncelle   # ayrıca demo giderlerini güncelle, 2026-03 öncesini sil
# UYARI: paket_uretici --gecmis-giderler takvim başlangıcını (2026-03) kullanır; tazeleme sonrası çalıştırma, gider penceresini bozar.
.\.venv\Scripts\python.exe -m sentetik.butik_reformer --veritabani panosu_demo    # ikinci Faz 0 demosu (bir kez)
.\.venv\Scripts\python.exe -m sentetik.butik_reformer --veritabani panosu_demo --yeniden   # yalnızca Butik Reformer'ı silip yeniden yükle
.\.venv\Scripts\python.exe -m sentetik.demo_kullanici --veritabani panosu_demo    # demo@panosu.local (parola getpass)
.\.venv\Scripts\python.exe -m servisler.isletme_ac --veritabani <ad> --eposta <e> --ad-soyad <a> --isletme <ad>  # pilot işletme (_demo/_test; canlı: --canli-onay, ayrı onayla)
.\.venv\Scripts\python.exe -m servisler.rapor_uret --veritabani panosu_demo --isletme <uuid> --cikti raporlar/haftalik.html
.\.venv\Scripts\python.exe -m servisler.yenileme_calistir --veritabani panosu_demo --isletme <uuid>  # yenileme riski (_demo/_test)
.\.venv\Scripts\python.exe -m sentetik.demo_sunucu                 # web paneli panosu_demo ile, 127.0.0.1:8000 (--port); açılışta ve her gece 03:00'te demo tazeleme
.\.venv\Scripts\python.exe -m sentetik.demo_sunucu --tazeleme-yok  # tazelemesiz
.\.venv\Scripts\python.exe -m sentetik.demo_tazele --veritabani panosu_demo --kuru   # demo tazeleme raporu, yazmaz
.\.venv\Scripts\python.exe -m sentetik.demo_tazele --veritabani panosu_demo          # [DEMO] verisini bugüne kaydır + riskleri yeniden hesapla
```
Test adresleri: `PANOSU_TEST_APP_URL` / `PANOSU_TEST_ADMIN_URL` ortamda tanımlıysa onlar kullanılır; değilse
`tests/conftest.py`, `.env`'deki `PANOSU_VERITABANI_URL` / `PANOSU_MIGRASYON_URL`'den yalnızca veritabanı adını
`panosu_test` yaparak türetir. Her iki durumda da adı `_test` ile bitmeyen veritabanında testler çalışmaz.

Sentetik veri yükleyicisi: hedef `--veritabani` ile zorunlu olarak verilir (yalnızca `--sadece-uret`'te gerekmez);
bağlantı adresleri `.env`'deki iki URL'den yalnızca veritabanı adı değiştirilerek türetilir. Ad `_demo` ile
bitmiyorsa bağlantı kurulmadan hata verir. Gerçek değerler `veri/gercek_degerler.csv`'ye yazılır (commit'lenmez).

Boş bir veritabanına şema kurmak: `PANOSU_MIGRASYON_URL` yalnızca o komut için hedef veritabanını
gösterecek şekilde `alembic upgrade head`.

## Yol haritası
| # | Adım | Durum |
|---|---|---|
| 1 | Güvenlik kilidi (RLS, bekçi testleri) | Tamam |
| 2 | Alembic baseline | Tamam |
| 3 | Müşteri API'si | Tamam |
| 4a | Hizmetler + ziyaretler API'si, sentetik veri motoru (yalnızca _demo veritabanlarına yazar) | Tamam |
| 5a | Model kütüphanesi: V1, BG/NBD, MBG/NBD, Gamma-Gamma, Riskteki Para (veritabanı yok; tasarım: `docs/adim-5-6-tasarim.md`) | Tamam |
| 6 | Backtest: V1, BG/NBD ve MBG/NBD'nin sentetik veride (S0–S5) karşılaştırılması (ROC AUC, kalibrasyon); sonuç: `docs/backtest-sonuclari.md` | Tamam |
| 5b | Sözleşmeli üyelik (paketler), yenileme riski (M3 + simülasyon), S6 backtest, panel ucu (`docs/adim-5b-tasarim.md`) | Tamam |
| 5c | Yenileme modelinin gerçek yenileme verisiyle kalibrasyonu (Faz 0 verisi gelince). Test edilecek hipotezler (proje sahibinin gözlemi): (1) aktif üyelerin yenileme oranı ρ %90'ın üzerinde; (2) önceki yenileme sayısı yenilemenin güçlü habercisi; (3) az gelip yine de yenileyen bir grup var ve model onlara yanlış alarm veriyor olabilir. S6'da Riskteki Para'nın %13 düşük çıkmasının nedeni ρ = 1 varsayımıdır. | Bekliyor |
| 7 | Panel: sessiz üyeler, gelir ve kâr özeti (giderler, başabaş), haftalık rapor (`docs/adim-7-tasarim.md`). Geçmiş ayda başabaş farkı ay ortalamasıyla (K2, `docs/adim-9-tasarim.md`) | Tamam |
| 4b | CSV içe aktarma (gerçek Faz 0 verisi gelince; 8'e bağlı değil). Not: içe aktarmada giriş (check-in) ziyaretlerinin tutarı 0 olmalı; aksi hâlde paket geliri iki kez sayılır. | Bekliyor |
| 8 | Gerçek kimlik doğrulama + işletme kaydı: Argon2id + JWT, tek kullanımlık yenileme tokenı, davet kodları (`docs/adim-8-tasarim.md`). Canlı `panosu` migration'ı ayrı onay bekliyor. | Tamam |
| 8a | Soğuk başlangıç modu (9'dan önce; yalnızca plan): geçmiş verisi az olan işletmede MBG/NBD parametreleri, diğer işletmelerden veya sentetik veriden öğrenilen önsel (prior) ile başlar ve işletmenin verisi geldikçe Bayesçi olarak güncellenir. Bu dönemde panelde tahminler 'ön tahmin' etiketiyle gösterilir. | Planlandı |
| 8b | Otomatik hesaplama (9'dan önce; yalnızca plan): finans paneli her veri girişinde anında, yenileme riskleri her gece otomatik yeniden hesaplanır. (demo için gece tazeleme 9c'de yapıldı; gerçek işletmeler bekliyor) | Planlandı |
| 9 | Web paneli (Jinja + HTMX, FastAPI içinde; `docs/adim-9-tasarim.md`), panosu_demo ile canlı demo | Tamam |
| 10 | İzin, mesaj, geri kazanım ölçümü | Planlandı |
| 11 | Yayına alma: Docker, CI, sunucu, güçlü ve farklı parolalar, ödeme | Planlandı |

Geliştirme fikirleri (karar değil; ilgili adımda tasarlanacak):
- Adım 4b: yapay zekâ ile CSV sütun eşleme önerisi; yoklama defteri fotoğrafından tablo çıkarma.
- Adım 10: kontrol gruplu mesajlaşma ve uplift ölçümü; "uyuyan köpekleri" (ödeyip az gelen üyeleri) rahatsız
  etmeme; geri kazanımın nedensel kanıtı.
- Adım 8a: işletmeler arası hiyerarşik Bayes önselleri.
- Adım 11 sonrası: yazılım firmalarına Skor API'si.

- Araştırma rafı (zaman kalırsa): RFM/kohort, sağkalım analizi (Kaplan-Meier, Cox), XGBoost + SHAP,
  kampanya simülatörü / A-B güç analizi.
  - Kafe/restoran modülü (menü fotoğrafından ürün çıkarma, menü mühendisliği, enflasyon/marj alarmı). Başlama
    koşulu: stüdyo ürünü en az bir gerçek stüdyoda çalışıyor ve bir kafe ürün bazında satış verisi verebiliyor.
  - Veteriner klinikleri: aşı/kontrol döngüsü (ileride değerlendirilecek).
- Faz 0: işletmelerle talep ve veri formatı görüşmeleri. Kod değildir; proje sahibi yürütür.
- Yol haritasının tek kaynağı bu dosyadır. README yalnızca kısa bir özet verir.
- Matematik kararları (model seçimi, varsayımlar) proje sahibinindir. 5a/6'nın onaylı tasarımı
  `docs/adim-5-6-tasarim.md`; 5b'nin onaylı tasarımı `docs/adim-5b-tasarim.md` (ürüne M3 girdi).
- Raporlar raporlar/ klasörüne kaydedilir; bu klasör git'e girmez.

## Açık konular
- Şu an açık konu yok.

## Çalışma şekli
- Her görevin sonunda rapor: değişen dosyalar, pytest özet satırı, talimattan her sapma.
- "Tamamlandı" demek için kanıt gerekir: komut çıktısı veya test sonucu.
- Bir adım bittiğinde bu dosyadaki yol haritası tablosu güncellenir.
