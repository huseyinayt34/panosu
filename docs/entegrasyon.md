# Ritmeva entegrasyonu: stüdyo yazılım firmaları için teknik rehber

Bu sayfa, bir stüdyo/salon yazılımı geliştiren firmanın teknik sorumlusu için yazıldı. Sorusu şu:
"Ritmeva'yı kendi sistemimize nasıl bağlarız?" Kısa cevap: sisteminizden iki dosya (paketler ve girişler) dışa
aktarırsınız, Ritmeva bu dosyaları sizin sunucunuzda okur, üye başına bir risk listesi üretir. Üyelerin adı, telefonu
ve e-postası hiçbir aşamada gerekmez ve bize gelmez.

Bu belgede **şu an çalışan** ile **planlanan** açıkça ayrılmıştır. "Planlanan" diye işaretlenen bir parça bugün
yoktur; söz değil, yol haritasıdır.

| Parça | Durum |
|---|---|
| Dosya okuma kuralları (CSV/XLSX, sütun eşleştirme, tarih/para ayrıştırma) | Çalışıyor |
| Pilot doğrulama komutu (`servisler.pilot_dogrula`): doğruluk raporu + bugünkü risk listesi, veritabanı yok | Çalışıyor |
| Skor komutu: yalnızca "dosya girer, risk listesi çıkar", düzenli çalıştırmaya uygun | **Planlanan** |
| Firmanın sunucusuna kurulan Docker lisans paketi | **Planlanan** |

## 1. Akış

```
Sizin sisteminiz ──(gece dışa aktarma)──> paketler.csv + girisler.csv
                                               │
                                     Ritmeva (sizin sunucunuzda)
                                               │
                                               ▼
                                skorlar.csv  (Üye No + risk + neden)
                                               │
Sizin sisteminiz <──(Üye No ile eşleştirme)────┘   ekranınızda "bu üyeleri arayın" listesi
```

Ritmeva sizin üye kodunuzu (Üye No) olduğu gibi geri verir. İsmi, telefonu sizin tarafınızda Üye No ile
eşleştirirsiniz. Bizim tarafımızda kişisel veri tutulmaz.

## 2. Dışa aktaracağınız veri

İki dosya yeterlidir. Üye dosyası (ad, telefon, e-posta) **gerekmez**.

- Biçim: CSV veya XLSX (ilk sayfa). CSV kodlaması UTF-8 ya da Türkçe Excel (cp1254); ayırıcı `;`, `,` veya sekme,
  otomatik bulunur. `.xls` kabul edilmez.
- Sınır: dosya başına en fazla 5 MB ve 50.000 veri satırı. Giriş dosyası büyükse yıllara bölüp birden çok dosya
  verebilirsiniz; aynı giriş iki dosyada geçerse bir kez sayılır.
- Sütun adları serbesttir: Türkçe ve İngilizce yaygın adlar otomatik eşleşir ("Üye No", "Member ID", "Başlangıç
  Tarihi", "Start Date" gibi). Eşleşmeyen olursa bir JSON eşleştirme dosyasıyla düzeltilir (bkz. Bölüm 6).

### 2.1 Paket dosyası (her satır bir satılan paket/üyelik)

| Alan | Zorunlu | Tür ve kural | Örnek sütun adları |
|---|---|---|---|
| Üye kodu | Evet | Sizin sisteminizdeki üye kimliği (metin) | Üye No, Müşteri No, Member ID |
| Paket kodu | Hayır | Paketin kimliği; yoksa üye + başlangıç + paket adından türetilir | Paket No, Satış No |
| Paket adı | Evet | Metin | Paket Adı, Üyelik Tipi, Plan |
| Başlangıç | Evet | Tarih | Başlangıç Tarihi, Satış Tarihi |
| Bitiş | Süreli pakette evet | Tarih | Bitiş Tarihi, Son Geçerlilik |
| Giriş hakkı | Hayır | Tam sayı; varsa paket "giriş bazlı", yoksa "süreli" sayılır. "Kalan Seans" gibi kalan hak sütunları kullanılmaz | Seans Sayısı, Ders Hakkı, Kredi |
| Ücret | Evet | Para; negatif olamaz | Ücret, Tutar, Paket Fiyatı |
| Durum | Hayır | aktif / bitti / iptal / donduruldu (İngilizce karşılıkları da olur); yoksa bitiş tarihinden çıkarılır | Durum, Üyelik Durumu |

Aynı üyenin paketleri başlangıç tarihine göre sıralanıp bir "yenileme zinciri" kurulur. Model, bir paketin
yenilenip yenilenmediğini bu zincirden öğrenir. Bu yüzden **eski (bitmiş) paketleri de** gönderin, yalnızca
aktifleri değil.

### 2.2 Giriş dosyası (her satır bir ders/giriş)

| Alan | Zorunlu | Tür ve kural | Örnek sütun adları |
|---|---|---|---|
| Üye kodu | Evet | Paket dosyasındaki üye kodunun aynısı | Üye No |
| Tarih | Evet | Tarih, isteğe bağlı saatle | Giriş Tarihi, Ders Tarihi, Check-in |
| Saat | Hayır | Ayrı sütunsa | Giriş Saati |
| Durum | Hayır | geldi / iptal / gelmedi; boşsa "geldi" | Durum |

Aynı üyenin aynı dakikadaki iki girişi çift okutma sayılır ve tek kayda indirilir. Gelecek tarihli giriş (5
dakikadan ileri) satır hatasıdır.

### 2.3 Biçim kuralları

- Tarih: `gg.aa.yyyy`, `gg/aa/yyyy`, `gg-aa-yyyy` veya `yyyy-aa-gg`, isteğe bağlı `SS:DD[:ss]`. Excel tarih hücresi
  doğrudan okunur. Ay/gün sırası (`aa/gg`) desteklenmez; ay 12'den büyük çıkarsa satır hatası verir. Saatsiz giriş
  yerel 12:00 sayılır. Saat dilimi varsayılan `Europe/Istanbul`.
- Para: `1.250,00`, `1250.00`, `1.250 TL`, `₺1250` gibi yazımlar okunur. İkiden fazla ondalık ya da negatif tutar
  satır hatasıdır. Hesaplar kayan nokta (float) değil, tam ondalık (Decimal) ile yapılır.
- Hatalı satırlar atlanır ve satır numarası + alan + sebep ile listelenir (ilk 20). Bir dosyada hatalı satır oranı
  %10'u geçerse çalıştırma durur ve hiçbir çıktı yazılmaz; çoğu zaman sebep yanlış sütun eşleşmesidir.

### 2.4 Örnek (uydurma veri)

`paketler.csv`:
```
Üye No;Paket No;Paket Adı;Başlangıç Tarihi;Bitiş Tarihi;Seans Sayısı;Ücret;Durum
U1001;P5001;Aylık Sınırsız;01.06.2026;30.06.2026;;2.400,00;Bitti
U1001;P5102;Aylık Sınırsız;01.07.2026;31.07.2026;;2.400,00;Bitti
U1001;P5230;Aylık Sınırsız;01.08.2026;31.08.2026;;2.400,00;Aktif
U1002;P5011;8 Ders Reformer;15.06.2026;15.08.2026;8;3.200,00;Bitti
U1003;P5240;12 Ders Mat;20.07.2026;20.10.2026;12;3.600,00;Aktif
```

`girisler.csv`:
```
Üye No;Giriş Tarihi
U1001;02.08.2026 18:30
U1001;05.08.2026 18:35
U1003;22.07.2026 09:00
U1003;12.08.2026 09:05
```

Dosyada isim, telefon ya da e-posta sütunu yoktur. Olsa bile okunmaz (Bölüm 3).

## 3. Kişisel veri ve KVKK

- **Ritmeva sizin sunucunuzda çalışacak şekilde tasarlandı.** Dosyalar sizin makinenizde okunur, sonuç sizin
  makinenize yazılır; bugün bu, pilot komutunu kendi makinenizde çalıştırdığınızda geçerlidir (sunucu paketi
  planlanan, Bölüm 9). Bu yolda üye verisi bize gönderilmez. Veri sorumlusu (KVKK) sizsiniz ve öyle kalırsınız.
- **Dosyaları bize gönderirseniz** (pilotta ikinci yol, Bölüm 7): isimsiz ve kodları değiştirilmiş veri de, siz
  kodları geri eşleyebildiğiniz sürece KVKK'da kişisel veri sayılabilir (takma ad, anonim değildir). Bu durumda biz
  veri işleyen oluruz; bu yol ancak yazılı bir veri işleme sözleşmesiyle ve sizin hukuki değerlendirmenizle
  kullanılmalıdır. Bu yüzden önerimiz birinci yoldur.
- **Beyaz liste:** yalnızca yukarıdaki alanlar okunur. Dosyadaki diğer sütunlar ayrıştırıcıdan çıkmaz, hiçbir
  yere yazılmaz, hiçbir çıktıda görünmez. Girdi dosyaları kopyalanmaz.
- **Hassas sütunlar:** başlığında "TC", "T.C.", "kimlik no", "kan", "biyometri", "parmak", "sağlık", "hastalık",
  "ilaç" geçen sütun hiçbir zaman eşleşmez; eşleştirme dosyasıyla zorla verilse bile reddedilir. Bu sütunların
  hücreleri okuma anında atılır.
- **Ad, telefon, e-posta:** pilot ve skor akışında hiç okunmaz. Hata mesajları da yalnızca satır numarası, alan ve
  sebep yazar, değer yazmaz.
- **Ek gizleme (isteğe bağlı; anonimleştirme yerine geçmez):** model yalnızca zaman farklarını kullanır ve "bugün"ü verideki son girişten
  alır. Bu yüzden iki dosyadaki tüm tarihleri aynı gün sayısı kadar geri kaydırmak sonucu değiştirmez (testle
  doğrulanmıştır). Üye kodlarını da sizin bildiğiniz bir eşlemeyle başka kodlara çevirebilirsiniz.

## 4. Geri dönen sonuç ve nasıl okunur

Çıktı `skorlar.csv` dosyasıdır (`;` ayırıcılı, Türkçe Excel'de doğrudan açılır). Her satır bugün aktif olan bir
paket; dondurulmuş paketler sayılır ama skorlanmaz. Satırlar Riskteki Para'ya göre büyükten küçüğe sıralıdır.

| Sütun | Anlamı |
|---|---|
| Üye No, Paket No, Paket Adı, Bitiş Tarihi | Sizin verinizden, olduğu gibi |
| Kalan Gün / Kalan Giriş | Paketin bitmesine kalan gün ya da kalan giriş hakkı |
| Aktif Olasılığı | Üyenin bugün hâlâ "gelmeye devam eden" üye olma olasılığı (0-1) |
| Yenileme Olasılığı | P(yenileme): üyenin paketi bittiğinde yenileme olasılığı (0-1, 4 ondalık) |
| Riskteki Para | (1 − P(yenileme)) × paket ücreti, kuruşa yuvarlanmış. Bu üyede kaybetme riski olan beklenen tutar |
| Neden | Tek cümlelik, sayıya dayalı açıklama |

"Neden" cümlesinin biçimleri:
- "Normalde ~7 günde bir geliyor; 24 gündür gelmiyor (normalin 3,4 katı)."
- "Paketi 01.08.2026 tarihinde aldı, o günden beri hiç gelmedi (34 gün)."
- "Yalnızca 2 kez geldi; son ziyaret 15 gün önce. Geçmiş az, tahmin belirsiz."
- "Şu an düzenli geliyor; risk, kalan 5 giriş hakkını kullanırken bırakma ihtimalinden."
- "Düzenli geliyor; belirgin bir risk yok." (P(yenileme) ≥ 0,80)

Nasıl kullanılır: listenin en üstü, stüdyonun önce araması gereken üyelerdir. Toplam Riskteki Para, "bu ay
yenilenmeme yüzünden kaybedilebilecek beklenen ciro" olarak ekranda gösterilebilir.

Bilinmesi gerekenler:
- Model yalnızca davranışa (geliş sıklığı, son geliş, paket süresi/hakkı) bakar. Fiyat değişikliği, taşınma,
  eğitmen değişikliği gibi bilgileri görmez.
- Yenileme olasılığı henüz gerçek yenileme verisiyle kalibre edilmedi; sentetik senaryolarda doğrulandı. Bu yüzden
  olasılıklar ilk aşamada **sıralama** olarak okunmalıdır. Kalibrasyon ilk pilotların verisiyle yapılacak.
- Az geçmişli üyelerde (birkaç giriş) tahmin belirsizdir; "Neden" cümlesi bunu açıkça yazar.

Modelin matematiği (MBG/NBD, MAP kestirimi, kesin yenileme formülü) ve sınırları: `docs/matematik-raporu.md`.

## 5. Yenileme sıklığı

Model her çalıştırmada o stüdyonun **kendi verisinden** yeniden kurulur (stüdyolar arası veri paylaşılmaz). Ayrı bir
"eğitim" adımı ya da sizin saklamanız gereken bir model dosyası yoktur.

Önerimiz: **günde bir kez**, gece, yeni dışa aktarmadan sonra çalıştırmak. Risk günler içinde değiştiği için (bir
üyenin sessizliği her gün uzar) haftalık çalıştırma geç kalabilir; gün içinde birden çok çalıştırma ise sonucu
anlamlı biçimde değiştirmez. Zamanlama (cron, Windows Görev Zamanlayıcı) sizin tarafınızdadır.

Bugün bu düzenli çalıştırma için pilot komutu kullanılabilir, ama o komut her seferinde doğrulama raporunu da
üretir. Yalnızca listeyi üreten hafif **skor komutu planlanandır**.

## 6. Model sürümü

Model sürümü bir sürüm adıyla izlenir; şu anki sürüm **`mbgnbd-map-v3`**.

- Sürüm adı, hesabın kendisi değiştiğinde değişir. Örnek: `v2`'den `v3`'e geçişte model aynı kaldı, yalnızca
  yenileme olasılığı yaklaşık (Monte Carlo) hesap yerine kesin formülle hesaplanmaya başladı; sonuçlar aynı,
  rastgelelik gürültüsü sıfır.
- Aynı veri ve aynı sürümle çalıştırma her seferinde bit bit aynı sonucu verir (girdi sırası önemsizdir).
- Sürüm değişiklikleri depodaki tasarım belgelerinde gerekçesiyle kayıtlıdır.

Planlanan: skor komutu ve Docker paketi, sürüm adını her çıktıya yazacak ve bir sürüm değişikliği önceden
duyurulacak. Bugünkü pilot çıktısında (`skorlar.csv`) sürüm sütunu yoktur.

## 7. Önce pilot

Entegrasyondan önce modelin **sizin verinizde** ne kadar isabetli olduğunu ölçeriz. Bu adım bugün çalışıyor.

1. Bir stüdyonun paket ve giriş dosyalarını Bölüm 2'deki gibi dışa aktarırsınız (en az 1 yıl geçmiş önerilir).
2. Pilot komutu çalıştırılır. İki yol var:
   - Komutu kendi makinenizde çalıştırırsınız ve bize yalnızca raporu gönderirsiniz (veri hiç çıkmaz). Komut
     veritabanı, `.env` ya da PostgreSQL gerektirmez; Python ve bu depo yeterlidir.
   - Ya da yalnızca bu iki dosyayı (isimsiz; isterseniz tarihleri kaydırılmış ve kodları değiştirilmiş) bize
     gönderirsiniz. Bu yol, önce yazılı bir veri işleme sözleşmesi gerektirir (Bölüm 3).

   ```powershell
   python -m servisler.pilot_dogrula --kaynak stuvio --ad "Örnek Stüdyo" --paketler paketler.csv --girisler girisler_2025.csv girisler_2026.csv
   ```
   Eşleştirme beklenen gibi değilse, oluşan `esleme.json` dosyası düzeltilip `--esleme esleme.json` ile tekrar
   verilir.
3. Komut geçmişe dönük bir sınav yapar: verideki son günden 90 gün geriye (ve geçmiş yeterliyse 90'ar gün daha,
   en çok 4 kez) gider, o güne kadarki veriyle tahmin yapar, sonra gerçekte kimin yenilediğine bakar.
4. Çıktılar (`raporlar/pilot/<kaynak>/`):
   - `pilot-raporu.html`: yazdırılabilir Türkçe rapor. Ayırma başarısı (ROC AUC ve %95 güven aralığı), basit
     "son 21 günde en fazla 1 kez geldi" kuralıyla karşılaştırma, en riskli 10 paketten kaçının gerçekten
     yenilemediği, tahmini ve gerçekleşen kayıp. Sonuç kötü çıkarsa rapor bunu da aynı açıklıkla yazar.
   - `dogrulama.csv`: değerlendirilen her paket, tahmini ve gerçek sonucuyla. Raporu kendi kayıtlarınızla
     karşılaştırabilmeniz için.
   - `skorlar.csv`: bugünkü risk listesi (Bölüm 4).
   - `esleme.json`: kullanılan sütun eşleştirmesi.

Sentetik verideki sonuçlar örnek olsun diye (gerçek veri değil): 400 üyeli bir demo stüdyoda AUC 0,74 (aralık
0,66-0,81), basit kural 0,67; en riskli 10 paketin 10'u yenilemedi. Değerlendirilen paket 30'un altındaysa ya da
geçmiş 1 yıldan kısaysa rapor uyarı verir.

## 8. Lisans

Kaynak kodu okunabilir ve değerlendirme için kendi bilgisayarınızda çalıştırılabilir. Ticari kullanım (kendi
ürününüzde, müşterileriniz için) yazılı izne bağlıdır; pilot da yazılı bir anlaşmayla yapılır. Ayrıntı:
[LICENSE](../LICENSE). İletişim: ritmeva.iletisim@gmail.com

## 9. Planlananlar (henüz yok)

- **Skor komutu:** paket ve giriş dosyası girer, yalnızca `skorlar.csv` çıkar; doğrulama raporu üretmez, gece
  çalıştırmaya uygun, çıktıda model sürümü.
- **Docker lisans paketi:** skor komutunu sizin sunucunuzda tek imajla çalıştırmak için; Python kurulumu gerekmez.
- **Gerçek veriyle kalibrasyon:** ilk pilotların yenileme verisiyle yenileme olasılığının ayarlanması.

Bu üçü hazır olduğunda bu belge güncellenecektir.
