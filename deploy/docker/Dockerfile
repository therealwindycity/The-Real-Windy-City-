FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SCANNER_DATA_DIR=/var/lib/civic-scanner \
    SCANNER_MODEL_CACHE_DIR=/var/lib/civic-scanner/models

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      ca-certificates \
      curl \
      git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 scanner \
    && useradd --system --uid 10001 --gid scanner --home-dir /var/lib/civic-scanner scanner \
    && mkdir -p /var/lib/civic-scanner && chown -R scanner:scanner /var/lib/civic-scanner && chmod 0700 /var/lib/civic-scanner

WORKDIR /app/services/scanner_transcriber

COPY services/scanner_transcriber/requirements.lock.txt ./requirements.lock.txt
RUN pip install --no-cache-dir --upgrade pip==26.2.2 \
    && pip install --no-cache-dir -r requirements.lock.txt

COPY services/scanner_transcriber/ ./
RUN pip install --no-cache-dir --no-deps .

USER scanner
EXPOSE 8787

HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8787/healthz >/dev/null || exit 1

ENTRYPOINT ["scanner-transcriber"]
CMD ["serve"]
