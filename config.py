"""Uygulama ayarları. Değerler ortam değişkeninden veya .env dosyasından okunur (koda GÖMÜLMEZ)."""

from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

JWT_GIZLI_EN_AZ_BAYT = 32
UYGULAMA_ROLU = "panosu_app"


class Ayarlar(BaseSettings):
    # hide_input_in_errors: doğrulama hatası girdi değerlerini (adres, parola) basmasın.
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PANOSU_", extra="ignore", hide_input_in_errors=True)

    # Örn: postgresql+psycopg2://panosu_app:PAROLA@localhost:5432/panosu
    veritabani_url: str
    # Üretimde (K22, `docs/adim-11-tasarim.md`) uygulama yalnızca panosu_app ile, migrasyon adresi ve açık kayıt
    # olmadan açılır.
    ortam: Literal["gelistirme", "uretim"] = "gelistirme"
    # Yalnızca Alembic kullanır: DDL yetkili rol (örn. postgres). Uygulama bu URL'yi ASLA kullanmaz.
    migrasyon_url: str | None = None

    # Erişim tokenı (JWT, HS256) imza anahtarı. Yoksa veya kısaysa uygulama AÇILMAZ. Hiçbir çıktıda görünmez.
    # Üretmek için: python -c "import secrets; print(secrets.token_urlsafe(32))"
    jwt_gizli: SecretStr
    erisim_suresi_dk: int = 15
    yenileme_suresi_gun: int = 30
    # Açık kayıt (POST /kayit). Üretimde kapalı; pilot işletmeler komutla açılır (K5).
    acik_kayit: bool = False
    # Salt okunur demo (K25): yazma yalnızca giriş/çıkış/işletme seçimi uçlarında (rotalar/ara_katman.py).
    salt_okunur: bool = False
    # Kamuya açık demo girişi (K26): ikisi de tanımlıysa giriş formu dolu gelir. Parola koda yazılmaz.
    demo_giris_eposta: str | None = None
    demo_giris_parola: SecretStr | None = None

    @field_validator("jwt_gizli")
    @classmethod
    def _jwt_gizli_yeterli(cls, deger: SecretStr) -> SecretStr:
        if len(deger.get_secret_value().encode()) < JWT_GIZLI_EN_AZ_BAYT:
            raise ValueError(f"PANOSU_JWT_GIZLI en az {JWT_GIZLI_EN_AZ_BAYT} bayt olmalı")
        return deger

    @model_validator(mode="after")
    def _uretim_en_az_yetki(self) -> "Ayarlar":
        """K22: üretimde en az yetki. Hata mesajları adres veya parola içermez."""
        if self.ortam != "uretim":
            return self
        try:
            kullanici = make_url(self.veritabani_url).username
        except Exception:
            raise ValueError("PANOSU_VERITABANI_URL çözümlenemedi") from None
        if kullanici != UYGULAMA_ROLU:
            raise ValueError(f"Üretimde uygulama yalnızca {UYGULAMA_ROLU} rolüyle bağlanır")
        if self.migrasyon_url:
            raise ValueError("Üretimde PANOSU_MIGRASYON_URL tanımlı olamaz (yönetici adresi web sunucusuna girmez)")
        if self.acik_kayit:
            raise ValueError("Üretimde PANOSU_ACIK_KAYIT kapalı olmalı")
        return self


ayarlar = Ayarlar()
