"""Ara katman (Adım 11; `docs/adim-11-tasarim.md`): salt okunur demo (K25) ve üretim güvenlik başlıkları (K27).

Ayarlar her istekte okunur (import anında değil): testler ayarları monkeypatch ile değiştirebilir.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from config import ayarlar

SALT_OKUNUR_MESAJI = "Bu demo salt okunur; veri değiştirilemez."
GUVENLI_YONTEMLER = frozenset({"GET", "HEAD", "OPTIONS"})
# Salt okunur modda yazmaya açık uçlar: yalnızca oturum açma/kapama ve işletme seçimi. Tam eşitlik; sondaki "/" farkı
# serbest bırakılmaz.
SALT_OKUNUR_IZINLI_YOLLAR = frozenset({
    "/giris", "/cikis", "/isletme",
    "/oturum/giris", "/oturum/yenile", "/oturum/cikis", "/oturum/isletme-sec",
})
URETIM_BASLIKLARI = {
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}


def yazma_izinli_mi(yontem: str, yol: str) -> bool:
    """K25: salt okunur modda bu istek geçebilir mi?"""
    return yontem.upper() in GUVENLI_YONTEMLER or yol in SALT_OKUNUR_IZINLI_YOLLAR


async def _ara_katman(request: Request, sonraki: RequestResponseEndpoint) -> Response:
    if ayarlar.salt_okunur and not yazma_izinli_mi(request.method, request.url.path):
        yanit: Response = JSONResponse({"detail": SALT_OKUNUR_MESAJI}, status_code=status.HTTP_403_FORBIDDEN)
    else:
        yanit = await sonraki(request)
    if ayarlar.ortam == "uretim":
        yanit.headers.update(URETIM_BASLIKLARI)
    return yanit


def kaydet(app: FastAPI) -> None:
    app.add_middleware(BaseHTTPMiddleware, dispatch=_ara_katman)
