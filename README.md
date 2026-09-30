# Panosu — Müşteri Zekâ Platformu

Tekrar eden müşterisi olan işletmeler (salon, spor salonu, klinik vb.) için **çok kiracılı (multi-tenant) müşteri analitiği backend'i**.
Amaç: hangi müşterinin kaybedilmek üzere olduğunu (churn) olasılıksal olarak tahmin etmek ve bunu **"Riskteki Para"** olarak göstermek.

> Durum: **v0.1 — Faz 0 tamamlandı** (veritabanı, güvenlik katmanı, API iskeleti, testler). Analitik modüller yol haritasında.

---

## Öne çıkanlar

- **Veritabanı katmanında kiracı izolasyonu:** Tüm işletmeler tek PostgreSQL veritabanını paylaşır; izolasyon uygulama kodundaki `WHERE` filtrelerine değil, **Row-Level Security (RLS)** politikalarına dayanır. Koddaki bir hata bile başka işletmenin verisini sızdıramaz.
- **En az yetki ilkesi:** Uygulama, RLS'yi atlayamayan ve tablo oluşturamayan kısıtlı `panosu_app` rolüyle bağlanır. Şema değişiklikleri yalnızca ayrı bir DDL rolüyle, Alembic üzerinden yapılır.
- **Kiracı bütünlüğü:** Alt tablolar `(isletme_id, x_id)` bileşik yabancı anahtarlarıyla bağlıdır; bir işletmenin ziyareti başka işletmenin müşterisine bağlanamaz.
- **Güvenlik bekçisi testleri:** `create_all()` gibi RLS'siz tablo üretebilecek çağrıları, süper kullanıcıyla bağlanmayı ve rol ayrıcalıklarını otomatik yakalayan testler.
- **Denetim ve KVKK dostu tasarım:** Değişiklikler trigger'larla `denetim_kayitlari` tablosuna yazılır; izni olmayan müşteriye mesaj gönderimi veritabanında engellenir; müşteri anonimleştirme fonksiyonu mevcuttur.
- **35 otomatik test:** izolasyon, güvenlik, API ve veri doğrulama.

---

## Mimari

```mermaid
flowchart LR
    C[İstemci] -->|HTTP| R[FastAPI rotaları<br/>rotalar/]
    R --> V[Pydantic şemaları<br/>semalar/]
    R --> K[Kimlik ve kiracı bağlamı<br/>bagimliliklar.py]
    R --> S[İş mantığı<br/>servisler/]
    S --> O[SQLAlchemy ORM<br/>models.py]
    O -->|panosu_app rolü<br/>app.isletme_id| DB[(PostgreSQL<br/>RLS politikaları)]
    M[Alembic migrasyonları] -->|DDL rolü| DB
```

| Katman | Dosya / klasör | Görev |
|---|---|---|
| Giriş | `main.py` | Uygulamayı ve rotaları birleştirir |
| Rotalar | `rotalar/` | HTTP uçları; servis hatalarını HTTP kodlarına çevirir |
| Doğrulama | `semalar/` | Pydantic v2 istek/yanıt şemaları |
| İş mantığı | `servisler/` | Müşteri işlemleri, E.164 telefon normalleştirme |
| Bağlam | `bagimliliklar.py`, `database.py` | Her işlem başında aktif işletme/kullanıcıyı PostgreSQL'e bildirir |
| Veri modeli | `models.py` | Kullanıcı, İşletme, Üyelik, Müşteri, Hizmet, Ziyaret, ZiyaretKalemi |
| Şema | `faz1_sema.sql`, `alembic/` | Tablolar, RLS, view'lar, trigger'lar, GRANT'lar |
| Analiz | `MusteriAnalizi.py` | Churn risk modeli (V1 çekirdek) |
| Testler | `tests/` | İzolasyon, güvenlik bekçisi, API ve birim testleri |

### Veritabanı öne çıkanları
- **Tablolar:** işletmeler, kullanıcılar, üyelikler, müşteriler, hizmetler, ziyaretler, ziyaret kalemleri, churn skorları, kampanyalar, mesaj gönderimleri, geri kazanımlar, müşteri izinleri, denetim kayıtları
- **Hazır raporlar (view):** `v_riskteki_para_paneli`, `v_musteri_ozet`, `v_guncel_churn_skorlari`, `v_geri_kazanim_ozeti`, `v_musteri_hizmet_dagilimi` — hepsi `security_invoker` ile RLS'ye tabidir

---

## Churn risk modeli (V1)

Her müşterinin ziyaretleri arasındaki gün farklarından kişisel bir **geliş ritmi** çıkarılır:

$$\text{aralık}_i \sim \mathcal{N}(\mu, \sigma^2)$$

Son ziyaretten bu yana geçen gün $r$ ise risk, *"müşterinin şimdiye kadar geri dönmüş olması gerekirken dönmemiş olma"* olasılığıdır:

$$\text{risk} = \Phi\left(\frac{r - \mu}{\sigma_{\text{etkin}}}\right), \qquad \sigma_{\text{etkin}} = \max(\sigma,\; 0.25\,\mu)$$

Taban değer, çok düzenli müşterilerde $\sigma \to 0$ olduğunda riskin ani sıçramasını önler. Risk değeri dört segmente ayrılır: **Güvenli** (< 0.35), **İzlenmeli** (< 0.75), **Yüksek Risk** (< 0.95), **Kritik**.

> Sonraki fazlarda bu model, olasılıksal CLV (BG/NBD + Gamma-Gamma), sağkalım analizi ve makine öğrenmesi modelleriyle karşılaştırılacaktır.

---

## API uçları

| Metot | Yol | Açıklama |
|---|---|---|
| `GET` | `/saglik` | Veritabanı bağlantı kontrolü |
| `POST` | `/musteriler` | Müşteri oluştur (aynı telefon → `409`) |
| `GET` | `/musteriler` | Müşterileri listele / ara |
| `GET` | `/musteriler/{id}` | Müşteri detayı |
| `PATCH` | `/musteriler/{id}` | Müşteri güncelle |
| `DELETE` | `/musteriler/{id}` | Müşteri sil |

Sunucu çalışırken etkileşimli dokümantasyon: `http://127.0.0.1:8000/docs`

---

## Kurulum

**Gereksinimler:** Python 3.12+, PostgreSQL 15+

```bash
# 1. Bağımlılıklar
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# 2. Ayarlar: .env.example dosyasını .env olarak kopyalayıp parolaları doldurun

# 3. Veritabanı
createdb -U postgres panosu
psql -U postgres -d panosu -c "CREATE ROLE panosu_app NOLOGIN;"
alembic upgrade head
psql -U postgres -d panosu -c "ALTER ROLE panosu_app WITH LOGIN PASSWORD 'parolaniz';"

# 4. Sunucu
uvicorn main:app --reload
```

### Testler
Testler veri ekleyip sildiği için **adı `_test` ile biten ayrı bir veritabanında** çalışır (ör. `panosu_test`, aynı şema kurulu olmalı):

```bash
set PANOSU_TEST_APP_URL=postgresql+psycopg2://panosu_app:PAROLA@localhost:5432/panosu_test
set PANOSU_TEST_ADMIN_URL=postgresql+psycopg2://postgres:PAROLA@localhost:5432/panosu_test
pytest
```

---

## Yol haritası

| Sürüm | İçerik | Durum |
|---|---|---|
| `v0.1` | Çok kiracılı şema, RLS, FastAPI iskeleti, izolasyon ve güvenlik testleri | ✅ |
| `v0.2` | Sentetik veri motoru (Poisson ziyaretler, Gamma harcamalar, gizli churn süreci) | ⏳ |
| `v0.3` | RFM segmentasyonu, kohort analizi, ilk Streamlit panosu | ⏳ |
| `v0.4` | BG/NBD + Gamma-Gamma CLV modelleri (sıfırdan, scipy ile) | ⏳ |
| `v0.5` | Sağkalım analizi (Kaplan-Meier, Cox) ve XGBoost + SHAP | ⏳ |
| `v0.6` | Kampanya simülatörü (beklenen değer, bütçe optimizasyonu, A/B güç analizi) | ⏳ |
| `v1.0` | Docker, CI, canlı demo | ⏳ |

---

## Teknolojiler

Python · FastAPI · SQLAlchemy 2 · Pydantic v2 · PostgreSQL (RLS, PL/pgSQL, view, trigger) · Alembic · pytest

## Geliştirici

**Hüseyin Aytekin** — Sakarya Üniversitesi, Matematik
