from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from bagimliliklar import get_db
from rotalar import hizmetler, musteriler, paketler, panel, ziyaretler

app = FastAPI(title="Panosu SaaS API")
app.include_router(musteriler.router)
app.include_router(hizmetler.router)
app.include_router(ziyaretler.router)
app.include_router(paketler.router)
app.include_router(panel.router)


@app.get("/")
def anasayfa():
    return {"mesaj": "Panosu API sistemine başarıyla bağlandınız!"}


@app.get("/saglik")
def saglik(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"durum": "ok"}
