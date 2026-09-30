from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from bagimliliklar import get_db
from rotalar import musteriler

app = FastAPI(title="Panosu SaaS API")
app.include_router(musteriler.router)


@app.get("/")
def anasayfa():
    return {"mesaj": "Panosu API sistemine başarıyla bağlandınız!"}


@app.get("/saglik")
def saglik(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"durum": "ok"}
