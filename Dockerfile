# CORE - Causal Operations & Recovery Engine, as one public web service.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    CORE_PUBLIC_DEMO=1
# OCR for the document archive (English, Russian, Azerbaijani)
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-rus tesseract-ocr-aze \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/core
COPY deploy/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
COPY backend ./backend
COPY scripts/init_demo.py ./scripts/init_demo.py
COPY frontend/dist ./frontend/dist
# Only what the running app reads. The raw Petrinex zips (130 MB) are inputs for
# rebuilding the evidence base, which the public build never does.
COPY data/processed ./data/processed
COPY data/demo ./data/demo
COPY data/alberta/cache ./data/alberta/cache
EXPOSE 8000
# empty host = every interface, IPv4 and IPv6 (Fly's proxy is IPv4)
CMD ["uvicorn", "backend.api.main:app", "--host", "", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
