# Liest Spielstände für die Karte
FROM node:22-slim AS extract
WORKDIR /x
COPY app/modules/karte/extract/package*.json ./
RUN npm ci --omit=dev

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=extract /usr/local/bin/node /usr/local/bin/node
RUN node --version

COPY app ./app
COPY --from=extract /x/node_modules ./app/modules/karte/extract/node_modules

RUN useradd -r -u 10001 satis && mkdir /data && chown satis /data
USER satis
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz')" || exit 1

# --preload: App (Secret, DB-Schema) wird genau einmal vor dem Forken der Worker initialisiert.
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-w", "2", "--threads", "4", "--preload", "--access-logfile", "-", "app:create_app()"]
