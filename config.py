"""Uygulama ayarları. Değerler ortam değişkeninden veya .env dosyasından okunur (koda GÖMÜLMEZ)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Ayarlar(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PANOSU_", extra="ignore")

    # Örn: postgresql+psycopg2://panosu_app:PAROLA@localhost:5432/panosu
    veritabani_url: str
    # "gelistirme" | "uretim"  (üretimde geçici başlık tabanlı kimlik devre dışıdır)
    ortam: str = "gelistirme"
    # Yalnızca Alembic kullanır: DDL yetkili rol (örn. postgres). Uygulama bu URL'yi ASLA kullanmaz.
    migrasyon_url: str | None = None


ayarlar = Ayarlar()