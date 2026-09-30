"""Servisler arasında paylaşılan yardımcılar."""

from collections.abc import Mapping

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

_TEKILLIK_IHLALI = "23505"


def kaydet(db: Session, tekillik_hatalari: Mapping[str, type[Exception]] | None = None) -> None:
    """Commit eder. Tekillik ihlalinde kısıt adına karşılık gelen servis istisnasını fırlatır.

    Kısıt adı e.orig.diag.constraint_name'den okunur; eşleşmeyen her hata olduğu gibi yeniden fırlatılır.
    """
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        if getattr(e.orig, "pgcode", None) == _TEKILLIK_IHLALI and tekillik_hatalari:
            kisit = getattr(getattr(e.orig, "diag", None), "constraint_name", None)
            if kisit in tekillik_hatalari:
                raise tekillik_hatalari[kisit] from e
        raise
