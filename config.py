"""Uygulama ayarları. Değerler ortam değişkeninden veya .env dosyasından okunur (koda GÖMÜLMEZ)."""

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

JWT_GIZLI_EN_AZ_BAYT = 32


class Ayarlar(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PANOSU_", extra="ignore")

    # Örn: postgresql+psycopg2://panosu_app:PAROLA@localhost:5432/panosu
    veritabani_url: str
    # "gelistirme" | "uretim"
    ortam: str = "gelistirme"
    # Yalnızca Alembic kullanır: DDL yetkili rol (örn. postgres). Uygulama bu URL'yi ASLA kullanmaz.
    migrasyon_url: str | None = None

    # Erişim tokenı (JWT, HS256) imza anahtarı. Yoksa veya kısaysa uygulama AÇILMAZ. Hiçbir çıktıda görünmez.
    # Üretmek için: python -c "import secrets; print(secrets.token_urlsafe(32))"
    jwt_gizli: SecretStr
    erisim_suresi_dk: int = 15
    yenileme_suresi_gun: int = 30
    # Açık kayıt (POST /kayit). Üretimde kapalı; pilot işletmeler komutla açılır (K5).
    acik_kayit: bool = False

    @field_validator("jwt_gizli")
    @classmethod
    def _jwt_gizli_yeterli(cls, deger: SecretStr) -> SecretStr:
        if len(deger.get_secret_value().encode()) < JWT_GIZLI_EN_AZ_BAYT:
            raise ValueError(f"PANOSU_JWT_GIZLI en az {JWT_GIZLI_EN_AZ_BAYT} bayt olmalı")
        return deger


ayarlar = Ayarlar()
