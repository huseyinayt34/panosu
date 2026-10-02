# Adım 9: Web paneli: tasarım ve kararlar

## KARARLAR (proje sahibi onayı, 2026-10-01)

**K1 Teknoloji:** Web paneli FastAPI'nin içinde Jinja2 şablonları + HTMX ile yapılır (Next.js değil). Tek dil, tek
proje, tek yayına alma. JSON API (Bearer) aynen kalır.

**K2 Geçmiş ayda aktif üye ve başabaş farkı:** Tamamlanmış (geçmiş) bir ayda başabaş farkı ORTALAMA aktif üyeyle
ölçülür: basabas_farki_ortalama = ortalama_aktif_uye − basabas_uye_sayisi. Gerekçe: başabaş zaten
B = ⌈G / u⌉, u = R / ort ile tanımlı, yani B = ⌈G·ort / R⌉; bu yüzden ort − B ≥ 0 olması (yuvarlama payı hariç)
R ≥ G, yani o ayın kârda olması demektir. Ay sonu stoku bu tutarlılığı sağlamaz. Geçmiş ayda aktif_uye_sayisi
ayın SON GÜNÜNDEKİ aktif üyedir (bilgi amaçlı), basabas_farki ve zarar_icin_kayip_uye None'dır ("N üye
kaybederseniz" cümlesi yalnızca içinde bulunulan ayda anlamlı). İçinde bulunulan ay (ve ileri tarihli ay) için
davranış değişmez: bugünün aktif üyesi.

**K3 Web oturumu:** Erişim ve yenileme tokenları httpOnly + SameSite=Lax çerezlerde (Secure yalnızca ortam=uretim).
Durum değiştiren her web isteğinde CSRF tokenı (çift gönderim: çerez + form alanı veya X-CSRF-Token başlığı).
Yenileme yalnızca tam sayfa GET isteğinde yapılır; HTMX parça isteğinde erişim çerezi geçersizse 401 +
"HX-Refresh: true" döner. Neden: yenileme tokenı tek kullanımlık; iki paralel istek aynı tokenı yenilemeye
çalışırsa ikincisi "yeniden kullanım" sayılır ve oturum ailesi iptal olur.

**Bölümleme:** 9a iskelet + giriş + finans kutuları; 9b riskli ve sessiz üye tabloları + "neden riskli";
9c haftalık rapor bağlantısı, mobil cila, demo cilası.

## 9a'da yapılanlar

**K2 (servis):** `servisler/finans_servisi.py` ve `semalar/panel.py`'de `gecmis_ay` ve `basabas_farki_ortalama`
alanları eklendi. `/panel/finans` yanıtı da bu iki alanı içerir.

**Uçlar** (`rotalar/web.py`, OpenAPI şemasında görünmez):

| Uç | Davranış |
|---|---|
| `GET /` | Geçerli oturum → 303 `/pano`; yoksa 303 `/giris` (eski JSON karşılama mesajı kaldırıldı) |
| `GET /giris` | Form (e-posta, parola, gizli csrf); geçerli oturum varsa 303 `/pano` |
| `POST /giris` | CSRF; hatalı giriş ve doğrulama hatası aynı mesaj ("E-posta veya parola hatalı", 401); başarıda çerezler + CSRF yenilenir; tek üyelik → `/pano`, değilse `/isletme` |
| `GET /isletme` | Kullanıcının üyelikleri; seçili işletme işaretli |
| `POST /isletme` | CSRF; üyelik sunucuda doğrulanır (`servis.isletme_sec`); başka işletme → 403 |
| `POST /cikis` | CSRF; oturum ailesi kapatılır, üç çerez silinir |
| `GET /pano?ay=YYYY-AA` | Finans kutuları; ay yok / geçersiz / ileri → içinde bulunulan ay; ay seçici son 12 ay |
| `GET /pano/finans?ay=` | Yalnızca `_finans.html` parçası (HTMX); yanıtta `HX-Push-Url: /pano?ay=…` |

- Rol: sahip ve yönetici finansı görür; çalışana finans hesaplanmaz, bilgi cümlesi gösterilir.
- Tüm web yanıtlarında `Cache-Control: no-store`.
- Kiracı oturumu, API ile ortak `bagimliliklar.kiraci_oturumu(kimlik)` context manager'ıyla açılır (RLS ve
  `after_begin` değişmedi). Token çözme API ile ortaktır (`token_kimligi`).

**Çerezler** (üçü de `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` yalnızca `ortam=uretim`):

| Çerez | İçerik | Ömür |
|---|---|---|
| `panosu_erisim` | Erişim tokenı (JWT) | `erisim_suresi_dk` |
| `panosu_yenileme` | Yenileme tokenı (tek kullanımlık) | `yenileme_suresi_gun` |
| `panosu_csrf` | `secrets.token_urlsafe(32)`; şablona sunucuda basılır, JS okumaz; girişte yenilenir | oturum çerezi |

**Dosyalar:** `rotalar/web.py`, `sablonlar/web/` (`taban.html`, `giris.html`, `isletme_sec.html`, `pano.html`,
`_finans.html`), `statik/htmx.min.js` (htmx 2.0.4, SHA-256
`e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447`), `statik/panel.css`,
`sentetik/demo_sunucu.py`, `servisler/bicim.py` (`ondalik`), `tests/test_web.py`.

## 9b ve 9c'ye kalanlar

- **9b:** Riskli (yenileme) ve sessiz üye tabloları (tüm rollere açık), her üye için "neden riskli" açıklaması
  (son ziyaretten bu yana geçen gün, normal ziyaret aralığına göre sapma, paket bitişine kalan gün).
- **9c:** Haftalık rapor bağlantısı, mobil cila, demo cilası; demo verisinin bugüne kaydırılması (CLAUDE.md
  "Açık konular").
