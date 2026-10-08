# A rendereléshez fej nélküli Chromium kell a rendszerkönyvtáraival együtt;
# ezt a Playwright telepítője hozza.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY requirements.txt .
# A Tesseract a feltöltött felvételek szövegét olvassa: a neveket, e-mail-címeket
# és telefonszámokat elmossuk, mielőtt bármi videóba kerülne (lásd redact.py).
RUN pip install --no-cache-dir -r requirements.txt \
 && python -m playwright install --with-deps chromium \
 && apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-hun tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*
COPY . .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
