# Immagine del server della Bazzica (deploy su TrueNAS SCALE, vedi docs/deploy-truenas.md).
# Costruzione sul NAS:   docker build -t bazzica:locale /mnt/<pool>/apps/bazzica/codice
#
# Versione di Python fissata. Se un giorno il tag non fosse più disponibile, si può cambiare
# senza toccare il file:  docker build --build-arg PYTHON_IMAGE=python:3.13-slim -t bazzica:locale .
ARG PYTHON_IMAGE=python:3.13.18-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Utente non root con gli stessi uid/gid dell'utente "apps" di TrueNAS (568),
# così i file in data/ e logs/ sui dataset appartengono ad apps:apps.
RUN groupadd --gid 568 apps \
 && useradd --uid 568 --gid 568 --no-create-home --home-dir /app --shell /usr/sbin/nologin apps

# Prima le dipendenze (strato riutilizzato finché requirements-docker.txt non cambia)
COPY requirements-docker.txt ./
RUN pip install -r requirements-docker.txt

# Poi il codice e le risorse del gioco (appartengono a root: in sola lettura per il server)
COPY run.py ./
COPY bazzica ./bazzica
COPY assets ./assets
RUN mkdir -p /app/data /app/logs && chown 568:568 /app/data /app/logs

USER 568:568

# versione mostrata da /api/salute (es. il commit git): --build-arg VERSIONE=$(git rev-parse --short HEAD)
ARG VERSIONE=locale
ENV BAZZICA_VERSIONE=${VERSIONE} \
    BAZZICA_HOST=0.0.0.0 \
    BAZZICA_PORTA=8000 \
    BAZZICA_DATI=/app/data \
    BAZZICA_LOG=/app/logs

EXPOSE 8000
VOLUME ["/app/data", "/app/logs"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/salute', timeout=4).status == 200 else 1)"

CMD ["python", "run.py"]
