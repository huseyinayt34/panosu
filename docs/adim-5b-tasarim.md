# Adım 5b: Sözleşmeli üyelik, yenileme riski ve Riskteki Para (stüdyolar)

Genel kurallar için `CLAUDE.md`'ye bak. Bu belgedeki matematik ve ürün kararları proje sahibi tarafından
onaylıdır; ajan bunları değiştirmez, sorun görürse durup raporlar.

## Bağlam ve kararlar
- Hedef pazar: müşterisini tanıyan işletmeler, öncelikle **pilates / spor stüdyoları**. Faz 0 bulgusu: stüdyolar
  bir tesis yönetim sistemi kullanıyor (ör. GymTekno), üye girişleri QR/turnike ile kaydediliyor, üyelik
  bitiş tarihi biliniyor.
- Backtest sonucu: ürüne **M3 (MBG/NBD)** girer.
- İki üyelik türü vardır:
  - **Süre bazlı:** ör. 1 ay 2.500 TL, 3 ay 6.000 TL, 6 ay 10.000 TL. Takvimdeki bitiş tarihinde biter.
  - **Giriş bazlı:** ör. 12 giriş 800 TL. Haklar bitince (varsa son kullanma tarihinde) biter.
- Fiyatlar sık değişir: her paket kaydı **kendi satış fiyatını** saklar.
- **Riskteki Para (stüdyo) = (1 − P(yenileme)) × mevcut paketin satış fiyatı.** (Karar A: işletme sahibi
  "kasaya girecek ya da girmeyecek para" ile düşünür.)

## Bölüm 1: Şema (migration 0002)
Dosyalar: `alembic/sql/0002_uyelik_paketleri.sql` ve `alembic/versions/0002_uyelik_paketleri.py`
(baseline ile aynı kalıp: SQL dosyasını `no_parameters=True` ile çalıştırır; downgrade iki tabloyu ve view'ı siler).
`faz1_sema.sql` ve `0001` dosyaları DEĞİŞMEZ.

### `musteri_paketleri`
(`uyelikler` ve `abonelikler` adları kullanıcı üyeliği ve SaaS aboneliği için zaten dolu.)
| Sütun | Tip | Kural |
|---|---|---|
| paket_id | uuid PK | gen_random_uuid() |
| isletme_id | uuid NOT NULL | DEFAULT aktif_isletme() |
| musteri_id | uuid NOT NULL | (isletme_id, musteri_id) → musteriler bileşik FK |
| tur | text NOT NULL | 'sure' veya 'giris' |
| ad | text NOT NULL | ör. '6 Aylık', '12 Giriş' |
| baslangic_tarihi | date NOT NULL | |
| bitis_tarihi | date | tur='sure' ise zorunlu; tur='giris' ise opsiyonel son kullanma |
| giris_hakki | integer | tur='giris' ise zorunlu ve > 0; tur='sure' ise NULL |
| ucret | numeric(12,2) NOT NULL | ≥ 0; satış anındaki fiyat |
| durum | text NOT NULL DEFAULT 'aktif' | 'aktif','bitti','iptal','donduruldu' |
| onceki_paket_id | uuid | aynı müşterinin bir önceki paketi (yenileme zinciri); (isletme_id, onceki_paket_id) bileşik FK |
| dis_kaynak, dis_kimlik | text | içe aktarma tekilliği (müşterilerdeki kalıp) |
| olusturma_zamani, guncelleme_zamani | timestamptz | |
Kısıtlar: bitis_tarihi > baslangic_tarihi (varsa); UNIQUE (isletme_id, paket_id);
dis_kimlik için kısmi tekil indeks; indeks (isletme_id, bitis_tarihi) WHERE durum = 'aktif';
indeks (isletme_id, musteri_id, baslangic_tarihi DESC).

### `yenileme_riskleri`
| Sütun | Tip | Kural |
|---|---|---|
| risk_id | uuid PK | |
| isletme_id | uuid NOT NULL | DEFAULT aktif_isletme() |
| musteri_id, paket_id | uuid NOT NULL | bileşik FK'ler |
| hesaplama_tarihi | date NOT NULL | |
| model_versiyonu | text NOT NULL | ör. 'mbgnbd-sim-v1' (2026-10'dan itibaren 'mbgnbd-map-v2') |
| kalan_gun | integer | süre bazlıda bitişe kalan gün |
| kalan_giris | integer | giriş bazlıda kalan hak |
| p_hayatta_simdi | numeric(5,4) | 0–1 |
| p_yenileme | numeric(5,4) NOT NULL | 0–1 |
| yenileme_tutari | numeric(12,2) NOT NULL | = paketin ucret'i |
| riskteki_para | numeric(12,2) | GENERATED: ROUND((1 − p_yenileme) × yenileme_tutari, 2) STORED |
| hesaplanma_zamani | timestamptz | |
UNIQUE (isletme_id, paket_id, hesaplama_tarihi, model_versiyonu).

### Ortak gereklilikler
- İki tabloda RLS ENABLE + FORCE ve `tenant_izolasyonu` politikası (faz1'deki kalıp).
- `panosu_app`'e SELECT, INSERT, UPDATE (DELETE yok).
- `musteri_paketleri`'ne `guncelleme_zamani` trigger'ı ve denetim trigger'ı (`denetim_kaydi_yaz('paket_id')`).
- View `v_yenileme_paneli` (security_invoker = true): her aktif paketin en güncel riski; müşteri adı,
  telefon, WhatsApp izni var mı, son ziyaret zamanı, paket adı, bitiş tarihi, kalan gün/giriş, p_yenileme,
  riskteki_para. `panosu_app`'e SELECT.
- `models.py`'ye `MusteriPaketi` ve `YenilemeRiski` (yalnızca sütunlar; riskteki_para Computed).

### Uygulama sırası ve doğrulama
1. `panosu_test`'i sıfırdan kur (`alembic upgrade head`, 0001 + 0002), tam pytest.
2. `panosu_demo`: `alembic upgrade head` (onaylı).
3. Canlı `panosu`: yalnızca her şey yeşilse `alembic upgrade head` (onaylı; canlı veritabanı boş).
Her veritabanında raporla: politika, view, trigger, RLS açık tablo sayıları (0001 sonrası 15/7/12/14;
0002 sonrası beklenen 17/8/14/16; farklıysa nedenini açıkla) ve version_num = 0002.

## Bölüm 2: Paket API'si
Dosyalar: `semalar/paket.py`, `servisler/paket_servisi.py`, `rotalar/paketler.py`, `tests/test_paket_api.py`.
- `POST /musteriler/{musteri_id}/paketler` (sahip/yonetici) → 201. Tür kuralları şemadakiyle aynı; ihlal → 422.
  Müşterinin aktif paketi varsa ve yenisi onun bitişinden önce başlıyorsa 409 (çakışan paket).
  onceki_paket_id verilmezse, müşterinin en son paketi otomatik bağlanır.
- `GET /musteriler/{musteri_id}/paketler` (tüm roller) → baslangic_tarihi azalan.
- `PATCH /paketler/{paket_id}` (sahip/yonetici) → yalnızca durum ve bitis_tarihi (dondurma uzatması için).
- `GET /paketler/{paket_id}` → kalan_giris hesaplanmış olarak (giriş bazlıda: giris_hakki − paket dönemindeki
  tamamlanmış ziyaret sayısı).
- Başka kiracının müşterisi/paketi → 404.

## Bölüm 3: Yenileme modeli (analitik/yenileme.py)
### Tanım
Üye, paketi bittiği anda hâlâ "hayatta" (MBG/NBD anlamında aktif) ise yeniler kabul edilir:
P(yenileme) = P(paket bittiğinde hayatta). Bu, gerçek yenileme verisiyle kalibre edilmemiş davranışsal bir
ilk sürümdür (model_versiyonu 'mbgnbd-sim-v1'; 2026-10'dan itibaren 'mbgnbd-map-v2').

### Hesaplama (sonsal simülasyon)
İşletmenin tüm üyelerinin ziyaret geçmişiyle M3 (MBG/NBD) parametreleri (r, α, a, b) tahmin edilir.
Her aktif paket için, üyenin (x, t_x, T) verisiyle:
1. Şu an hayatta mı? Bernoulli(P(hayatta | x, t_x, T)) (M3 formülü).
2. Hayattaysa: λ ~ Gamma(r + x, α + T) (oran parametresiyle), p ~ Beta(a, b + x + 1).
   (Hayatta olma koşulunda sonsallar; türetmeyi rapora yaz, uyuşmazlık görürsen dur.)
3. Bugünden itibaren ileri simülasyon: ziyaretler Poisson(λ) süreci; her ziyaretten sonra p olasılıkla bırakma.
   - Süre bazlı: bitis_tarihi'ne kadar simüle et; o anda hayatta mı?
   - Giriş bazlı: kalan haklar bitene kadar (varsa son kullanma tarihine kadar) simüle et; haklar bittiği
     anda hayatta mı? Son kullanma tarihine kadar haklar bitmezse, o tarihte hayatta mı?
4. N = 2 000 simülasyon; P(yenileme) = hayatta biten simülasyonların oranı.
Tekrarlanabilirlik: tohum, (paket_id, hesaplama_tarihi)'nden türetilir. Vektörize NumPy; 500 üyelik bir
işletme için hesaplama 10 saniyeyi geçmemeli.

### Bilinen sınırlamalar (rapora ve docs'a yazılacak)
- Backtest'te M3, S5'te gelecekteki ziyaretleri ~%11 fazla tahmin etti; bu simülasyon aynı eğilimi taşıyabilir.
- Fiyat, kampanya, taşınma gibi davranış dışı yenileme nedenleri modelde yok.
- İleride: `onceki_paket_id` zincirlerinden gerçek yenileme etiketleri çıkarılıp model kalibre edilecek (5c).

## Bölüm 4: Backtest S6 "Stüdyo"
`backtest/senaryolar.py`'ye S6 eklenir (sentetik, veritabanı yok):
- 1 500 üye, 2 yıl. Paket karışımı (HİPOTEZ): 1 ay %45, 3 ay %25, 6 ay %15, 12 giriş %15.
  Fiyatlar: 2.500 / 6.000 / 10.000 / 800 TL.
- Katılım: S1 kalıbı (düzenli aralıklar, ortalama 4 gün), bırakma MBG/NBD tarzı (ilk ziyaret dahil),
  bırakan üye paket bitene kadar ödemiş ama gelmeyen üyedir.
- Gerçek yenileme: paket bittiğinde hayatta olan üye %90 olasılıkla yeniler (aynı paket türü); hayatta
  olmayan yenilemez. (%10: fiyat/taşınma gibi davranış dışı nedenler.)
- Değerlendirme: kalibrasyon tarihinde aktif olan ve 60 gün içinde biten paketler.
  - p_yenileme için gerçek yenilemeye karşı ROC AUC ve Brier.
  - Karşılaştırma tabanı (kural): "son 21 günde en fazla 1 giriş → yenilemez".
  - Toplam Riskteki Para ile gerçekleşen kayıp ciro (yenilenmeyen paketlerin fiyat toplamı) karşılaştırması (hata %).
  - Paket türü kırılımı.
- 20 tohum; sonuçlar `docs/backtest-sonuclari.md`'ye yeni bölüm olarak.

## Bölüm 5: Servis, demo ve panel ucu
- `servisler/yenileme_servisi.py`: bir işletme için (kiracı bağlamlı oturumla) ziyaretleri ve aktif paketleri
  okur, modeli çalıştırır, `yenileme_riskleri`'ne yazar (aynı gün + model için yeniden çalıştırma idempotent:
  ON CONFLICT ile günceller).
- Komut: `python -m servisler.yenileme_calistir --veritabani <ad> --isletme <uuid>`. Yükleyicideki kilit
  kalıbıyla yalnızca `_demo` veya `_test` ile biten veritabanlarına yazar (canlı için ileride ayrı onay).
- `sentetik/`: [DEMO] Denge Pilates Stüdyosu için S6 kalıbında paket verisi üretip `panosu_demo`'ya yükle
  (yükleyici kilidi geçerli; mevcut demo verisini silmeden yalnızca paketleri ekle).
- `GET /panel/yenilemeler?gun=45` (tüm roller): `v_yenileme_paneli`'nden, bitişi önümüzdeki `gun` gün içinde olan
  paketler, riskteki_para azalan; yanıtın başında toplam riskteki para ve paket sayısı.

## Testler
- Şema: tür kısıtları (sure'de bitis zorunlu, giris'te hak zorunlu), riskteki_para hesaplanan sütunu,
  başka kiracının paketine erişim yok (DB düzeyinde ve API'de).
- Paket API: oluşturma, çakışma 409, otomatik onceki_paket bağlantısı, calisan POST → 403, kalan_giris.
- Yenileme modeli: P(hayatta)=0 iken P(yenileme)=0; aynı üyede kalan gün arttıkça P(yenileme) azalır
  (veya eşit kalır); çok sık gelen ve düşük p'li üyede P(yenileme) yüksek; aynı tohumla aynı sonuç.
- Riskteki Para: P(yenileme)=1 → 0; P(yenileme)=0 → ucret.
- Servis: panosu_test'te küçük bir işletme için çalışır, satırları yazar, ikinci çalıştırma satır sayısını
  değiştirmez.
- Kilit: servis komutu `panosu` ve adı _demo/_test ile bitmeyen veritabanlarını bağlanmadan reddeder.
- Bekçi testleri değişmeden yeşil kalır.

## Kabul kriterleri ve rapor
- Tam `pytest -q` yeşil; `python -c "import main"` hatasız; `python -m backtest` S0–S6 hatasız.
- Rapor (`raporlar/rapor-5b.md`; sohbette yalnızca özet):
  1. Üç veritabanında migration sonrası sayılar ve version_num.
  2. S6 sonuç tablosu: model ve kural tabanı için AUC, Brier, Riskteki Para hata %, paket türü kırılımı.
  3. `panosu_demo`'daki [DEMO] Denge Pilates için `GET /panel/yenilemeler?gun=45` çıktısının özeti:
     toplam riskteki para, paket sayısı, en yüksek riskli 5 üye (sentetik adlar).
  4. Sonsal dağılımların türetmesi (Bölüm 3, adım 2).
  5. Talimattan her sapma.
- CLAUDE.md yol haritasına 5b "Tamam", yeni bir 5c satırı: "Yenileme modelinin gerçek yenileme verisiyle
  kalibrasyonu (Faz 0 verisi gelince)".
- Commit ve push onaylı (raporlar/, veri/ hariç).

## Uygulama notları (2026-10-01)
Proje sahibi kararları (uygulama sırasında sorulan belirsizlikler):
- Giriş bazlı pakette son hakkı kullanan ziyaretin ardındaki bırakma çekilişi de sayılır: üye, haklar bittiği anda
  o çekilişten sağ çıktıysa "hayatta"dır (süre bazlıyla tutarlı).
- S6'da 12 giriş paketi satın alımdan 60 gün sonra (hak kalsa da) biter.

Uygulama ayrıntıları:
- Simülasyon vektörizedir: pencere içindeki ziyaret sayısı K, ters CDF ile ortak bir tekdüze sayıdan çekilir ve K ziyaretin
  hepsinden sağ çıkma tek bir U ~ Uniform(0,1) ile "U < (1−p)^K" olarak sınanır (K ayrı Bernoulli ile dağılım olarak aynı).
  Aynı tohumla pencere uzadıkça K azalmaz; "kalan gün arttıkça P(yenileme) artmaz" özelliği tohum gürültüsü olmadan sağlanır.
- Hiç ziyareti olmayan paket sahibinde x = 0, t_x = 0, T = paket başlangıcından bu yana geçen gün kullanılır.
- `kalan_giris` = giris_hakki − paket dönemindeki (başlangıç..bitiş; bitiş yoksa açık uçlu, işletmenin yerel günüyle)
  tamamlanmış ziyaret; 0'ın altına inmez.
- `GET /panel/yenilemeler`: bitiş tarihi olmayan (son kullanmasız giriş) paketler tarih penceresine giremez, listede yoktur.

## Bilinen sınırlamalar
- Backtest'te M3, S5'te gelecekteki ziyaretleri ~%11 fazla tahmin etti; bu simülasyon aynı eğilimi taşıyabilir.
- Fiyat, kampanya, taşınma gibi davranış dışı yenileme nedenleri modelde yok.
- Model gerçek yenileme verisiyle kalibre edilmedi. İleride `onceki_paket_id` zincirlerinden gerçek yenileme etiketleri
  çıkarılıp model kalibre edilecek (5c).
