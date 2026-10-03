"""Web paneli (Adım 9a): HTML uçları, çerezli oturum ve CSRF. Servis istisnaları burada HTTP'ye çevrilir.

Oturum (K3, `docs/adim-9-tasarim.md`): erişim ve yenileme tokenları httpOnly + SameSite=Lax çerezlerde (Secure yalnızca
ortam=uretim). Durum değiştiren her istekte CSRF tokenı çift gönderimle denetlenir (çerez + form alanı "csrf" veya
X-CSRF-Token başlığı). Yenileme yalnızca tam sayfa GET isteğinde yapılır: yenileme tokenı tek kullanımlık olduğundan iki
paralel HTMX isteği aynı tokenı yenilemeye çalışırsa ikincisi "yeniden kullanım" sayılır ve oturum ailesi iptal olur;
bu yüzden HTMX parça isteğinde erişim çerezi geçersizse 401 + "HX-Refresh: true" döner.

FastAPI'de doğrudan Response döndürüldüğünde enjekte edilen Response'un çerezleri kaybolur: çerezler her zaman
döndürülen yanıta yazılır.
"""

import re
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analitik.aciklama import AYRISTIRMA_MIN_P_AKTIF
from bagimliliklar import Kimlik, get_db, kiraci_oturumu, token_kimligi
from config import ayarlar
from database import SessionLocal
from models import Isletme
from rotalar.kimlik import _GIRIS_HATALI
from semalar.gider import AY_DESENI, ay_coz
from semalar.kimlik import GirisIstegi
from servisler import bicim, finans_servisi, rapor_servisi, risk_listeleri
from servisler import kimlik as servis
from servisler.kimlik import GirisHatali, TokenCifti, TokenGecersiz, UyeDegil
from servisler.yenileme_servisi import isletme_bugun

router = APIRouter(include_in_schema=False)

ERISIM_CEREZI = "panosu_erisim"
YENILEME_CEREZI = "panosu_yenileme"
CSRF_CEREZI = "panosu_csrf"
CSRF_ALANI = "csrf"
CSRF_BASLIGI = "X-CSRF-Token"
FINANS_ROLLERI = ("sahip", "yonetici")
AY_SECICI_AY = 12                                       # içinde bulunulan ay dahil

KOK_DIZIN = Path(__file__).resolve().parent.parent
STATIK_DIZINI = KOK_DIZIN / "statik"

sablonlar = Jinja2Templates(directory=KOK_DIZIN / "sablonlar")   # otomatik kaçış açık (Starlette varsayılanı)
sablonlar.env.globals.update(para=bicim.para, tarih=bicim.tarih, ay_adi=bicim.ay_adi, yuzde=bicim.yuzde,
                             ondalik=bicim.ondalik, olasilik=bicim.olasilik, telefon=bicim.telefon,
                             AYRISTIRMA_MIN_P_AKTIF=AYRISTIRMA_MIN_P_AKTIF)


@dataclass
class WebOturumu:
    kimlik: Kimlik
    yeni_cift: TokenCifti | None = None        # tam sayfa GET'te yenilendiyse yanıta çerez olarak yazılır


class WebKesinti(Exception):
    """Bağımlılıktan hazır bir yanıtla çıkış (yönlendirme, 401 HX-Refresh, 403). main.py'de işleyicisi var."""

    def __init__(self, yanit: Response):
        self.yanit = yanit


def web_kesinti_isleyici(_request: Request, hata: WebKesinti) -> Response:
    return hata.yanit


# ---------------------------------------------------------------------------------------------
# Çerezler ve yanıtlar
# ---------------------------------------------------------------------------------------------
def _cerez_nitelikleri() -> dict:
    return {"httponly": True, "samesite": "lax", "path": "/", "secure": ayarlar.ortam == "uretim"}


def _onbelleksiz(yanit: Response) -> Response:
    yanit.headers["Cache-Control"] = "no-store"           # finansal veri tarayıcı önbelleğinde kalmasın
    return yanit


def _erisim_cerezi_yaz(yanit: Response, erisim_tokeni: str) -> None:
    yanit.set_cookie(ERISIM_CEREZI, erisim_tokeni, max_age=ayarlar.erisim_suresi_dk * 60, **_cerez_nitelikleri())


def _cerezleri_yaz(yanit: Response, cift: TokenCifti) -> None:
    _erisim_cerezi_yaz(yanit, cift.erisim_tokeni)
    yanit.set_cookie(YENILEME_CEREZI, cift.yenileme_tokeni, max_age=ayarlar.yenileme_suresi_gun * 24 * 60 * 60,
                     **_cerez_nitelikleri())


def _csrf_yaz(yanit: Response, deger: str) -> None:
    yanit.set_cookie(CSRF_CEREZI, deger, **_cerez_nitelikleri())


def _cerezleri_sil(yanit: Response, csrf_dahil: bool = False) -> Response:
    adlar = (ERISIM_CEREZI, YENILEME_CEREZI) + ((CSRF_CEREZI,) if csrf_dahil else ())
    for ad in adlar:
        yanit.delete_cookie(ad, **_cerez_nitelikleri())
    return yanit


def _yonlendir(adres: str) -> Response:
    return _onbelleksiz(RedirectResponse(adres, status_code=status.HTTP_303_SEE_OTHER))


def _htmx_mi(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


def _sayfa(request: Request, sablon: str, baglam: dict | None = None, oturum: WebOturumu | None = None,
           durum: int = status.HTTP_200_OK) -> Response:
    """Şablonu işler; CSRF çerezi yoksa üretip yazar, oturum yenilendiyse yeni çerezleri yazar."""
    csrf = request.cookies.get(CSRF_CEREZI)
    yeni_csrf = csrf is None
    if yeni_csrf:
        csrf = secrets.token_urlsafe(32)
    yanit = sablonlar.TemplateResponse(request, sablon, {"csrf": csrf, **(baglam or {})}, status_code=durum)
    if yeni_csrf:
        _csrf_yaz(yanit, csrf)
    if oturum is not None and oturum.yeni_cift is not None:
        _cerezleri_yaz(yanit, oturum.yeni_cift)
    return _onbelleksiz(yanit)


def _demo_girisi() -> dict:
    """K26: iki demo değişkeni de tanımlıysa giriş formu demo hesabıyla dolu gelir; biri eksikse boş."""
    if not ayarlar.demo_giris_eposta or ayarlar.demo_giris_parola is None:
        return {}
    return {"demo_eposta": ayarlar.demo_giris_eposta, "demo_parola": ayarlar.demo_giris_parola.get_secret_value()}


def _mesaj_sayfasi(request: Request, mesaj: str, durum: int) -> Response:
    return _sayfa(request, "web/taban.html", {"mesaj": mesaj}, durum=durum)


# ---------------------------------------------------------------------------------------------
# Web kimliği ve CSRF
# ---------------------------------------------------------------------------------------------
def web_kimligi(request: Request, db: Session = Depends(get_db)) -> WebOturumu:
    """Erişim çerezinden Kimlik. Geçersizse: HTMX → 401 + HX-Refresh (yenileme yok); tam sayfa GET + yenileme çerezi →
    oturum yenilenir; diğer durumlar → 303 /giris."""
    erisim = request.cookies.get(ERISIM_CEREZI)
    if erisim:
        try:
            return WebOturumu(token_kimligi(erisim))
        except TokenGecersiz:
            pass
    if _htmx_mi(request):
        raise WebKesinti(_onbelleksiz(Response(status_code=status.HTTP_401_UNAUTHORIZED,
                                               headers={"HX-Refresh": "true"})))
    yenileme = request.cookies.get(YENILEME_CEREZI)
    if request.method == "GET" and yenileme:
        try:
            cift = servis.oturum_yenile(db, yenileme)
        except TokenGecersiz:
            raise WebKesinti(_cerezleri_sil(_yonlendir("/giris")))
        return WebOturumu(token_kimligi(cift.erisim_tokeni), cift)
    raise WebKesinti(_yonlendir("/giris"))


def _csrf_denetle(request: Request, form_degeri: str | None) -> None:
    cerez = request.cookies.get(CSRF_CEREZI)
    gelen = form_degeri or request.headers.get(CSRF_BASLIGI)
    if not cerez or not gelen or not secrets.compare_digest(cerez.encode(), gelen.encode()):
        raise WebKesinti(_mesaj_sayfasi(request, "Güvenlik doğrulaması başarısız. Sayfayı yenileyip tekrar deneyin.",
                                        status.HTTP_403_FORBIDDEN))


def _uyelikler(kimlik: Kimlik) -> list[servis.UyelikBilgisi]:
    with SessionLocal() as db:                       # yalnızca app.kullanici_id ayarlı (kullanici_db gibi)
        db.info["kullanici_id"] = kimlik.kullanici_id
        return servis.uyelikler(db, kimlik.kullanici_id)


def _ust_bilgi(db: Session, kimlik: Kimlik) -> dict:
    """taban.html başlık çubuğu: işletme adı ve üyelik sayısı (kiracı oturumunda, RLS ile)."""
    return {"oturum_acik": True,
            "isletme_adi": db.scalar(select(Isletme.ad).where(Isletme.isletme_id == func.aktif_isletme())),
            "uyelik_sayisi": len(servis.uyelikler(db, kimlik.kullanici_id))}


# ---------------------------------------------------------------------------------------------
# Uçlar
# ---------------------------------------------------------------------------------------------
@router.get("/")
def kok(request: Request) -> Response:
    """K53: public landing page. No session, no database, no cookie; the demo starts at /giris."""
    return sablonlar.TemplateResponse(request, "web/tanitim.html",
                                      {"pilot_takvim_adresi": ayarlar.pilot_takvim_adresi})


@router.get("/giris")
def giris_formu(request: Request, db: Session = Depends(get_db)):
    try:
        oturum = web_kimligi(request, db)
    except WebKesinti:
        return _cerezleri_sil(_sayfa(request, "web/giris.html", _demo_girisi()))
    yanit = _yonlendir("/pano")
    if oturum.yeni_cift is not None:
        _cerezleri_yaz(yanit, oturum.yeni_cift)
    return yanit


@router.post("/giris")
def giris_gonder(request: Request, eposta: Annotated[str, Form()] = "", parola: Annotated[str, Form()] = "",
                 csrf: Annotated[str, Form()] = "", db: Session = Depends(get_db)):
    _csrf_denetle(request, csrf)
    try:
        veri = GirisIstegi(eposta=eposta, parola=parola)
        kullanici_id = servis.giris(db, veri.eposta, veri.parola)
    except (ValidationError, GirisHatali):
        # Doğrulama hatası da yanlış parola da aynı genel mesaj; kullanıcının yazdığı parola asla geri basılmaz
        # (parola alanı yalnızca demo parolasıyla dolabilir, K26).
        return _sayfa(request, "web/giris.html", {**_demo_girisi(), "eposta": eposta, "hata": _GIRIS_HATALI},
                      durum=status.HTTP_401_UNAUTHORIZED)
    db.info["kullanici_id"] = kullanici_id               # sonraki işlemde app.kullanici_id ayarlanır
    cift, _ = servis.giris_oturumu(db, kullanici_id)
    yanit = _yonlendir("/pano" if cift.isletme_id is not None else "/isletme")
    _cerezleri_yaz(yanit, cift)
    _csrf_yaz(yanit, secrets.token_urlsafe(32))          # oturum sabitleme önlemi: girişte CSRF tokenı yenilenir
    return yanit


@router.get("/isletme")
def isletme_listesi(request: Request, oturum: WebOturumu = Depends(web_kimligi)):
    liste = _uyelikler(oturum.kimlik)
    secili = next((u for u in liste if u.isletme_id == oturum.kimlik.isletme_id), None)
    return _sayfa(request, "web/isletme_sec.html", {
        "oturum_acik": True, "uyelikler": liste, "secili_id": oturum.kimlik.isletme_id,
        "isletme_adi": secili.isletme_adi if secili else None, "uyelik_sayisi": len(liste),
    }, oturum=oturum)


@router.post("/isletme")
def isletme_sec(request: Request, isletme_id: Annotated[str, Form()] = "", csrf: Annotated[str, Form()] = "",
                oturum: WebOturumu = Depends(web_kimligi)):
    _csrf_denetle(request, csrf)
    yenileme = request.cookies.get(YENILEME_CEREZI)
    if not yenileme:
        return _cerezleri_sil(_yonlendir("/giris"))
    try:
        hedef = uuid.UUID(isletme_id)
    except ValueError:
        return _mesaj_sayfasi(request, "Bu işletmenin üyesi değilsiniz.", status.HTTP_403_FORBIDDEN)
    kimlik = oturum.kimlik
    with SessionLocal() as db:                       # yalnızca app.kullanici_id ayarlı (kullanici_db gibi)
        db.info["kullanici_id"] = kimlik.kullanici_id
        try:
            cift = servis.isletme_sec(db, kimlik.kullanici_id, hedef, yenileme)
        except UyeDegil:
            return _mesaj_sayfasi(request, "Bu işletmenin üyesi değilsiniz.", status.HTTP_403_FORBIDDEN)
        except TokenGecersiz:
            return _cerezleri_sil(_yonlendir("/giris"))
    yanit = _yonlendir("/pano")
    _erisim_cerezi_yaz(yanit, cift.erisim_tokeni)
    return yanit


@router.post("/cikis")
def cikis(request: Request, csrf: Annotated[str, Form()] = "", db: Session = Depends(get_db)):
    _csrf_denetle(request, csrf)
    yenileme = request.cookies.get(YENILEME_CEREZI)
    if yenileme:
        servis.oturum_kapat(db, yenileme)
    return _cerezleri_sil(_yonlendir("/giris"), csrf_dahil=True)


def _hedef_ay(ay: str | None, bugun: date) -> date:
    """?ay=YYYY-AA; yoksa, desene uymuyorsa veya içinde bulunulan aydan ileriyse içinde bulunulan ay."""
    bu_ay = bugun.replace(day=1)
    if not ay or not re.fullmatch(AY_DESENI, ay):
        return bu_ay
    return min(ay_coz(ay), bu_ay)


def _son_aylar(bu_ay: date) -> list[date]:
    aylar = [bu_ay]
    while len(aylar) < AY_SECICI_AY:
        aylar.append(finans_servisi.onceki_ay(aylar[-1]))
    return aylar


def _kiraci_sayfasi(request: Request, oturum: WebOturumu, sablon: str | None,
                    baglam_kur: Callable[[Session], dict]) -> tuple[Response, dict | None]:
    """Kiracı oturumu gerektiren pano yanıtlarının ortak gövdesi. İşletme seçilmemişse HTMX → 401 + HX-Refresh, tam
    sayfa → /isletme. Bağlam kiracı oturumunda kurulur; yanıtla birlikte döner (erken çıkışta None).
    sablon None ise bağlamın "html" alanı (hazır sayfa, ör. haftalık rapor) aynı çerez ve önbellek kurallarıyla döner."""
    if oturum.kimlik.isletme_id is None:
        if _htmx_mi(request):
            return _onbelleksiz(Response(status_code=status.HTTP_401_UNAUTHORIZED, headers={"HX-Refresh": "true"})), None
        yanit = _yonlendir("/isletme")
        if oturum.yeni_cift is not None:
            _cerezleri_yaz(yanit, oturum.yeni_cift)
        return yanit, None
    try:
        with kiraci_oturumu(oturum.kimlik) as db:
            baglam = baglam_kur(db)
    except HTTPException as h:
        return _sayfa(request, "web/taban.html", {"mesaj": h.detail}, oturum=oturum, durum=h.status_code), None
    if sablon is None:
        yanit = HTMLResponse(baglam["html"])
        if oturum.yeni_cift is not None:
            _cerezleri_yaz(yanit, oturum.yeni_cift)
        return _onbelleksiz(yanit), baglam
    return _sayfa(request, sablon, baglam, oturum=oturum), baglam


def _finans_baglami(db: Session, ay: str | None) -> dict:
    """Rol, seçili ay, finans özeti (yalnızca sahip/yönetici)."""
    bugun = isletme_bugun(db)
    hedef = _hedef_ay(ay, bugun)
    finans_gorur = db.info["rol"] in FINANS_ROLLERI
    return {"ay": hedef, "bugun": bugun, "finans_gorur": finans_gorur,
            "finans": finans_servisi.finans_ozeti(db, hedef) if finans_gorur else None}


@router.get("/pano")
def pano(request: Request, ay: str | None = None, riskli: str | None = None, sessiz: str | None = None,
         oturum: WebOturumu = Depends(web_kimligi)):
    """Finans kutuları + riskli ve sessiz üye tabloları (tablolar tüm rollere açık, seçili aydan bağımsız)."""
    def kur(db: Session) -> dict:
        baglam = _finans_baglami(db, ay)
        baglam.update(_ust_bilgi(db, oturum.kimlik), aylar=_son_aylar(baglam["bugun"].replace(day=1)),
                      riskli=risk_listeleri.riskli_uyeler(db, tumu=riskli == "tumu"),
                      sessiz=risk_listeleri.sessiz_uye_listesi(db, tumu=sessiz == "tumu"))
        return baglam
    return _kiraci_sayfasi(request, oturum, "web/pano.html", kur)[0]


@router.get("/pano/finans")
def pano_finans(request: Request, ay: str | None = None, oturum: WebOturumu = Depends(web_kimligi)):
    """Yalnızca finans parçası (HTMX ay seçici); risk tabloları hesaplanmaz."""
    yanit, baglam = _kiraci_sayfasi(request, oturum, "web/_finans.html", lambda db: _finans_baglami(db, ay))
    if baglam is not None and _htmx_mi(request):
        yanit.headers["HX-Push-Url"] = f"/pano?ay={baglam['ay']:%Y-%m}"   # adres çubuğunda parça değil sayfa adresi
    return yanit


@router.get("/pano/riskli")
def pano_riskli(request: Request, tumu: str | None = None, oturum: WebOturumu = Depends(web_kimligi)):
    """Yalnızca riskli üye tablosu parçası ("Tümünü göster")."""
    return _kiraci_sayfasi(request, oturum, "web/_riskli.html",
                           lambda db: {"riskli": risk_listeleri.riskli_uyeler(db, tumu=tumu == "1")})[0]


@router.get("/pano/sessiz")
def pano_sessiz(request: Request, tumu: str | None = None, oturum: WebOturumu = Depends(web_kimligi)):
    """Yalnızca sessiz üye tablosu parçası ("Tümünü göster")."""
    return _kiraci_sayfasi(request, oturum, "web/_sessiz.html",
                           lambda db: {"sessiz": risk_listeleri.sessiz_uye_listesi(db, tumu=tumu == "1")})[0]


@router.get("/pano/rapor")
def pano_rapor(request: Request, oturum: WebOturumu = Depends(web_kimligi)):
    """Haftalık rapor (K18): panelin yazdırılabilir hâli, yalnızca sahip ve yönetici. Panelde yeni sekmede açılır."""
    def kur(db: Session) -> dict:
        if db.info["rol"] not in FINANS_ROLLERI:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Haftalık rapor yalnızca işletme sahibi ve yöneticiye açıktır.")
        return {"html": rapor_servisi.haftalik_rapor(db)}
    return _kiraci_sayfasi(request, oturum, None, kur)[0]
