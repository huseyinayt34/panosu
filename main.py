from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from bagimliliklar import get_db
from rotalar import ara_katman, davetler, giderler, hizmetler, kimlik, musteriler, paketler, panel, rapor, web, ziyaretler

app = FastAPI(title="Ritmeva API")
ara_katman.kaydet(app)                            # salt okunur demo (K25), üretim başlıkları (K27)
app.include_router(kimlik.router)
app.include_router(davetler.router)
app.include_router(davetler.uye_router)
app.include_router(musteriler.router)
app.include_router(hizmetler.router)
app.include_router(ziyaretler.router)
app.include_router(paketler.router)
app.include_router(panel.router)
app.include_router(giderler.router)
app.include_router(rapor.router)
app.include_router(web.router)
app.add_exception_handler(web.WebKesinti, web.web_kesinti_isleyici)
app.mount("/statik", StaticFiles(directory=web.STATIK_DIZINI), name="statik")


@app.get("/saglik")
def saglik(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"durum": "ok"}
