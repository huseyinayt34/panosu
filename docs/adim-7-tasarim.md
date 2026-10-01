# Adım 7: Panel (sessiz üyeler, gelir ve kâr özeti, haftalık rapor)

Genel kurallar için `CLAUDE.md`'ye bak. Bu belgedeki ürün ve matematik kararları proje sahibi tarafından
onaylıdır; ajan bunları değiştirmez, sorun görürse durup raporlar.

## Amaç
Stüdyo sahibine üç soruyu tek bakışta cevaplamak:
1. Paketi aktif olduğu hâlde gelmeyi bırakan kim? (sessiz üyeler)
2. Bu ay gerçekten kâr ettim mi, ve kaç üyenin altına düşersem zarara geçerim? (gelir ve kâr)
3. Bunların hepsini bir sayfada görebilir, yazdırabilir miyim? (haftalık rapor; Faz 0 görüşmelerinde de
   demo olarak kullanılacak)

## Bölüm 1: Migration 0003
Dosyalar: `alembic/sql/0003_panel.sql`, `alembic/versions/0003_panel.py` (önceki migration'larla aynı kalıp;
downgrade bu migration'ın nesnelerini siler).

### `isletme_giderleri`
| Sütun | Tip | Kural |
|---|---|---|
| gider_id | uuid PK | |
| isletme_id | uuid NOT NULL | DEFAULT aktif_isletme(), FK isletmeler |
| ay | date NOT NULL | ayın ilk günü (CHECK: EXTRACT(day FROM ay) = 1) |
| kategori | text NOT NULL | 'kira','personel','faturalar','diger' |
| tutar | numeric(12,2) NOT NULL | ≥ 0 |
| aciklama | text | |
| olusturma_zamani, guncelleme_zamani | timestamptz | |
UNIQUE (isletme_id, ay, kategori). RLS ENABLE + FORCE + tenant_izolasyonu; panosu_app'e SELECT, INSERT, UPDATE;
guncelleme_zamani trigger'ı ve denetim trigger'ı.

### `v_sessiz_uyeler` (security_invoker = true)
Aktif paketi olan (durum 'aktif'; süre bazlıda bitis_tarihi ≥ bugün, giriş bazlıda kalan hak > 0) ve en güncel
`yenileme_riskleri` kaydında `p_hayatta_simdi` değeri olan üyeler. Sütunlar: musteri_id, ad_soyad, telefon,
WhatsApp izni var mı, paket_id, paket adı, tür, bitis_tarihi, kalan_gun / kalan_giris, son_ziyaret,
son ziyaretten bu yana geçen gün, p_hayatta_simdi, p_yenileme, paket ücreti, riskteki_para.
Eşik filtresi view'da değil, uçta uygulanır. panosu_app'e SELECT.

Uygulama sırası (5b ile aynı): panosu_test sıfırdan → tam pytest → panosu_demo → en son, her şey yeşilse canlı
panosu (onaylı). Her veritabanında politika/view/trigger/RLS sayılarını ve version_num'u raporla
(beklenen 18/9/16/17; farklıysa nedenini açıkla).

## Bölüm 2: Sessiz üyeler
- `GET /panel/sessiz-uyeler?esik=0.5` (tüm roller): `p_hayatta_simdi < esik` olanlar, riskteki_para azalan,
  eşitlikte son ziyaretten bu yana geçen gün azalan. esik 0–1 arası (dışı → 422). Yanıtın başında üye sayısı ve
  toplam riskteki para.
- Bir üye hem yenileme listesinde hem sessiz listede görünebilir; bu beklenen davranıştır (farklı sorular).

## Bölüm 3: Gelir ve kâr özeti
### Gelir tanımları
İki görünüm her zaman birlikte gösterilir:
- **Kasaya giren (nakit):** paketin ücreti `baslangic_tarihi` gününde tamamen girer (varsayım: ödeme başlangıçta
  yapılır; gerçek tahsilat verisi ileride gelirse değiştirilecek, bunu docs'a yaz).
  Ziyaretlerin `toplam_tutar`'ı ziyaret gününde girer.
- **Gerçek gelir (hak edilen):**
  - Süre bazlı paket: ücret [baslangic_tarihi, bitis_tarihi) aralığındaki günlere eşit dağıtılır.
    Decimal ile; kuruş yuvarlama farkı son güne eklenir, böylece paket ömrü boyunca toplam = ücret, tam olarak.
  - Giriş bazlı paket: her kullanılan giriş için ücret / giris_hakki, o ziyaretin gününde hak edilir
    (aynı yuvarlama kuralı: son girişe fark eklenir). Son kullanma tarihi geçtiyse kullanılmayan hakların
    karşılığı o tarihte hak edilir (kullanılmayan hak geliri). Son kullanmasız pakette kullanılmayan haklar
    hak edilmemiş kalır.
  - Ziyaretlerin `toplam_tutar`'ı ziyaret gününde hak edilir (paketten bağımsız ek satış: tek ders, ürün vb.).
  - Durumu 'iptal' olan paketlerde iptal tarihinden sonrası hak edilmez (iptal tarihi = guncelleme_zamani'nın
    günü; varsayım, docs'a yaz). İade modellenmez.
- **Çift sayım kuralı:** Paketli işletmede giriş ziyaretlerinin `toplam_tutar`'ı 0 olmalıdır. `panosu_demo`'daki
  [DEMO] Denge Pilates verisinde, paket dönemi içine düşen ziyaretlerin tutarı sıfır değilse, sentetik üreticiyi
  bu ziyaretlerin tutarını 0 yapacak şekilde güncelle (yalnızca panosu_demo; kaç satırın değiştiğini raporla).

### Giderler
- `PUT /giderler/{ay}` (sahip/yonetici; ay = YYYY-MM): gövde {kira, personel, faturalar, diger}, her biri
  Decimal ≥ 0 veya null (null = o kategori silinmez, değişmez). Kayıt yoksa oluşturur, varsa günceller.
- `GET /giderler/{ay}` (sahip/yonetici).
- calisan → 403.

### Özet ucu
`GET /panel/finans?ay=YYYY-MM` (sahip/yonetici; calisan → 403; finansal bilgi). Yanıt:
- kasaya_giren, gercek_gelir, gider_toplam, kar_zarar (= gercek_gelir − gider_toplam). Gider girilmemişse
  gider_toplam ve kar_zarar null, ve `gider_girilmedi: true`.
- gunluk: ayın her günü için {tarih, kasaya_giren, gercek_gelir, gider_payi, net}. gider_payi = aylık gider /
  ayın gün sayısı (aynı yuvarlama kuralı). Gelecekteki günler dahil edilmez.
- aktif_uye_sayisi: bugün aktif paketi olan farklı üye sayısı.
- uye_basi_aylik_gelir = gercek_gelir / ay içindeki ortalama günlük aktif üye sayısı (ay bitmediyse bugüne kadar).
- basabas_uye_sayisi = ⌈gider_toplam / uye_basi_aylik_gelir⌉ (gider veya gelir yoksa null).
- basabas_farki = aktif_uye_sayisi − basabas_uye_sayisi.
- riskteki_para_45_gun: `v_yenileme_paneli`'nden önümüzdeki 45 günün toplamı.
Tüm tutarlar Decimal, 2 ondalık.

## Bölüm 4: Haftalık rapor (tek sayfa)
- `GET /rapor/haftalik` (sahip/yonetici) → HTML (Jinja2 şablonu; fastapi[all] ile geliyor, yoksa raporla).
  A4'e yazdırılabilir CSS (tarayıcıda Ctrl+P → PDF). Grafik yok.
- İçerik: işletme adı ve tarih; üç gösterge kutusu: (1) bu ayın kâr/zararı (gider yoksa gerçek gelir ve
  "gider girilmedi" notu), (2) önümüzdeki 45 günde riskteki para, (3) aktif üye / başabaş üye sayısı;
  "Önümüzdeki 45 günde yenilemesi riskli 10 üye" tablosu; "En değerli 10 sessiz üye" tablosu; altta not:
  "Olasılıklar model tahminidir; gerçek yenileme verisiyle kalibre edilmemiştir."
- Para biçimi Türkçe: 1.234,56 TL. Tarih: 9 Ekim 2026. Biçimleme fonksiyonları ayrı modülde ve testli.
- Komut: `python -m servisler.rapor_uret --veritabani <ad> --isletme <uuid> --cikti raporlar/<dosya>.html`
  (kilit: yalnızca _demo/_test veritabanları). Çıktı raporlar/ altında (git'e girmez).
- Faz 0 için: `panosu_demo`'daki [DEMO] Denge Pilates için raporu üret. Ay için demo giderleri yoksa,
  sentetik üreticiye makul demo giderleri ekle (kira 45.000, personel 60.000, faturalar 8.000, diğer 5.000 TL;
  HİPOTEZ) ve raporla.

## Testler
- Hak edilen gelir: 6 aylık paket ömrü boyunca günlük payların toplamı = ücret (Decimal, tam eşitlik);
  ay sınırını geçen pakette iki ayın payları doğru; giriş bazlıda kullanım başına pay ve son kullanma tarihinde
  kalan hakların tanınması; iptal sonrası tanıma yok.
- Kasaya giren: ücret başlangıç gününde.
- Çift sayım: paketli demo işletmede paket dönemi içindeki ziyaret tutarları 0.
- Başabaş: tavan fonksiyonu; gider yokken null.
- Giderler: PUT oluşturur/günceller; null kategori değişmez; başka kiracının giderine erişim yok (DB ve API);
  calisan 403.
- Sessiz üyeler: eşik filtresi; sıralama; esik dışı değer 422.
- Rapor: HTML 200; işletme adı, üç gösterge ve iki tablo başlığı var; Türkçe para/tarih biçimi testleri.
- Bekçi ve izolasyon testleri değişmeden yeşil.

## CLAUDE.md güncellemeleri
- Yol haritası: 7 "Tamam".
- 5c satırına not: "Test edilecek hipotezler (proje sahibinin gözlemi): (1) aktif üyelerin yenileme oranı ρ
  %90'ın üzerinde; (2) önceki yenileme sayısı yenilemenin güçlü habercisi; (3) az gelip yine de yenileyen bir
  grup var ve model onlara yanlış alarm veriyor olabilir. S6'da Riskteki Para'nın %13 düşük çıkmasının nedeni
  ρ = 1 varsayımıdır."
- Araştırma rafına ekle: "Kafe/restoran modülü (menü fotoğrafından ürün çıkarma, menü mühendisliği,
  enflasyon/marj alarmı). Başlama koşulu: stüdyo ürünü en az bir gerçek stüdyoda çalışıyor ve bir kafe ürün
  bazında satış verisi verebiliyor." ve "Veteriner klinikleri: aşı/kontrol döngüsü (ileride değerlendirilecek)."

## Kabul kriterleri ve rapor
- Tam `pytest -q` yeşil; `python -c "import main"` hatasız.
- Rapor (`raporlar/rapor-7.md`; sohbette yalnızca özet):
  1. Üç veritabanında migration sonrası sayılar ve version_num.
  2. Demo için `GET /panel/finans` (bu ay) özeti: kasaya giren, gerçek gelir, gider, kâr/zarar, aktif üye,
     başabaş üye sayısı.
  3. Demo için sessiz üye sayısı (esik=0.5) ve toplam riskteki para; ilk 3 üye.
  4. Üretilen haftalık rapor dosyasının yolu.
  5. Çift sayım düzeltmesinde değişen satır sayısı.
  6. Talimattan her sapma.
- Commit ve push onaylı (raporlar/, veri/ hariç).

## Uygulama notları (2026-10-01)
Varsayımlar (gerçek veri gelince değiştirilecek):
- **Kasaya giren:** paket ücretinin tamamı `baslangic_tarihi` gününde tahsil edilmiş sayılır. Gerçek tahsilat
  (taksit, geç ödeme) verisi gelirse kasaya giren bu veriden hesaplanacak.
- **İptal tarihi:** durumu 'iptal' olan paketin iptal günü = `guncelleme_zamani`'nın işletme yerel günü. İptalden
  sonra pakete yapılan herhangi bir güncelleme bu tarihi kaydırır. İade modellenmez.

Proje sahibi kararları (uygulama sırasında sorulan belirsizlikler):
- **Ay bitmemişse:** kasaya giren ve gerçek gelir bugüne kadar; `kar_zarar` = gerçek gelir − bugüne kadarki gider
  payları (= günlük net toplamı; yanıtta `gider_bugune_kadar`); `gider_toplam` tüm ayın gideri;
  `uye_basi_aylik_gelir` = gerçek gelir × (ayın gün sayısı / geçen gün) / ortalama günlük aktif üye;
  başabaş tüm ayın gideriyle. Ay bitince tanımlar belgedekiyle aynıdır.
- **Kullanılmayan giriş hakkı geliri:** `bitis_tarihi` geçince (bitis_tarihi < bugün) o tarihe yazılır.

Uygulama ayrıntıları:
- Yuvarlama: her pay kuruşa aşağı yuvarlanır, fark son paya eklenir (pay negatif olmaz; toplam = ücret, tam).
- Gelir yalnızca tamamlanmış ziyaretlerden; giriş kullanımı `kalan_giris` ile aynı dönem tanımıyla
  ([başlangıç, son kullanma], yerel gün); haktan fazla giriş gelir üretmez.
- Aktif üye (bugün ve ortalama günlük): paketin o günü kapsaması (süre: [başlangıç, bitiş); giriş: başlangıçtan
  son kullanmaya kadar ve haklar o günden önce bitmemişse; iptal gününden sonra değil). Geçmiş günler için paketin
  bugünkü `durum` sütununa bakılmaz.
- `v_sessiz_uyeler`: giriş bazlıda kalan hak > 0 koşuluna ek olarak son kullanma tarihi geçmemiş olmalı.
- Demo çift sayım düzeltmesinde ziyaret tutarıyla birlikte kalemlerin indirimi tam tutara eşitlenir; kalem
  dökümü ziyaret toplamıyla tutarlı kalır.

## İyileştirmeler (2026-10-01, proje sahibi isteği)
- Kâr/zarar göstergesi iki satır: "Geçen ay (tamamlanmış)" (`onceki_ay_kar_zarar`) ve "Bu ay şimdiye kadar"
  (`kar_zarar`, `gecen_gun` gün).
- İçinde bulunulan ayın ilk 7 gününde üye başı aylık gelir ve başabaş üye sayısı geçen ayın tamamlanmış verisiyle
  hesaplanır; kaynak ay `basabas_kaynak_ay` alanında ve raporda "Başabaş <Ay Yıl> verisiyle hesaplandı." metniyle.
