"""İçe aktarmanın veritabanına yazılması (Adım 4b-1, `docs/adim-4b-tasarim.md`, K32, K33, K38, K39). FastAPI yok.

Kiracı bağlamlı oturumla (db.info["isletme_id"]; after_begin bağlamı kurar) çalışır: RLS süzer, sorgulara isletme_id
filtresi eklenmez, isletme_id INSERT'e konmaz (DB varsayılanı aktif_isletme()). Sıra üyeler → paketler → girişler,
TEK işlemde; herhangi bir hatada tamamı geri alınır. Ardından ayrı işlemde yenileme riski yeniden hesaplanır.

Tekrar yükleme (K33): üye ve paket UPSERT, giriş yalnızca EKLENİR. Değeri değişmeyen satır güncellenmez (ON CONFLICT
... WHERE IS DISTINCT FROM), "atlanan" sayılır ve denetim kaydı üretmez.
Paket zinciri (proje sahibi kararı, 2026-10-02): dosyada öncülü olmayan paket, aynı üyenin aynı dis_kaynak'tan gelen ve
daha önce başlamış en son veritabanı paketine bağlanır; öncül bulunamazsa var olan onceki_paket_id korunur (COALESCE).
Telefon: veritabanında BAŞKA bir üyede (aynı dis_kaynak + dis_kimlik hariç) olan telefon boş bırakılır, uyarı sayılır.
"""

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from models import Isletme, Musteri, MusteriPaketi, Ziyaret
from servisler.ice_aktarma import (
    TURLER,
    Hazirlik,
    IceAktarmaHatasi,
    Tablo,
    UyeKaydi,
    satirlari_hazirla,
)
from servisler.yenileme_servisi import YetersizVeri, yenileme_hesapla

PARCA = 1000


class EsikAsildi(IceAktarmaHatasi):
    """K38: bir dosyada hatalı satır oranı %10'un üzerinde; hiçbir şey yazılmaz."""


@dataclass
class TurSonucu:
    eklenen: int = 0
    guncellenen: int = 0
    atlanan: int = 0


@dataclass
class Sonuc:
    turler: dict[str, TurSonucu] = field(default_factory=dict)
    uyarilar: Counter = field(default_factory=Counter)
    yenilenen: int | None = None                 # yenileme riski yazılan paket sayısı
    yenileme_uyarisi: str | None = None


def isletme_saat_dilimi(db: Session) -> str | None:
    """Oturumdaki işletmenin saat dilimi; işletme yoksa (ya da RLS göstermiyorsa) None."""
    return db.scalar(select(Isletme.saat_dilimi).where(Isletme.isletme_id == func.aktif_isletme()))


def uye_idleri(db: Session, dis_kaynak: str) -> dict[str, uuid.UUID]:
    """Aynı dis_kaynak'lı üyeler: dis_kimlik → musteri_id."""
    return dict(db.execute(select(Musteri.dis_kimlik, Musteri.musteri_id).where(Musteri.dis_kaynak == dis_kaynak)).all())


def hazirliklari_olustur(db: Session, tablolar: dict[str, Tablo], eslemeler: dict[str, dict[str, str | None]],
                         dis_kaynak: str, anonim: bool) -> dict[str, Hazirlik]:
    """Dosyaları üyeler → paketler → girişler sırasıyla hazırlar. Paket ve girişteki üye kimliği bu çalıştırmanın
    geçerli üyelerinde ya da veritabanında (aynı dis_kaynak) olmalıdır (K38). Veritabanına yazmaz."""
    dilim = isletme_saat_dilimi(db)
    if dilim is None:
        raise IceAktarmaHatasi("İşletme bulunamadı")
    bugun = datetime.now(ZoneInfo(dilim)).date()
    bilinen = set(uye_idleri(db, dis_kaynak))
    sonuc: dict[str, Hazirlik] = {}
    for tur in TURLER:
        if tur not in tablolar:
            continue
        h = satirlari_hazirla(tur, tablolar[tur], eslemeler[tur], dilim, bugun, anonim, dis_kaynak,
                              bilinen_uyeler=None if tur == "uyeler" else bilinen)
        if tur == "uyeler":
            bilinen |= {k.dis_kimlik for k in h.kayitlar}
        sonuc[tur] = h
    return sonuc


def yaz(db: Session, hazirliklar: list[Hazirlik], dis_kaynak: str, yenile: bool = True) -> Sonuc:
    sirali = {h.tur: h for h in hazirliklar}
    if len(sirali) != len(hazirliklar) or any(h.dis_kaynak != dis_kaynak for h in hazirliklar):
        raise ValueError("Her türden en çok bir dosya ve tek bir dis_kaynak olmalı")
    if asanlar := [h.tur for h in hazirliklar if h.esik_asildi]:
        raise EsikAsildi(f"Hatalı satır oranı %10'un üzerinde ({', '.join(asanlar)}); eşleştirmeyi kontrol et")

    sonuc = Sonuc()
    try:
        if h := sirali.get("uyeler"):
            sonuc.turler["uyeler"] = _uyeleri_yaz(db, h, dis_kaynak, sonuc.uyarilar)
        uyeler = uye_idleri(db, dis_kaynak)          # bu çalıştırmanın üyeleri + veritabanındakiler
        if h := sirali.get("paketler"):
            sonuc.turler["paketler"] = _paketleri_yaz(db, h, dis_kaynak, uyeler)
        if h := sirali.get("girisler"):
            sonuc.turler["girisler"] = _girisleri_yaz(db, h, dis_kaynak, uyeler)
        db.commit()
    except Exception:
        db.rollback()
        raise

    if yenile:                                       # ayrı işlem (K39); içe aktarma zaten kalıcı
        try:
            sonuc.yenilenen = yenileme_hesapla(db)
        except YetersizVeri as hata:
            db.rollback()
            sonuc.yenileme_uyarisi = f"Yenileme riski hesaplanmadı: {hata}"
        except RuntimeError:                         # MBG/NBD yakınsamadı (CLAUDE.md "Açık konular")
            db.rollback()
            sonuc.yenileme_uyarisi = "Yenileme riski hesaplanmadı: model yakınsamadı"
    return sonuc


def _parcalar(liste: list) -> list[list]:
    return [liste[i:i + PARCA] for i in range(0, len(liste), PARCA)]


def _xmax_sifir():
    """RETURNING'de: satır yeni eklendiyse true, ON CONFLICT ile güncellendiyse false."""
    return literal_column("(xmax = 0)").label("eklendi")


def _upsert_say(db: Session, ifade, adet: int, sonuc: TurSonucu) -> None:
    """RETURNING yalnızca eklenen ve gerçekten değişen satırları döndürür; kalanı atlanandır."""
    satirlar = db.execute(ifade).all()
    eklenen = sum(1 for s in satirlar if s.eklendi)
    sonuc.eklenen += eklenen
    sonuc.guncellenen += len(satirlar) - eklenen
    sonuc.atlanan += adet - len(satirlar)


def _telefon_cakismalari(db: Session, kayitlar: list[UyeKaydi], dis_kaynak: str,
                         uyarilar: Counter) -> list[UyeKaydi]:
    telefonlar = {k.telefon_e164 for k in kayitlar if k.telefon_e164}
    if not telefonlar:
        return kayitlar
    sahipler: dict[str, set] = defaultdict(set)
    for telefon, kaynak, kimlik in db.execute(
        select(Musteri.telefon_e164, Musteri.dis_kaynak, Musteri.dis_kimlik)
        .where(Musteri.telefon_e164.in_(telefonlar), Musteri.silindi_at.is_(None))
    ):
        sahipler[telefon].add((kaynak, kimlik))
    sonuc = []
    for k in kayitlar:
        if k.telefon_e164 and sahipler[k.telefon_e164] - {(dis_kaynak, k.dis_kimlik)}:
            uyarilar["telefon_cakisma"] += 1
            k = replace(k, telefon_e164=None)
        sonuc.append(k)
    return sonuc


def _uyeleri_yaz(db: Session, h: Hazirlik, dis_kaynak: str, uyarilar: Counter) -> TurSonucu:
    kayitlar = _telefon_cakismalari(db, h.kayitlar, dis_kaynak, uyarilar)
    tablo = Musteri.__table__
    # Yalnızca dosyada olan alanlar güncellenir; --anonim'de yalnızca ad_soyad (K35).
    guncellenen = ["ad_soyad"] + [sutun for alan, sutun in (("telefon", "telefon_e164"), ("eposta", "eposta"))
                                  if alan in h.alanlar]
    sonuc = TurSonucu()
    for parca in _parcalar(kayitlar):
        ifade = insert(tablo).values([
            {"ad_soyad": k.ad_soyad, "telefon_e164": k.telefon_e164, "eposta": k.eposta, "kaynak": "csv",
             "dis_kaynak": dis_kaynak, "dis_kimlik": k.dis_kimlik}
            for k in parca
        ])
        ifade = ifade.on_conflict_do_update(
            index_elements=[tablo.c.isletme_id, tablo.c.dis_kaynak, tablo.c.dis_kimlik],
            index_where=tablo.c.dis_kimlik.isnot(None),
            set_={s: ifade.excluded[s] for s in guncellenen},
            where=or_(*(tablo.c[s].is_distinct_from(ifade.excluded[s]) for s in guncellenen)),
        ).returning(_xmax_sifir())
        _upsert_say(db, ifade, len(parca), sonuc)
    return sonuc


def _paketleri_yaz(db: Session, h: Hazirlik, dis_kaynak: str, uyeler: dict[str, uuid.UUID]) -> TurSonucu:
    tablo = MusteriPaketi.__table__
    mevcut = db.execute(
        select(MusteriPaketi.dis_kimlik, MusteriPaketi.paket_id, MusteriPaketi.musteri_id,
               MusteriPaketi.baslangic_tarihi)
        .where(MusteriPaketi.dis_kaynak == dis_kaynak)
        .order_by(MusteriPaketi.baslangic_tarihi, MusteriPaketi.olusturma_zamani, MusteriPaketi.paket_id)
    ).all()
    # Yeni paketin kimliği istemcide üretilir: aynı işlemde zincir (onceki_paket_id) kurulabilsin.
    paket_idleri = {p.dis_kimlik: p.paket_id for p in mevcut}
    uye_paketleri: dict[uuid.UUID, list] = defaultdict(list)          # başlangıca göre sıralı
    for p in mevcut:
        uye_paketleri[p.musteri_id].append(p)

    satirlar = []
    for k in sorted(h.kayitlar, key=lambda k: (k.baslangic_tarihi, k.satir)):   # öncül her zaman önce yazılır
        if k.uye_kimlik not in uyeler:
            raise IceAktarmaHatasi(f"satır {k.satir}, uye_kimlik: üye bulunamadı")
        musteri_id = uyeler[k.uye_kimlik]
        paket_id = paket_idleri.setdefault(k.dis_kimlik, uuid.uuid4())
        if k.onceki_dis_kimlik is not None:
            onceki = paket_idleri[k.onceki_dis_kimlik]
        else:
            oncekiler = [p.paket_id for p in uye_paketleri[musteri_id] if p.baslangic_tarihi < k.baslangic_tarihi]
            onceki = oncekiler[-1] if oncekiler else None
        satirlar.append({
            "paket_id": paket_id, "musteri_id": musteri_id, "tur": k.tur, "ad": k.ad,
            "baslangic_tarihi": k.baslangic_tarihi, "bitis_tarihi": k.bitis_tarihi, "giris_hakki": k.giris_hakki,
            "ucret": k.ucret, "durum": k.durum, "onceki_paket_id": onceki,
            "dis_kaynak": dis_kaynak, "dis_kimlik": k.dis_kimlik,
        })

    sonuc = TurSonucu()
    for parca in _parcalar(satirlar):
        ifade = insert(tablo).values(parca)
        yeni = {s: ifade.excluded[s] for s in ("ad", "bitis_tarihi", "giris_hakki", "ucret", "durum")}
        yeni["onceki_paket_id"] = func.coalesce(ifade.excluded.onceki_paket_id, tablo.c.onceki_paket_id)
        ifade = ifade.on_conflict_do_update(
            index_elements=[tablo.c.isletme_id, tablo.c.dis_kaynak, tablo.c.dis_kimlik],
            index_where=tablo.c.dis_kimlik.isnot(None),
            set_=yeni,
            where=or_(*(tablo.c[s].is_distinct_from(deger) for s, deger in yeni.items())),
        ).returning(_xmax_sifir())
        _upsert_say(db, ifade, len(parca), sonuc)
    return sonuc


def _girisleri_yaz(db: Session, h: Hazirlik, dis_kaynak: str, uyeler: dict[str, uuid.UUID]) -> TurSonucu:
    tablo = Ziyaret.__table__
    satirlar = []
    for k in h.kayitlar:
        if k.uye_kimlik not in uyeler:
            raise IceAktarmaHatasi(f"satır {k.satir}, uye_kimlik: üye bulunamadı")
        satirlar.append({
            "musteri_id": uyeler[k.uye_kimlik], "ziyaret_zamani": k.ziyaret_zamani, "durum": k.durum,
            "toplam_tutar": k.toplam_tutar, "kaynak": "csv", "dis_kaynak": dis_kaynak, "dis_kimlik": k.dis_kimlik,
        })
    sonuc = TurSonucu()
    for parca in _parcalar(satirlar):
        ifade = insert(tablo).values(parca).on_conflict_do_nothing(       # Adım 4a: giriş zamanı/tutarı değişmez
            index_elements=[tablo.c.isletme_id, tablo.c.dis_kaynak, tablo.c.dis_kimlik],
            index_where=tablo.c.dis_kimlik.isnot(None),
        ).returning(tablo.c.ziyaret_id)
        eklenen = len(db.execute(ifade).all())
        sonuc.eklenen += eklenen
        sonuc.atlanan += len(parca) - eklenen
    return sonuc
