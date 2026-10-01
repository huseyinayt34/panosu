"""Kimlik uçları: kayıt, giriş, oturum yenileme/çıkış, işletme seçimi, /ben. Servis istisnaları burada HTTP'ye çevrilir."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from bagimliliklar import Kimlik, get_db, kimlik_dogrula, kullanici_db
from config import ayarlar
from semalar.kimlik import (
    BenYanit, DavetliKayitIstegi, GirisIstegi, GirisYanit, IsletmeSecIstegi, KayitIstegi, TokenCiftiYanit,
    UyelikYanit, YenilemeIstegi,
)
from servisler import kimlik as servis
from servisler.kimlik import DavetGecersiz, EpostaKayitli, GirisHatali, TokenGecersiz, UyeDegil

router = APIRouter(tags=["Kimlik"])

_GIRIS_HATALI = "E-posta veya parola hatalı"
_EPOSTA_KAYITLI = "Bu e-posta ile kayıtlı bir hesap var"
_DAVET_GECERSIZ = "Davet bulunamadı"


def _yetkisiz(mesaj: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, mesaj, headers={"WWW-Authenticate": "Bearer"})


def _cift(c: servis.TokenCifti) -> TokenCiftiYanit:
    return TokenCiftiYanit.model_validate(c)


@router.post("/kayit", response_model=TokenCiftiYanit, status_code=status.HTTP_201_CREATED,
             responses={404: {"description": "Açık kayıt kapalı"}, 409: {"description": _EPOSTA_KAYITLI}})
def kayit(veri: KayitIstegi, db: Session = Depends(get_db)):
    """Yeni kullanıcı + işletme (sahip, ücretsiz abonelik). Yalnızca açık kayıt etkinken."""
    if not ayarlar.acik_kayit:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    try:
        return _cift(servis.kayit(db, veri.eposta, veri.ad_soyad, veri.parola, veri.isletme_adi, veri.sektor))
    except EpostaKayitli:
        raise HTTPException(status.HTTP_409_CONFLICT, _EPOSTA_KAYITLI)


@router.post("/kayit/davet", response_model=TokenCiftiYanit, status_code=status.HTTP_201_CREATED,
             responses={404: {"description": _DAVET_GECERSIZ}, 409: {"description": _EPOSTA_KAYITLI}})
def davetle_kayit(veri: DavetliKayitIstegi, db: Session = Depends(get_db)):
    """Davet koduyla hesap açma (açık kayıttan bağımsız); kullanıcı davetteki rolle üye olur."""
    try:
        return _cift(servis.davetle_kayit(db, veri.kod, veri.eposta, veri.ad_soyad, veri.parola))
    except EpostaKayitli:
        raise HTTPException(status.HTTP_409_CONFLICT, _EPOSTA_KAYITLI)
    except DavetGecersiz:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _DAVET_GECERSIZ)


@router.post("/oturum/giris", response_model=GirisYanit, responses={401: {"description": _GIRIS_HATALI}})
def giris(veri: GirisIstegi, db: Session = Depends(get_db)):
    """Tek üyelik varsa o işletme seçili gelir; 0 veya birden fazlaysa isletme_id boş, üyelik listesi yanıtta."""
    try:
        kullanici_id = servis.giris(db, veri.eposta, veri.parola)
    except GirisHatali:
        raise _yetkisiz(_GIRIS_HATALI)
    db.info["kullanici_id"] = kullanici_id               # sonraki işlemde app.kullanici_id ayarlanır
    cift, uyelikler = servis.giris_oturumu(db, kullanici_id)
    return GirisYanit(**_cift(cift).model_dump(), uyelikler=[UyelikYanit.model_validate(u) for u in uyelikler])


@router.post("/oturum/yenile", response_model=TokenCiftiYanit, responses={401: {"description": "Geçersiz token"}})
def yenile(veri: YenilemeIstegi, db: Session = Depends(get_db)):
    """Yeni token çifti; eski yenileme tokenı bir daha kullanılamaz (tekrar gelirse oturum ailesi iptal edilir)."""
    try:
        return _cift(servis.oturum_yenile(db, veri.yenileme_tokeni))
    except TokenGecersiz:
        raise _yetkisiz("Geçersiz veya süresi dolmuş yenileme tokenı")


@router.post("/oturum/cikis", status_code=status.HTTP_204_NO_CONTENT)
def cikis(veri: YenilemeIstegi, db: Session = Depends(get_db)) -> Response:
    """Oturum ailesinin tamamını iptal eder."""
    servis.oturum_kapat(db, veri.yenileme_tokeni)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/oturum/isletme-sec", response_model=TokenCiftiYanit,
             responses={401: {"description": "Geçersiz token"}, 403: {"description": "Bu işletmenin üyesi değilsiniz"}})
def isletme_sec(veri: IsletmeSecIstegi, kimlik: Kimlik = Depends(kimlik_dogrula), db: Session = Depends(kullanici_db)):
    """Üyelik doğrulanır, seçim yenileme oturumuna da yazılır, yeni erişim tokenı imzalanır (yenileme tokenı aynı kalır)."""
    try:
        return _cift(servis.isletme_sec(db, kimlik.kullanici_id, veri.isletme_id, veri.yenileme_tokeni))
    except UyeDegil:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu işletmenin üyesi değilsiniz")
    except TokenGecersiz:
        raise _yetkisiz("Geçersiz veya süresi dolmuş yenileme tokenı")


@router.get("/ben", response_model=BenYanit)
def ben(kimlik: Kimlik = Depends(kimlik_dogrula), db: Session = Depends(kullanici_db)):
    kullanici = servis.kullanici_bilgisi(db, kimlik.kullanici_id)
    if kullanici is None:
        raise _yetkisiz("Kullanıcı bulunamadı")
    return BenYanit(kullanici_id=kullanici.kullanici_id, eposta=kullanici.eposta, ad_soyad=kullanici.ad_soyad,
                    son_giris_zamani=kullanici.son_giris_zamani,
                    uyelikler=[UyelikYanit.model_validate(u) for u in servis.uyelikler(db, kimlik.kullanici_id)])
