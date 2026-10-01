"""Sentetik veriyi PostgreSQL'e yükler. YALNIZCA adı "_demo" ile biten bir veritabanına yazar.

Hedef veritabanı açıkça verilir (--veritabani). Bağlantı adresleri .env'deki iki URL'den yalnızca
veritabanı adı değiştirilerek türetilir; ad "_demo" ile bitmiyorsa bağlantı kurulmadan durulur.

İki ayrı bağlantı kullanılır (en az yetki ilkesi):
  * YÖNETİCİ (PANOSU_MIGRASYON_URL'nin rolü): yalnızca (1) demo işletme sahibi kullanıcıyı oluşturmak ve
    (2) --temizle ile eski demo verisini silmek için. panosu_app'in kullanıcı ekleme ve iş verisini
    silme yetkisi bilinçli olarak YOKTUR.
  * UYGULAMA (PANOSU_VERITABANI_URL'nin rolü = panosu_app): tüm iş verisi RLS altında yazılır. Her işletme
    kendi işleminde (transaction) ve kendi kiracı bağlamında oluşturulur; yani yükleyici de
    uygulamanın güvenlik kurallarına tabidir.
"""

import csv
import uuid
from pathlib import Path

from sqlalchemy import Engine, create_engine, insert, text
from sqlalchemy.engine import make_url

from config import ayarlar
from models import Hizmet, Musteri, Ziyaret, ZiyaretKalemi
from sentetik.uretici import SentetikVeri

DEMO_ONEK = "[DEMO]"
DEMO_SONEKI = "_demo"
DEMO_SAHIP_EPOSTA = "demo-sahip@example.com"

# Yabancı anahtar bağımlılıklarına göre silme sırası. denetim_kayitlari en sonda: silme trigger'ları
# da denetim kaydı ürettiği için.
_SILME_SIRASI = (
    "geri_kazanimlar", "mesaj_gonderimleri", "churn_skorlari", "yenileme_riskleri", "musteri_paketleri", "isletme_giderleri",
    "musteri_izinleri", "ziyaret_kalemleri",
    "ziyaretler", "kampanyalar", "musteriler", "hizmetler", "abonelikler", "uyelikler", "denetim_kayitlari",
)


class DemoVerisiZatenVar(RuntimeError):
    pass


class DemoDisiVeritabani(ValueError):
    pass


def demo_veritabani_dogrula(veritabani: str) -> None:
    """Ad "_demo" ile bitmiyorsa DemoDisiVeritabani fırlatır. Veritabanına bağlanmaz."""
    if not veritabani or not veritabani.endswith(DEMO_SONEKI):
        raise DemoDisiVeritabani(
            f"Güvenlik: sentetik veri yalnızca adı '{DEMO_SONEKI}' ile biten bir veritabanına yüklenebilir "
            f"(verilen: {veritabani!r}). Canlı veya test veritabanına yazılmaz."
        )


def baglanti_adresleri(veritabani: str) -> tuple[str, str]:
    """(yönetici, uygulama) adresleri: .env'deki URL'ler, yalnızca veritabanı adı değiştirilerek.

    Önce ad doğrulanır; yani "_demo" dışı bir ad için hiçbir adres üretilmez.
    """
    demo_veritabani_dogrula(veritabani)
    if not ayarlar.migrasyon_url:
        raise RuntimeError("PANOSU_MIGRASYON_URL tanımlı değil (.env dosyasına bakın).")
    return tuple(
        make_url(url).set(database=veritabani).render_as_string(hide_password=False)
        for url in (ayarlar.migrasyon_url, ayarlar.veritabani_url)
    )


def demo_isletme_sayisi(yonetici: Engine) -> int:
    with yonetici.connect() as con:
        return con.scalar(text("SELECT count(*) FROM isletmeler WHERE ad LIKE :o"), {"o": f"{DEMO_ONEK}%"})


def temizle(yonetici: Engine) -> int:
    """Adı [DEMO] ile başlayan işletmeleri ve tüm verilerini siler. Silinen işletme sayısını döndürür."""
    demo_veritabani_dogrula(yonetici.url.database)
    with yonetici.begin() as con:
        idler = con.execute(
            text("SELECT isletme_id FROM isletmeler WHERE ad LIKE :o"), {"o": f"{DEMO_ONEK}%"}
        ).scalars().all()
        if not idler:
            return 0
        for tablo in _SILME_SIRASI:
            con.execute(text(f"DELETE FROM {tablo} WHERE isletme_id = ANY(:idler)"), {"idler": list(idler)})
        con.execute(text("DELETE FROM isletmeler WHERE isletme_id = ANY(:idler)"), {"idler": list(idler)})
    return len(idler)


def _demo_sahibi(yonetici: Engine) -> uuid.UUID:
    with yonetici.begin() as con:
        return con.execute(
            text("INSERT INTO kullanicilar (eposta, ad_soyad) VALUES (:e, 'Demo İşletme Sahibi') "
                 "ON CONFLICT (eposta) DO UPDATE SET ad_soyad = EXCLUDED.ad_soyad RETURNING kullanici_id"),
            {"e": DEMO_SAHIP_EPOSTA},
        ).scalar_one()


def _kiracili(satirlar: list[dict], isletme_id: uuid.UUID) -> list[dict]:
    return [{**s, "isletme_id": isletme_id} for s in satirlar]


def yukle(
    veri: SentetikVeri,
    veritabani: str,
    *,
    eskiyi_sil: bool = False,
    ilerleme=print,
) -> dict[str, uuid.UUID]:
    """Veriyi "_demo" ile biten veritabanına yükler; sektör -> isletme_id eşlemesini döndürür."""
    yonetici_url, uygulama_url = baglanti_adresleri(veritabani)     # ad doğrulanmadan bağlantı yok
    yonetici, uygulama = create_engine(yonetici_url), create_engine(uygulama_url)
    try:
        if demo_isletme_sayisi(yonetici):
            if not eskiyi_sil:
                raise DemoVerisiZatenVar("Veritabanında zaten demo verisi var. Yenilemek için --temizle kullanın.")
            ilerleme(f"Eski demo verisi silindi: {temizle(yonetici)} işletme")

        sahip = _demo_sahibi(yonetici)
        eslesme: dict[str, uuid.UUID] = {}

        for isletme in veri.isletmeler:
            p = isletme.profil
            with uygulama.begin() as con:                       # işletme başına TEK işlem
                con.execute(text("SELECT set_config('app.kullanici_id', :u, true)"), {"u": str(sahip)})
                # isletme_olustur: işletme + sahip üyeliği + abonelik; app.isletme_id'yi de ayarlar
                iid = con.execute(
                    text("SELECT isletme_olustur(:ad, :u, :s)"), {"ad": p.isletme_adi, "u": sahip, "s": p.sektor}
                ).scalar_one()

                con.execute(insert(Hizmet.__table__), _kiracili(isletme.hizmetler, iid))
                con.execute(insert(Musteri.__table__), _kiracili(isletme.musteriler, iid))
                if isletme.izinler:
                    con.execute(
                        text("INSERT INTO musteri_izinleri "
                             "(isletme_id, musteri_id, kanal, durum, kaynak, kayit_zamani, kaydeden_kullanici_id) "
                             "VALUES (:isletme_id, :musteri_id, :kanal, :durum, :kaynak, :kayit_zamani, :sahip)"),
                        [{**s, "isletme_id": iid, "sahip": sahip} for s in isletme.izinler],
                    )
                con.execute(insert(Ziyaret.__table__), _kiracili(isletme.ziyaretler, iid))
                con.execute(insert(ZiyaretKalemi.__table__), _kiracili(isletme.kalemler, iid))

            eslesme[p.sektor] = iid
            ilerleme(f"  {p.isletme_adi:<32} {len(isletme.musteriler):>5} müşteri "
                     f"{len(isletme.ziyaretler):>7} ziyaret {len(isletme.kalemler):>7} kalem")
        return eslesme
    finally:
        yonetici.dispose()
        uygulama.dispose()


def gercek_degerleri_yaz(veri: SentetikVeri, eslesme: dict[str, uuid.UUID], dosya: Path) -> None:
    """Modellerin göremeyeceği gerçek parametreleri CSV'ye yazar (Faz 3-4 değerlendirmesi için)."""
    dosya.parent.mkdir(parents=True, exist_ok=True)
    with dosya.open("w", newline="", encoding="utf-8") as f:
        yazici = csv.writer(f)
        yazici.writerow(["isletme_id", "sektor", "musteri_id", "lambda_gunluk", "p_birakma",
                         "harcama_egilimi", "edinim_zamani", "olum_zamani", "canli_mi", "tamamlanan_ziyaret"])
        for isletme in veri.isletmeler:
            for g in isletme.gercek:
                yazici.writerow([
                    eslesme.get(g.sektor, ""), g.sektor, g.musteri_id, f"{g.lambda_gunluk:.6f}",
                    f"{g.p_birakma:.6f}", f"{g.harcama_egilimi:.4f}", g.edinim_zamani.isoformat(),
                    g.olum_zamani.isoformat() if g.olum_zamani else "", int(g.canli_mi), g.tamamlanan_ziyaret,
                ])
