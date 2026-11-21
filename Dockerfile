# ───── Étape 1 : build du front ─────
FROM node:20-alpine AS front
WORKDIR /f
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ───── Étape 2 : API ─────
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app DATA_DIR=/data PORT=8080 STATIC_DIR=/app/static
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-dejavu-core fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rh_manager ./rh_manager
COPY --from=front /f/dist ./static

# social_config.py écrit dans /app/uploads/social : on le redirige vers le volume
RUN ln -s /data/uploads /app/uploads

VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8080')+'/health',timeout=4)" || exit 1

CMD ["python", "-m", "rh_manager.run"]