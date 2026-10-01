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
- `rotalar/`: HTTP katmanı. Servis istisnalarını HTTP kodlarına çevirir.
- `servisler/`: iş kuralları. FastAPI import ETMEZ, HTTPException fırlatmaz.
- `semalar/`: Pydantic istek/yanıt şemaları.
- `models.py`: yalnızca sütunları yansıtır. Şemanın tek kaynağı SQL'dir.
- `faz1_sema.sql`: okunabilir şema kaynağı. `alembic/sql/0001_faz1_sema.sql`: aynısı, BEGIN/COMMIT'siz.
- `sentetik/`: BG/NBD tabanlı sentetik veri üreticisi. Yükleyici yalnızca adı `_demo` ile biten veritabanına yazar.

## Değiştirilemez kurallar
1. `create_all` / `drop_all` / `reflect` kullanılmaz. `alembic/` dışında DDL yazılmaz.
   `tests/test_guvenlik_bekcisi.py` bunu denetler.
2. `faz1_sema.sql`, `alembic/sql/*`, `tests/test_guvenlik_bekcisi.py`, `tests/test_izolasyon_db.py`
   değiştirilmez.
3. Kiracı izolasyonu PostgreSQL RLS ile sağlanır. `isletme_id` asla istemciden alınmaz; sorgulara elle
   `isletme_id` filtresi eklenmez. `database.py`'deki `after_begin` olayı her işlemde
   `app.isletme_id` / `app.kullanici_id` bağlamını ayarlar; bu mekanizma bozulmaz.
4. Uygulama `panosu_app` rolüyle bağlanır (RLS'ye tabi, DDL yetkisi yok). Migration'lar
   `PANOSU_MIGRASYON_URL` (DDL yetkili rol) ile çalışır. Autogenerate kullanılmaz; migration'lar elle yazılır.
5. Para hesapları yalnızca `Decimal` ile yapılır, float kullanılmaz.
6. Test silme, zayıflatma, `skip`/`xfail` yok. Güvenlik/izolasyon testi kırmızıysa düzeltmeye çalışma:
   dur ve raporla.
7. Parolalar hiçbir çıktıda, raporda veya commit'te görünmez. `.env` asla commit'lenmez.
8. Yeni paket eklemek onay gerektirir.
9. Push (GitHub) yalnızca açık onayla yapılır.
10. Talimatta olmayan yeniden düzenleme (refactor) veya yeni dosya/klasör önce sorulur.

## Veritabanları
| Ad | Amaç | Kural |
|---|---|---|
| `panosu` | Canlı; yalnızca gerçek işletme verisi | Yalnızca salt-okunur sorgu. Her yazma işlemi açık onay ister. `alembic upgrade` asla çalıştırılmaz (yalnızca onaylı `stamp`). |
| `panosu_test` | pytest | Silinip `alembic upgrade head` ile yeniden kurulabilir |
| `panosu_demo` | Sentetik veri, demo, backtest | Kuruldu; 4 [DEMO] işletme, sentetik veri. Yükleyici yalnızca _demo adlarına yazar. |

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
| 5b | Seçilen modelin churn_skorlari'na bağlanması (backtest sonucundan sonra, ayrı belgeyle) | Sıradaki (model kararı bekleniyor) |
| 7 | Panel API'si: Riskteki Para listesi, işletme özeti | Planlandı |
| 4b | CSV içe aktarma (Faz 0'dan gerçek veri formatı gelince, 8'den önce) | Bekliyor |
| 8 | Gerçek kimlik doğrulama + işletme kaydı | Planlandı |
| 9 | Web paneli (Next.js), panosu_demo ile canlı demo | Planlandı |
| 10 | İzin, mesaj, geri kazanım ölçümü | Planlandı |
| 11 | Yayına alma: Docker, CI, sunucu, güçlü ve farklı parolalar, ödeme | Planlandı |

- Araştırma rafı (zaman kalırsa): RFM/kohort, sağkalım analizi (Kaplan-Meier, Cox), XGBoost + SHAP,
  kampanya simülatörü / A-B güç analizi.
- Faz 0: işletmelerle talep ve veri formatı görüşmeleri. Kod değildir; proje sahibi yürütür.
- Yol haritasının tek kaynağı bu dosyadır. README yalnızca kısa bir özet verir.
- Matematik kararları (model seçimi, varsayımlar) proje sahibinindir. 5a/6'nın onaylı tasarımı
  `docs/adim-5-6-tasarim.md`; 5b'ye hangi modelin gireceğine backtest sonucundan sonra proje sahibi karar verir.
- Raporlar raporlar/ klasörüne kaydedilir; bu klasör git'e girmez.

## Açık konular
Şu an açık konu yok.

## Çalışma şekli
- Her görevin sonunda rapor: değişen dosyalar, pytest özet satırı, talimattan her sapma.
- "Tamamlandı" demek için kanıt gerekir: komut çıktısı veya test sonucu.
- Bir adım bittiğinde bu dosyadaki yol haritası tablosu güncellenir.
