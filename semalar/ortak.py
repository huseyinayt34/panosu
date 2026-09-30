"""Şemalar arasında paylaşılan tipler ve taban sınıflar."""

from decimal import Decimal
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

# NUMERIC(12,2) ile uyumlu, negatif olmayan para tutarı
Para = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class KismiGuncelleme(BaseModel):
    """PATCH gövdeleri için taban: fazla alan yasak, boş gövde yasak, NULL_OLAMAZ alanlarına null yasak.

    Servisler yalnızca model_dump(exclude_unset=True) alanlarını uygular.
    """
    model_config = ConfigDict(extra="forbid")

    NULL_OLAMAZ: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def _kismi_guncelleme_kurallari(self):
        if not self.model_fields_set:
            raise ValueError("Güncellenecek en az bir alan gönderilmelidir")
        for alan in self.NULL_OLAMAZ:
            if alan in self.model_fields_set and getattr(self, alan) is None:
                raise ValueError(f"{alan} boş (null) olamaz")
        return self
