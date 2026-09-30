# Adım 4a: Hizmetler ve Ziyaretler API'si

Genel kurallar için `CLAUDE.md`'ye bak. Bu adımda şema değişikliği YOK.

## Tasarım kararları (proje sahibi onaylı)
| Konu | Karar |
|---|---|
| Hizmet ekleme/düzenleme | Yalnızca `sahip`/`yonetici`. Listeyi tüm roller görür |
| Hizmet silme | Yok. `aktif_mi = false` ile pasifleştirilir |
| Ziyaret tutarı | Kalem varsa toplamı sunucu hesaplar; kalem yoksa `toplam_tutar` zorunlu |
| Kalem fiyatı | Gönderilmezse hizmetin liste fiyatı kullanılır |
| Saat dilimi | Saat dilimi içermeyen zaman, işletmenin `saat_dilimi` ile yorumlanır |
| Gelecek tarihli ziyaret | Şu andan 5 dakikadan fazla ileri → 422 |
| Ziyaret düzeltme | Tutar ve zaman değiştirilemez; yanlış kayıt `iptal` edilip yenisi girilir |
| Müşteri özeti | `GET /musteriler/{id}/ozet`, `v_musteri_ozet` view'ından |

## 1. Hizmetler
Dosyalar: `semalar/hizmet.py`, `servisler/hizmet_servisi.py`, `rotalar/hizmetler.py`, `tests/test_hizmet_api.py`

- `HizmetOlustur`: ad (kırpılır, 1–100), kategori (str|None, ≤50), liste_fiyati (Decimal|None, ≥0, 2 ondalık),
  sure_dk (int|None, >0). `extra="forbid"`.
- `HizmetGuncelle`: aynı alanlar + aktif_mi, hepsi opsiyonel; boş gövde → 422.
- `HizmetYanit`: hizmet_id, ad, kategori, liste_fiyati, sure_dk, aktif_mi, olusturma_zamani, guncelleme_zamani.

Uçlar (prefix `/hizmetler`, tag "Hizmetler"):
- `POST ""` (sahip/yonetici) → 201 | 409 aynı ad (UNIQUE (isletme_id, ad); kısıt adı
  `e.orig.diag.constraint_name`'den okunur) | 403 calisan
- `GET ""` (tüm roller) → liste. `aktif: bool | None = True`; `None` gönderilirse tümü.
  Sıralama: kategori, ad.
- `GET "/{hizmet_id}"` → 404 (başka kiracınınki de 404)
- `PATCH "/{hizmet_id}"` (sahip/yonetici) → 200 | 404 | 409
- Silme ucu yok; pasifleştirme `PATCH {"aktif_mi": false}`.

## 2. Ziyaretler
Dosyalar: `semalar/ziyaret.py`, `servisler/ziyaret_servisi.py`, `rotalar/ziyaretler.py`, `tests/test_ziyaret_api.py`

Şemalar:
- `KalemGirdi`: hizmet_id (UUID|None), aciklama (str|None, ≤200), adet (int ≥1, vars. 1),
  birim_fiyat (Decimal|None, ≥0), indirim_tutari (Decimal ≥0, vars. 0).
  hizmet_id ve aciklama ikisi birden boşsa → 422. hizmet_id yoksa birim_fiyat zorunlu.
- `ZiyaretOlustur`: ziyaret_zamani (datetime), toplam_tutar (Decimal|None, ≥0),
  odeme_yontemi (nakit|kart|havale|diger|None), notlar (str|None, ≤1000),
  kalemler (list[KalemGirdi], vars. boş, ≤50). `extra="forbid"`.
- `ZiyaretGuncelle`: yalnızca durum (tamamlandi|iptal|gelmedi), odeme_yontemi, notlar; boş gövde → 422.
- `KalemYanit`, `ZiyaretYanit` (ziyaret_id, musteri_id, ziyaret_zamani, durum, toplam_tutar,
  odeme_yontemi, notlar, kalemler, olusturma_zamani). isletme_id döndürülmez.
- `MusteriOzet`: musteri_id, ziyaret_sayisi, ilk_ziyaret, son_ziyaret, toplam_ciro, ort_sepet_tutari,
  ciro_son_90_gun (`v_musteri_ozet` view'ı, `text()` SELECT ile; model eklenmez).

Servis kuralları:
- Müşteri `musteri_servisi.musteri_getir` ile alınır (silinmiş / başka kiracının müşterisi → 404).
- Saat dilimsiz `ziyaret_zamani`, `isletmeler.saat_dilimi` (zoneinfo) ile yorumlanır.
- Her kalemin hizmet_id'si aynı oturumda aranır (RLS nedeniyle başka kiracının hizmeti bulunmaz);
  bulunamazsa 422 "Hizmet bulunamadı". Pasif hizmet kabul edilir (geçmiş kayıt girilebilmeli).
  birim_fiyat yoksa liste_fiyati; o da yoksa 422.
- Kalem tutarı = adet × birim_fiyat − indirim_tutari; negatifse 422.
- Kalem varsa toplam_tutar = kalem toplamı; istemci farklı bir toplam gönderdiyse 422.
  Kalem yoksa toplam_tutar zorunlu.
- Ziyaret ve kalemleri TEK işlemde yazılır.

Uçlar (tag "Ziyaretler", tüm roller):
- `POST "/musteriler/{musteri_id}/ziyaretler"` → 201 | 404 | 422
- `GET "/musteriler/{musteri_id}/ziyaretler"` → liste (ziyaret_zamani azalan), limit 1–200 vars. 50, offset
- `GET "/ziyaretler/{ziyaret_id}"` → kalemlerle | 404
- `PATCH "/ziyaretler/{ziyaret_id}"` → 200 | 404 | 422
- `GET "/musteriler/{musteri_id}/ozet"` → MusteriOzet | 404

## 3. Testler
`test_hizmet_api.py`: oluşturma; aynı ad 409 / diğer kiracıda aynı ad 201; calisan POST ve PATCH → 403,
GET → 200; pasifleştirilen hizmet varsayılan listede yok, `aktif=false`'da var; başka kiracının hizmeti 404.

`test_ziyaret_api.py`:
- Kalemsiz ziyaret: toplam_tutar yoksa 422, varsa 201.
- Kalemli ziyaret: toplam sunucuda hesaplanır; liste fiyatı devralınır; indirim uygulanır;
  uyumsuz toplam_tutar 422; negatif kalem tutarı 422.
- Başka kiracının hizmet_id'si kalemde → 422; başka kiracının müşterisine ziyaret → 404.
- Saat dilimsiz zaman İstanbul saatiyle kaydedilir (UTC karşılığı doğrulanır); gelecek tarih 422.
- PATCH ile iptal sonrası özetteki ziyaret_sayisi ve toplam_ciro iptal edileni içermez.
- PATCH'te toplam_tutar veya ziyaret_zamani gönderilirse 422.
- Özet: iki tamamlanmış ziyaret sonrası sayı 2, toplam ve ortalama doğru (Decimal karşılaştırması).
- Silinmiş müşteriye ziyaret eklenemez (404). Başka kiracının ziyaretine GET/PATCH → 404.

Test temizliği: conftest'teki `_kiraci_temizle` ziyaret_kalemleri, ziyaretler ve hizmetler tablolarını
siliyor. Yeni fixture gerekirse aynı `lock_timeout` kalıbını kullan.

## Kabul kriterleri
- Tam `pytest -v` yeşil, skip/xfail yok.
- `python -c "import main"` hatasız; /docs'ta Hizmetler (4 uç) ve Ziyaretler (5 uç) grupları görünür.
- Rapor: değişen/yeni dosyalar, pytest özet satırı, talimattan her sapma.
