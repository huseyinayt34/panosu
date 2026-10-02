# Panosu web paneli (Adım 11, K28; docs/adim-11-tasarim.md). İmajı Render derler.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-uretim.txt .
RUN pip install --no-cache-dir -r requirements-uretim.txt

COPY . .

RUN useradd --create-home --uid 10001 panosu
USER panosu

EXPOSE 8000

# Render PORT'u ortam değişkeniyle verir; HTTPS Render'da sonlanır (K27).
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'
