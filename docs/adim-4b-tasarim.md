# Adım 4b: CSV/Excel içe aktarma

Genel kurallar için `CLAUDE.md`'ye bak. Bu adımda şema değişikliği (migration) YOK.

## Kararlar (proje sahibi onayı, 2026-10-02)

**K29** Üç dosya türü: uyeler, paketler, girisler (ziyaretler). Giderler içe aktarılmaz (web formu).
Yazma sırası: üyeler → paketler → girişler; üçü TEK veritabanı işleminde.

**K30** Biçimler: CSV ve XLSX (ilk sayfa). CSV kodlaması önce utf-8-sig, çözülemezse cp1254 (Türkçe Excel).
Ayırıcı ilk 5 satırdan csv.Sniffer ile; adaylar ; , \t. Boş satırlar atlanır. Başlık = ilk dolu satır.

**K31** Sütun eşleştirme: başlıklar normalleştirilir (Türkçe küçük harf: İ→i, I→ı; sonra ş→s ğ→g ı→i ö→o ü→u ç→c;
boşluk/noktalama tek boşluğa; kırpılır) ve aşağıdaki eş anlamlı sözlükle eşleşir. Kullanıcı eşleştirmeyi JSON
dosyasıyla (--esleme) düzeltebilir. Eşleştirmenin işletme başına veritabanında saklanması 4b-3'e (web) kalır.
Yapay zekâ önerisi yok.

**K32** İki aşama: varsayılan ÖNİZLEME (veritabanına hiçbir şey yazılmaz). --onayla ile tek işlemde yazılır; herhangi bir
yazma hatasında tamamı geri alınır.

**K33** Tekrar yükleme: dis_kaynak = "csv:<kaynak>" (--kaynak, ör. "stuvio"; yalnızca [a-z0-9_-], 1–40 karakter),
dis_kimlik = dosyadaki kimlik. kaynak sütunu = 'csv'. Üyeler ve paketler UPSERT (güncellenen alanlar aşağıda),
girişler yalnızca EKLENİR (var olan atlanır; Adım 4a: ziyaret tutarı/zamanı değişmez). Paket kimliği yoksa
dis_kimlik = "P" + sha256(uye_kimlik|baslangic|paket_adi)[:16]; giriş kimliği yoksa
dis_kimlik = "G" + sha256(uye_kimlik|yerel ISO zaman)[:16]. Aynı dosyada aynı türetilmiş kimlik → tek satır.

> **Giriş No sütunu yok (proje sahibi kararı, 2026-10-02).** Gerçek stüdyo dosyalarında giriş numarası genelde
> bulunmaz. Aynı üyenin aynı dakikadaki iki girişi gerçekte çift okutmadır; türetilmiş kimlikle tek kayda indirilmesi
> doğru davranıştır. Dışa aktarma (`sentetik/disa_aktar.py`) bu yüzden giriş dosyasına kimlik sütunu koymaz.
> Elle denemede Butik Reformer'daki 22 aynı anlı ziyaret çifti bu kuralla tek kayda indi (bkz. "4b-1 sonuçları").

**K34** Beyaz liste: yalnızca eşleştirilen alanlar okunur; diğer tüm sütunlar ayrıştırıcıdan çıkmaz, hiçbir yere
yazılmaz, hiçbir çıktıda görünmez. Yüklenen dosya kopyalanmaz/saklanmaz. Başlığında "tc", "kimlik no",
"kan", "biyometri", "parmak", "saglik", "hastalik", "ilac" geçen sütun HİÇBİR ZAMAN otomatik eşleşmez
(elle --esleme ile verilse de reddedilir: "hassas alan").
Hata ve uyarı mesajları ad_soyad, telefon ve eposta DEĞERLERİNİ asla yazmaz; yalnızca satır no + alan + sebep.

**K35** --anonim: ad_soyad = "Üye " + sha256(dis_kaynak|uye_kimlik)[:6] (kararlı), telefon ve eposta hiç okunmaz.

**K36** Giriş tutarı varsayılan 0. tutar alanı eşleştirilirse okunur; ama aynı çalıştırmada paket dosyası da varsa
uyarı: "Paket geliri ve giriş tutarı birlikte: ciro iki kez sayılabilir".

**K37** Tarih: gg.aa.yyyy, gg/aa/yyyy, gg-aa-yyyy, yyyy-aa-gg (+ isteğe bağlı SS:DD[:ss]); xlsx tarih hücresi doğrudan;
sayısal değer 20000–80000 arası ise Excel seri tarihi (1899-12-30 + n). Ay > 12 → satır hatası
("gün/ay sırası"; aa/gg biçimi desteklenmez). İki haneli yıl → 20yy. Saatsiz giriş → yerel 12:00.
Saat dilimi: isletmeler.saat_dilimi (zoneinfo). Şu andan 5 dakikadan ileri giriş → satır hatası.
Para: "TL", "₺", boşluk atılır; hem "." hem "," varsa sondaki ondalık ayırıcıdır; yalnız "," → ondalık;
yalnız "." ve desen ^\d{1,3}(\.\d{3})+$ → binlik (1.250 = 1250, uyarı sayacına eklenir); diğer "." → ondalık.
Sonuç Decimal, 2 ondalığa yuvarlanmaz; 2'den fazla ondalık → satır hatası. Negatif → satır hatası. float YOK.
Telefon: servisler/telefon.py telefon_normallestir; ValueError → telefon NULL + uyarı (satır hatası değil).

**K38** Geçersiz satırlar atlanır ve raporlanır (ilk 20). Bir dosyada hatalı satır oranı > %10 ise --onayla reddedilir
("eşleştirmeyi kontrol et"), hiçbir şey yazılmaz. Girişte üye kimliği ne bu çalıştırmadaki üyelerde ne de
veritabanında (aynı dis_kaynak) varsa satır hatası.

**K39** Sınırlar: dosya başına en fazla 5 MB ve 50.000 veri satırı (aşılırsa okumadan reddedilir). Yazma sonrası
yenileme riski yeniden hesaplanır (servisler.yenileme_servisi.yenileme_hesapla; YetersizVeri → uyarı).
Web ekranı (sahip/yönetici yetkisi, salt okunur demoda kapalı) 4b-3'te.

**K40** (4b-2'de yapılacak, bu adımda KOD YOK) Gerçek veride doğrulama: zaman bölmeli test, kesim = son tarih − H gün,
H varsayılan 90 (proje sahibinin son onayı bekleniyor). ROC AUC, 10'luk kalibrasyon, Riskteki Para vs gerçekleşen.

**K41** Gidiş-dönüş kabul testi: bir işletmenin verisi dışa aktarılıp boş bir işletmeye içe aktarıldığında sayılar
birebir korunur; aynı dosyanın ikinci yüklemesi 0 satır ekler.

### Alanlar ve eş anlamlılar

Eş anlamlılar normalleştirilmiş hâlleriyle; * zorunlu. † işaretliler sonradan (2026-10-02, DUR 1 kararı) eklendi.

| Tür | Alan | Eş anlamlılar |
|---|---|---|
| uyeler | uye_kimlik* | uye no, uye id, uye kodu, uye numarasi, musteri no, musteri id, musteri kodu, member id, id |
| uyeler | ad_soyad* | ad soyad, adi soyadi, uye adi, uye adi soyadi, musteri adi, isim, isim soyisim, name, full name |
| uyeler | ad / soyad | ad, adi, first name / soyad, soyadi, last name (ad_soyad yoksa "ad soyad" birleştirilir) |
| uyeler | telefon | telefon, tel, gsm, cep, cep telefonu, telefon no, phone, mobile |
| uyeler | eposta | e posta, eposta, email, e mail, mail |
| paketler | uye_kimlik* | (uyeler ile aynı) |
| paketler | paket_kimlik | paket no, paket id, uyelik no, satis no |
| paketler | paket_adi* | paket, paket adi, uyelik, uyelik tipi, uyelik turu, package, plan |
| paketler | baslangic* | baslangic, baslangic tarihi, satis tarihi, start, start date |
| paketler | bitis | bitis, bitis tarihi, son kullanma, son gecerlilik, end, end date |
| paketler | giris_hakki | giris hakki, seans, seans sayisi, ders hakki, ders sayisi, kredi, sessions |
| paketler | ucret* | ucret, tutar, fiyat, odenen, odenen tutar, price, amount, fiyati†, paket fiyati†, uyelik ucreti†, ucreti†, tutari† |
| paketler | durum | durum, status, durumu†, uyelik durumu†, paket durumu† |
| girisler | uye_kimlik* | (uyeler ile aynı) |
| girisler | tarih* | tarih, giris tarihi, ziyaret tarihi, ders tarihi, check in, checkin, date |
| girisler | saat | saat, giris saati, time |
| girisler | giris_kimlik | giris no, giris id, kayit no |
| girisler | tutar | tutar, ucret, amount |
| girisler | durum | durum, status |

(--anonim'de ad_soyad zorunlu değildir ve okunmaz.) Bir başlık birden çok alana uyarsa daha uzun eş anlamlı kazanır;
yine eşitse eşleşmez ve önizlemede "belirsiz" olarak listelenir. Tek başına "id" yalnızca uye_kimlik için ve dosyada
başka kimlik sütunu yoksa kullanılır.

Paket kuralları: tur = giris_hakki varsa 'giris', yoksa 'sure' (sure'de bitis yoksa satır hatası, DB CHECK).
durum eş anlamlıları: aktif/devam/devam ediyor/active → aktif; bitti/sona erdi/suresi doldu/expired/tamamlandi →
bitti; iptal/iptal edildi/cancelled → iptal; donduruldu/dondu/frozen → donduruldu; başka → satır hatası.
durum yoksa: bitis yok ya da bitis ≥ yerel bugün → aktif, değilse bitti.
onceki_paket_id: her üyenin paketleri baslangic'e göre sıralanır, her paket bir öncekine bağlanır (yenileme zinciri).
UPSERT'te güncellenen: ad, bitis_tarihi, giris_hakki, ucret, durum, onceki_paket_id.
Üye UPSERT'te güncellenen: ad_soyad, telefon_e164, eposta (anonim modda yalnızca ad_soyad).
Giriş durum eş anlamlıları: geldi/tamamlandi/katildi/boş → tamamlandi; iptal → iptal; gelmedi/no show → gelmedi.

## Sonradan onaylanan kararlar (proje sahibi onayı, 2026-10-02)

**Eşleştirme kuralı (DUR 1).** Eş anlamlı, başlıkta tam kelime dizisi olarak geçerse eşleşir ("Üyelik Başlangıç
Tarihi" → baslangic). 4 harften kısa eş anlamlılar ("ad", "adi", "tel", "cep", "gsm", "end") yalnızca başlığın başında
eşleşir ("Cep Tel" → telefon; "Paket Adı" üyenin adı değildir). Aynı alana birden çok başlık uyarsa önce tam eşleşen,
sonra eş anlamlısı uzun olan kazanır. Başlığında "kalan", "kullanilan", "kullanilmis", "harcanan" kelimelerinden biri
geçen sütun giris_hakki'na eşleşmez ("Kalan Seans" eşleşmeyenlere düşer). Durum için eklenen eş anlamlılar yalnızca
paketlerde (girişlerdeki "Üyelik Durumu" sütunu giriş durumuna eşleşmesin). Hassas başlık: normalleştirilmiş başlıkta
alt dize; ayrıca "t c" kelime dizisi ("T.C. No").

**Çekirdek ayrıntıları (DUR 1).** tarih_coz yalnızca (gün, saat) döndürür; yerel → UTC, saatsizse 12:00 ve gelecek
denetimi zaman_coz'dadır (ayrı saat sütunu varsayılan 12:00'den önce uygulanır). Hassas sütunların hücreleri okuma
anında atılır. Türetilmiş kimlik tekrarı → tek kayıt + uyarı; dosyadaki açık kimlik tekrarı → satır hatası
(ON CONFLICT DO UPDATE aynı komutta aynı anahtarı iki kez kabul etmez). Aynı telefon dosyada iki üyede → ikincisinde boş
+ uyarı ((isletme_id, telefon_e164) tekil indeksi). "@" içermeyen e-posta → boş + uyarı. xlsx'te 00:00 saatli tarih
hücresi saatsiz sayılır; Excel seri tarihinin kesri saattir. Sniffer bulamazsa başlıktaki en sık aday ayırıcıdır.
.txt/.tsv CSV gibi okunur; .xls reddedilir. Üye kimliği denetimi paketlere de uygulanır.

**Paket zinciri sonraki yüklemelerde (DUR 1).** Dosyada öncülü olmayan paket, aynı üyenin aynı dis_kaynak'tan gelen ve
daha önce başlamış en son veritabanı paketine bağlanır. UPSERT'te dosya bir öncül vermiyorsa var olan onceki_paket_id
korunur (COALESCE).

**Telefon çakışması (DUR 1).** Veritabanında başka bir üyede (aynı dis_kaynak + dis_kimlik hariç) olan telefon boş
bırakılır, uyarı verilir; aynı üyenin yeniden yüklenmesi uyarı üretmez.

**Yazma ayrıntıları (DUR 2).** Üye UPSERT'i telefon ve e-postayı yalnızca o sütun dosyada eşleşmişse yazar (telefon
sütunu olmayan dosya mevcut telefonları silmez). Değeri değişmeyen satır güncellenmez ("atlanan" sayılır, denetim
kaydı üretmez). Yeni paketin paket_id'si istemcide üretilir (zincir aynı işlemde kurulur); paketler başlangıç sırasıyla
yazılır. Model yakınsamazsa (RuntimeError) da yenileme uyarıya döner (içe aktarma o anda kalıcıdır). %10 eşiği yaz()
içinde de denetlenir. Komut çıkış kodları: eşleştirme hatası 2, eşik reddi 1. Dışa aktarmada "Paket No" ve "E-posta"
sütunları var; silinmiş üyeler aktarılmaz.

**Fit girdisi kanonik sırada (DUR 2).** bgnbd.fit ve mbgnbd.fit (x, t_x, T), gamma_gamma.fit (x, m; süzmeden sonra)
girdisini optimizasyondan önce np.lexsort ile kanonik sıraya dizer (`analitik.bgnbd.kanonik_sira`). Olabilirlik
üyelerin çoklu kümesinin fonksiyonudur; aynı veri, kimlikler ve okuma sırası ne olursa olsun bit bit aynı parametreyi
verir. Kanonik sıra belirlenimcilik sağlar, tanımlanabilirliği çözmez (bkz. "4b-1 sonuçları").

## 4b-1'de yapılanlar

Dosyalar:
- `servisler/ice_aktarma.py`: saf çekirdek (veritabanı ve FastAPI yok): dosya_oku (CSV/XLSX; openpyxl yalnızca xlsx
  okuyan fonksiyonun içinde import edilir), baslik_normallestir, esleme_tahmin_et, esleme_dogrula, tarih_coz,
  zaman_coz, para_coz, durum_coz, satirlari_hazirla.
- `servisler/ice_aktarma_yaz.py`: hazirliklari_olustur (saat dilimi, bilinen üyeler) ve yaz (tek işlem, 1.000'lik
  parçalar, ON CONFLICT ... RETURNING (xmax = 0), ardından ayrı işlemde yenileme riski).
- `servisler/ice_aktar.py`: komut (önizleme, --onayla, --esleme, --anonim); önerilen eşleştirme
  `raporlar/ice_aktarma_esleme.json`.
- `sentetik/disa_aktar.py`: işletmenin üyelerini, paketlerini ve tamamlanmış girişlerini Türkçe Excel biçiminde
  (cp1254, ";", gg.aa.yyyy SS:DD, "1.250,00") üç CSV'ye yazar; csv_uret testte çağrılabilir, kilit komutta (_demo).
- `analitik/bgnbd.py`, `analitik/mbgnbd.py`, `analitik/gamma_gamma.py`: fit girdisi kanonik sırada.
- Testler: `tests/test_ice_aktarma_cekirdek.py` (94, veritabanı yok), `tests/test_ice_aktarma_db.py` (11, panosu_test),
  üç analitik test dosyasına birer permütasyon testi (parametre ==, toleranssız).

Komutlar:
```powershell
.\.venv\Scripts\python.exe -m servisler.ice_aktar --veritabani panosu_demo --isletme <uuid> --kaynak <ad> --uyeler u.csv --paketler p.csv --girisler g.csv
.\.venv\Scripts\python.exe -m servisler.ice_aktar ... --esleme raporlar/ice_aktarma_esleme.json --onayla
.\.venv\Scripts\python.exe -m sentetik.disa_aktar --veritabani panosu_demo --isletme <uuid> --cikti raporlar/disa_aktarma/
```

## 4b-1 sonuçları

### Gidiş-dönüş (K41, `test_gidis_donus_sayilar_korunur_ve_ikinci_yukleme_eklemez`)

A'daki 33 üye, ~6 aylık girişler, süre ve giriş bazlı paketler (3 paketli zincirler dahil) dışa aktarılıp B'ye içe
aktarıldı. Birebir eşit: üye/paket/tamamlanmış giriş sayıları, üye başına giriş sayısı ve ilk/son giriş zamanı, paket
alanları ve ücret toplamı (Decimal), tür/durum dağılımı, zincirler. İkinci yükleme 0 ekler, 0 günceller; adı
değiştirilmiş dosya 1 güncellenen verir, giriş eklemez. Yenileme riski (19 aktif paket), testin tek başına 8 çalıştırması:

| | p_hayatta_simdi en büyük fark (sınır 0,01) | p_yenileme ortalama fark (sınır 0,03) | Sonuç |
|---|---|---|---|
| Kanonik sıra öncesi | 0,0175–0,0312 | 0,0084–0,0162 | 8/8 kırmızı |
| Kanonik sıra sonrası | 0,0000 (8/8) | 0,0001–0,0024 | 8/8 yeşil |

Kanonik sıra öncesindeki farkın nedeni içe aktarma değildi (girdiler birebir aynıydı): yenileme_hesapla üyeleri
musteri_id (rastgele UUID) sırasıyla okuyordu ve MBG/NBD uyumu sıraya göre farklı noktalarda duruyordu. Kanıt: aynı
veride (29 üye) üye sırası değiştirilerek 12 uydurmada a/(a+b) 0,009–0,011 sabit, a+b 29 ile 164.000 arası; r, α
sınıra kaçıyor (r/α ≈ 0,148; α birkaç uydurmada üst sınır e¹²'de); log-olabilirlik farkı ≤ 0,8; bireysel p_hayatta
farkı 0,031'e kadar. Kanonik sıra belirlenimcilik sağlar, tanımlanabilirliği çözmez; kök çözüm ((μ, κ) yeniden
parametreleme + log κ için zayıf önsel; r, α için benzeri) ayrı adımda. Kanonik sıra sonrası p_yenileme farkı
Monte Carlo tohumunun paket_id'ye bağlı olmasındandır.

### Elle deneme (panosu_demo, 2026-10-02)

[DEMO] Butik Reformer `sentetik.disa_aktar` ile dışa aktarıldı (163 üye, 983 paket, 15.489 giriş) ve
`servisler.isletme_ac` ile açılan [DEMO] Butik Kopya'ya `--kaynak butik` ile içe aktarıldı.

Önizleme özeti: üç dosya da cp1254, ";" ayırıcı. Eşleştirme: uyeler uye_kimlik ← Üye No, ad_soyad ← Adı Soyadı,
telefon ← Telefon, eposta ← E-posta; paketler 8 alanın 8'i (Üye No, Paket No, Paket Adı, Başlangıç Tarihi, Bitiş
Tarihi, Seans Sayısı, Ücret, Durum); girisler uye_kimlik ← Üye No, tarih ← Giriş Tarihi. Belirsiz, eşleşmeyen ya da
hassas başlık yok. Okunan/geçerli/hatalı: üyeler 163/163/0, paketler 983/983/0, girişler 15.489/15.467/0
("22 × aynı türetilmiş kimlikli tekrar satır tek kayıt sayıldı"). --onayla: 163 + 983 + 15.467 eklendi, güncellenen ve
atlanan 0; yenileme riski 81 aktif paket. Butik Reformer'ın riski aynı gün yeni kodla yeniden hesaplandı.

| | Butik Reformer | Butik Kopya |
|---|---|---|
| Üye / paket / aktif paket | 163 / 983 / 81 | 163 / 983 / 81 |
| Tamamlanmış giriş | 15.489 | 15.467 (−22) |
| Aktif üye (bugün) | 79 | 79 |
| Eylül kasaya giren (paket geliri) | 151.200,00 | 151.200,00 |
| Eylül gerçek gelir | 156.572,75 | 156.639,41 (+66,66) |
| Eylül gider / kâr-zarar | 124.000,00 / 32.572,75 | — / — (gider girilmedi) |
| Eylül başabaş / ortalama aktif üye | 63 / 79,33 | — / 79,33 |
| Riskteki Para (45 gün) | 22.384,95 | 22.511,85 (+126,90; %0,57) |

Farkların doğrulanmış nedenleri:
- 22 giriş: Butik Reformer'da 9 üyede saniyesine kadar aynı zamanlı 22 ziyaret çifti var (dis_kimlik'leri farklı;
  sentetik üreticinin kusuru, CLAUDE.md "Açık konular"). Giriş dosyasında kimlik sütunu olmadığından K33 ile tek kayda
  indi; bu doğru davranıştır (yukarıda K33 notu).
- Gerçek gelir: aylar arası kayma, kayıp değil. Bugüne kadar hak edilen toplam ikisinde de 3.057.281,44; Ağustos
  −66,66, Eylül +66,66. Giriş bazlı bir pakette tek kayda inen giriş, kullanılmamış hak olarak son kullanma gününde
  tanındı. Kasaya giren ciroda fark yok.
- Kâr/zarar ve başabaş: giderler içe aktarılmaz (K29); Kopya'da gider girilmedi.
- Riskteki Para'daki %0,57 fark: Monte Carlo tohumu (paket_id) kaynaklı simülasyon gürültüsü (p_yenileme ortalama
  mutlak fark 0,006). Tek kayda inen 22 girişin p_hayatta_simdi'ye etkisi en çok 0,0008 (81 aktif paketin 23'ünde).

## Kalanlar

- **4b-2 Gerçek veride doğrulama (K40):** H onayı bekliyor; gerçek Faz 0 verisi gelince.
- **4b-3 Web ekranı:** eşleştirmenin işletme başına saklanması, sahip/yönetici yetkisi, salt okunur demoda kapalı;
  openpyxl'in requirements-uretim.txt'e eklenmesi ayrı onayla.
- **(μ, κ) adımı:** MBG/NBD tanımlanabilirliği (a,b sırtı; r, α Poisson sınırı); backtest sonuçları orada yeniden
  üretilecek.
- **Sentetik üretici:** aynı anlı ziyaret çiftleri (düşük öncelik; düzeltmek demo sayılarını değiştirir, ayrı karar).
