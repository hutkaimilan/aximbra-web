# 1. szakasz: csak feltöltés és médiatár — nincs benne Chromium, se Tesseract,
# így a build gyors és a futó szolgáltatás kevés memóriát visz. A renderelés
# a következő szakaszban kerül bele.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
# ffmpeg: a HEVC/MOV felvételek átalakítása és a borítóképek.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--timeout-keep-alive", "75"]
