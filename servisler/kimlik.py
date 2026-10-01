"""Kimlik altyapısı (Adım 8, Bölüm 2): parola, tokenlar, kayıt, giriş, oturum, davet. FastAPI'ye bağımlı değildir.

- Parola: Argon2id (argon2-cffi varsayılanları: RFC 9106 düşük bellek profili, 64 MiB, 3 geçiş, 4 paralel).
  Düz parola veritabanına hiç gitmez; özet burada hesaplanır.
- Erişim tokenı: JWT HS256, 15 dk; alanlar sub, isl (seçili işletme, isteğe bağlı), typ="erisim", iat, exp.
- Yenileme tokenı: 256 bit rastgele, veritabanında yalnızca SHA-256 özeti; tek kullanımlık (oturum_yenile).
- Davet kodu: 128 bit rastgele, yalnızca SHA-256 özeti saklanır.
Parola özetleri ve oturumlar tablolarına panosu_app doğrudan erişemez; tüm işlemler SECURITY DEFINER fonksiyonlarıyla.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import ayarlar
from models import Isletme, Kullanici, Uyelik

ALGORITMA = "HS256"
ERISIM_TURU = "erisim"
PAROLA_EN_AZ, PAROLA_EN_COK = 10, 128
EPOSTA_TEKIL_KISITI = "kullanicilar_eposta_key"
_TEKILLIK_IHLALI = "23505"

_ph = PasswordHasher()


class GirisHatali(Exception):
    """E-posta yok, parola yanlış veya hesap kilitli: hepsi aynı yanıt (401)."""


class TokenGecersiz(Exception):
    pass


class EpostaKayitli(Exception):
    pass


class DavetGecersiz(Exception):
    """Geçersiz / süresi geçmiş / kullanılmış / iptal edilmiş davet: tek tip (404)."""


class ZatenUye(Exception):
    pass


class UyeDegil(Exception):
    pass


# ---------------------------------------------------------------------------------------------
# Parola
# ---------------------------------------------------------------------------------------------
def parola_kurali_hatasi(parola: str, eposta: str | None = None) -> str | None:
    """NIST SP 800-63B: 10–128 karakter, karakter sınıfı zorunluluğu yok; e-postanın kendisi parola olamaz."""
    if not PAROLA_EN_AZ <= len(parola) <= PAROLA_EN_COK:
        return f"Parola {PAROLA_EN_AZ}–{PAROLA_EN_COK} karakter olmalı"
    if eposta and parola.strip().casefold() == eposta.strip().casefold():
        return "Parola e-posta adresiyle aynı olamaz"
    return None


def parola_ozetle(parola: str) -> str:
    return _ph.hash(parola)


@lru_cache(maxsize=1)
def _sahte_ozet() -> str:
    """Olmayan e-posta / kilitli hesapta da aynı maliyetli doğrulama yapılsın diye (zamanlama eşitliği)."""
    return _ph.hash(secrets.token_urlsafe(32))


def _dogrula(ozet: str, parola: str) -> bool:
    try:
        return _ph.verify(ozet, parola)
    except (VerificationError, InvalidHashError):
        return False


# ---------------------------------------------------------------------------------------------
# Tokenlar
# ---------------------------------------------------------------------------------------------
def ozet(deger: str) -> bytes:
    """Yenileme tokenı ve davet kodu için SHA-256 (yüksek entropili değerlerde yavaş özete gerek yok)."""
    return hashlib.sha256(deger.encode()).digest()


def _anahtar() -> str:
    return ayarlar.jwt_gizli.get_secret_value()


def erisim_tokeni_uret(kullanici_id: uuid.UUID, isletme_id: uuid.UUID | None) -> str:
    simdi = datetime.now(timezone.utc)
    yuk = {"sub": str(kullanici_id), "typ": ERISIM_TURU, "iat": simdi,
           "exp": simdi + timedelta(minutes=ayarlar.erisim_suresi_dk)}
    if isletme_id is not None:
        yuk["isl"] = str(isletme_id)
    return jwt.encode(yuk, _anahtar(), algorithm=ALGORITMA)


def erisim_tokeni_coz(token: str) -> tuple[uuid.UUID, uuid.UUID | None]:
    """(kullanici_id, isletme_id | None). Algoritma sabit (alg=none ve algoritma karışıklığı reddedilir)."""
    try:
        yuk = jwt.decode(token, _anahtar(), algorithms=[ALGORITMA], options={"require": ["exp", "iat", "sub", "typ"]})
        if yuk["typ"] != ERISIM_TURU:
            raise TokenGecersiz("Token türü geçersiz")
        isl = yuk.get("isl")
        return uuid.UUID(yuk["sub"]), (uuid.UUID(isl) if isl else None)
    except (jwt.PyJWTError, ValueError, TypeError) as e:
        raise TokenGecersiz(str(e)) from e


@dataclass
class TokenCifti:
    erisim_tokeni: str
    yenileme_tokeni: str
    isletme_id: uuid.UUID | None
    erisim_bitis_sn: int = field(default_factory=lambda: ayarlar.erisim_suresi_dk * 60)
    token_turu: str = "bearer"


def _yenileme_suresi() -> timedelta:
    return timedelta(days=ayarlar.yenileme_suresi_gun)


def _oturum_ac(db: Session, kullanici_id: uuid.UUID, isletme_id: uuid.UUID | None) -> TokenCifti:
    yenileme = secrets.token_urlsafe(32)
    db.execute(text("SELECT oturum_ac(:k, :o, :i, :s)"),
               {"k": kullanici_id, "o": ozet(yenileme), "i": isletme_id, "s": _yenileme_suresi()})
    return TokenCifti(erisim_tokeni_uret(kullanici_id, isletme_id), yenileme, isletme_id)


# ---------------------------------------------------------------------------------------------
# Kayıt ve giriş
# ---------------------------------------------------------------------------------------------
def _kullanici_kaydet(db: Session, eposta: str, ad_soyad: str, parola: str) -> uuid.UUID:
    try:
        with db.begin_nested():
            return db.scalar(text("SELECT kullanici_kaydet(:e, :a, :o)"),
                             {"e": eposta, "a": ad_soyad, "o": parola_ozetle(parola)})
    except IntegrityError as e:
        if getattr(e.orig, "pgcode", None) == _TEKILLIK_IHLALI and \
                getattr(getattr(e.orig, "diag", None), "constraint_name", None) == EPOSTA_TEKIL_KISITI:
            raise EpostaKayitli(eposta) from e
        raise


def kayit(db: Session, eposta: str, ad_soyad: str, parola: str, isletme_adi: str, sektor: str | None) -> TokenCifti:
    """Tek işlemde: kullanıcı + parola özeti + işletme + sahip üyeliği + ücretsiz abonelik + oturum."""
    try:
        kullanici_id = _kullanici_kaydet(db, eposta, ad_soyad, parola)
        isletme_id = db.scalar(text("SELECT isletme_olustur(:ad, :k, :s)"),
                               {"ad": isletme_adi, "k": kullanici_id, "s": sektor})
        cift = _oturum_ac(db, kullanici_id, isletme_id)
        db.commit()
        return cift
    except Exception:
        db.rollback()
        raise


def davetle_kayit(db: Session, kod: str, eposta: str, ad_soyad: str, parola: str) -> TokenCifti:
    """Davet koduyla: kullanıcı + üyelik (davetteki rol) + oturum. Geçersiz davette hiçbir şey yazılmaz."""
    try:
        kullanici_id = _kullanici_kaydet(db, eposta, ad_soyad, parola)
        satir = db.execute(text("SELECT isletme_id, rol FROM davet_kabul(:o, :k)"),
                           {"o": ozet(kod), "k": kullanici_id}).first()
        if satir is None:
            raise DavetGecersiz()
        cift = _oturum_ac(db, kullanici_id, satir.isletme_id)
        db.commit()
        return cift
    except Exception:
        db.rollback()
        raise


def giris(db: Session, eposta: str, parola: str) -> uuid.UUID:
    """Doğrulanmış kullanici_id; aksi hâlde GirisHatali (tek tip). Başarısız deneme sayacı her durumda commit edilir."""
    satir = db.execute(text("SELECT kullanici_id, parola_ozeti, kilit_bitis FROM giris_bilgisi(:e)"),
                       {"e": eposta}).first()
    if satir is None:
        _dogrula(_sahte_ozet(), parola)
        db.rollback()
        raise GirisHatali()
    if satir.kilit_bitis is not None and satir.kilit_bitis > datetime.now(timezone.utc):
        _dogrula(satir.parola_ozeti, parola)          # aynı süre; sonuç kullanılmaz, deneme sayılmaz
        db.rollback()
        raise GirisHatali()
    basarili = _dogrula(satir.parola_ozeti, parola)
    db.execute(text("SELECT giris_sonucu_yaz(:k, :b)"), {"k": satir.kullanici_id, "b": basarili})
    if basarili and _ph.check_needs_rehash(satir.parola_ozeti):
        db.execute(text("SELECT parola_ozeti_guncelle(:k, :o)"),
                   {"k": satir.kullanici_id, "o": parola_ozetle(parola)})
    db.commit()
    if not basarili:
        raise GirisHatali()
    return satir.kullanici_id


@dataclass
class UyelikBilgisi:
    isletme_id: uuid.UUID
    isletme_adi: str
    rol: str


def uyelikler(db: Session, kullanici_id: uuid.UUID) -> list[UyelikBilgisi]:
    """Kullanıcının üyelikleri. Oturumda app.kullanici_id ayarlı olmalı (uyelik_okuma / isletme_erisim politikaları)."""
    satirlar = db.execute(
        select(Uyelik.isletme_id, Isletme.ad, Uyelik.rol)
        .join(Isletme, Isletme.isletme_id == Uyelik.isletme_id)
        .where(Uyelik.kullanici_id == kullanici_id)
        .order_by(Isletme.ad)
    ).all()
    return [UyelikBilgisi(i, ad, rol) for i, ad, rol in satirlar]


def giris_oturumu(db: Session, kullanici_id: uuid.UUID) -> tuple[TokenCifti, list[UyelikBilgisi]]:
    """Tek üyelik varsa o işletme seçili; 0 veya birden fazlaysa seçimsiz. db.info'da kullanici_id ayarlı olmalı."""
    liste = uyelikler(db, kullanici_id)
    secili = liste[0].isletme_id if len(liste) == 1 else None
    cift = _oturum_ac(db, kullanici_id, secili)
    db.commit()
    return cift, liste


def kullanici_bilgisi(db: Session, kullanici_id: uuid.UUID) -> Kullanici:
    return db.get(Kullanici, kullanici_id)


# ---------------------------------------------------------------------------------------------
# Oturum
# ---------------------------------------------------------------------------------------------
def oturum_yenile(db: Session, yenileme_tokeni: str) -> TokenCifti:
    yeni = secrets.token_urlsafe(32)
    satir = db.execute(text("SELECT kullanici_id, secili_isletme_id FROM oturum_yenile(:e, :y, :s)"),
                       {"e": ozet(yenileme_tokeni), "y": ozet(yeni), "s": _yenileme_suresi()}).first()
    db.commit()                       # boş sonuçta da: yeniden kullanımda yapılan aile iptali kalıcı olmalı
    if satir is None:
        raise TokenGecersiz("Yenileme tokenı geçersiz")
    return TokenCifti(erisim_tokeni_uret(satir.kullanici_id, satir.secili_isletme_id), yeni, satir.secili_isletme_id)


def oturum_kapat(db: Session, yenileme_tokeni: str) -> None:
    db.execute(text("SELECT oturum_kapat(:o)"), {"o": ozet(yenileme_tokeni)})
    db.commit()


def isletme_sec(db: Session, kullanici_id: uuid.UUID, isletme_id: uuid.UUID, yenileme_tokeni: str) -> TokenCifti:
    """Üyelik doğrulanır (istemcinin önerdiği isletme_id doğrulanmadan kullanılmaz), seçim oturuma yazılır."""
    uye = db.scalar(select(func.count()).select_from(Uyelik)
                    .where(Uyelik.kullanici_id == kullanici_id, Uyelik.isletme_id == isletme_id))
    if not uye:
        db.rollback()
        raise UyeDegil()
    try:
        with db.begin_nested():
            db.execute(text("SELECT oturum_isletme_degistir(:o, :i)"), {"o": ozet(yenileme_tokeni), "i": isletme_id})
    except Exception as e:
        db.rollback()
        kod = getattr(getattr(e, "orig", None), "pgcode", None)
        if kod == "42501":
            raise UyeDegil() from e
        raise TokenGecersiz("Yenileme tokenı geçersiz") from e
    db.commit()
    return TokenCifti(erisim_tokeni_uret(kullanici_id, isletme_id), yenileme_tokeni, isletme_id)


# ---------------------------------------------------------------------------------------------
# Davet
# ---------------------------------------------------------------------------------------------
def davet_kodu_uret() -> str:
    return secrets.token_urlsafe(16)


def davet_kabul(db: Session, kod: str, kullanici_id: uuid.UUID) -> UyelikBilgisi:
    try:
        with db.begin_nested():
            satir = db.execute(text("SELECT isletme_id, rol FROM davet_kabul(:o, :k)"),
                               {"o": ozet(kod), "k": kullanici_id}).first()
    except IntegrityError as e:
        db.rollback()
        if getattr(e.orig, "pgcode", None) == _TEKILLIK_IHLALI:
            raise ZatenUye() from e
        raise
    if satir is None:
        db.rollback()
        raise DavetGecersiz()
    db.commit()
    isletme = db.get(Isletme, satir.isletme_id)          # artık üyesi: isletme_erisim politikası gösterir
    return UyelikBilgisi(satir.isletme_id, isletme.ad if isletme else "", satir.rol)
