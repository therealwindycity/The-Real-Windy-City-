# Civic Cheyenne Live Scanner Transcription Service (`scanner_transcriber`)

Continuous single-feed radio capture, neural speech-to-text (`faster-whisper` + Silero VAD), durable SQLite WAL storage, health telemetry, and authenticated HTTP/SSE API for Civic Cheyenne.

Default vertical slice: **Broadcastify Feed `#47003` — `Laramie County Law Enforcement`**.

---

## Verified Resource Measurements

Measured on a 2 vCPU Intel Xeon @ 2.60 GHz Linux x86_64 host running Python 3.11.2, `ffmpeg` 7.0.2, `faster-whisper` 1.2.1 (`ctranslate2` 4.8.3 INT8 + `onnxruntime` 1.31.0 Silero VAD), and SQLite WAL:

| Metric | Measured Value (`tiny.en`, INT8, 2 threads) | Recommended Production Host Minimum |
|---|---|---|
| Steady-state CPU usage (including model load) | `4.01 s` CPU across `18.45 s` wall clock (**~21.7% of 1 vCPU**) | **2 vCPU** (`small.en` INT8: ~45% of 1 vCPU) |
| Peak process RSS memory (`ru_maxrss`) | **324.52 MiB** | **1 GiB RAM** (`small.en` INT8: **2 GiB RAM**) |
| End-to-end `capture_to_publish_ms` (after chunk window) | **min 526 ms / mean 559.3 ms / max 600 ms** (for 5.0 s audio chunks) | `< 2,000 ms` after chunk boundary |
| Disk footprint (SQLite transcripts + 24h private WAVs) | `~15.4 MiB/minute` of continuous retained 16 kHz PCM audio (~`22.1 GiB/24h` worst-case if 100% continuous; `< 50 MiB/week` SQLite metadata) | **40 GiB persistent SSD volume** (`/var/lib/civic-scanner`) |

---

## Architecture & Provenance Invariants

1. **Strict Source Authorization & No Browser Mic Capture**:
   - Audio capture runs exclusively on the backend worker over `ffmpeg` (direct stream URL) or `yt-dlp` -> `ffmpeg` (explicit page URL).
   - `SCANNER_DIRECT_AUDIO_URL` and `SCANNER_PAGE_URL` are distinct settings; configuring both raises `ConfigurationError`.
   - Production startup (`SCANNER_ENV=production`) requires `SCANNER_SOURCE_AUTHORIZED=true` and `SCANNER_API_TOKEN` and **strictly rejects** any stub/mock ASR backend.
   - Upstream stream credentials (`SCANNER_SOURCE_AUTH_HEADER`, `SCANNER_SOURCE_COOKIE_FILE`) remain exclusively on the backend host; URL tokens/userinfo and subprocess errors are scrubbed via `sanitize_diagnostic_text()` before logging or health exposure.
2. **Anti-SSRF & Endpoint Access Controls**:
   - Outbound capture hosts must match `SCANNER_ALLOWED_HOSTS`; link-local/cloud-metadata addresses (`169.254.169.254`, `fe80::/10`), multicast, unspecified (`0.0.0.0`), and `-` option-injection strings are unconditionally blocked.
   - Any HTTP request supplying `?url=`, `?stream_url=`, `?source_url=`, `?media_url=`, `?page_url=`, `?target=`, or `?fetch=` returns `403 Forbidden`.
   - All `/api/scanner/*` routes enforce constant-time (`hmac.compare_digest`) token verification when `SCANNER_REQUIRE_AUTH=true`.
   - For public web deployments, Caddy (`deploy/caddy/Caddyfile`) terminates TLS and injects `Authorization: Bearer ...` upstream so secrets are never embedded in client JavaScript.
3. **Truthful Provenance, Timestamps, Ordering & Retention**:
   - Capture `audio_start_utc` and `audio_end_utc` are recorded at sample-arrival time before ASR queueing; processing lag never shifts capture timestamps forward.
   - Silence and carrier hum are filtered by acoustic dBFS + frame ratio + Silero VAD without inventing incidents.
   - Every published segment carries `verification_status: "unverified_machine"`, raw `whisper_avg_logprob` explicitly labeled as **not** a calibrated word-accuracy score, and never infers unit/agency/address/outcome from feed names.
   - Segments are persisted to SQLite WAL **before** publication (`cursor` assignment), deduplicated idempotently, ordered monotonically across out-of-order completions, and never committed back into Git.
   - `enforce_retention()` sweeps raw private WAV files (`0700` dir / `0600` files) independently of transcript rows and immediately updates `audio_retained = false` + `audio_purged_at_utc` upon purge.

---

## Operations Runbook (Start, Stop, Monitor, Backup, Restore, Rollback)

### 1. Start / Stop / Restart (Docker Compose with HTTPS)
```bash
cp deploy/.env.example deploy/.env
chmod 0600 deploy/.env
# Edit deploy/.env with authorized stream URL, SCANNER_SOURCE_AUTHORIZED=true, SCANNER_API_TOKEN, SCANNER_API_HOSTNAME
docker compose -f deploy/docker/docker-compose.yml up -d --build
docker compose -f deploy/docker/docker-compose.yml ps
docker compose -f deploy/docker/docker-compose.yml stop
```

### 2. Start / Stop / Monitor (`systemd` bare-metal / VM)
```bash
sudo install -d -m 0750 /etc/civic-scanner
sudo cp deploy/.env.example /etc/civic-scanner/scanner.env
sudo chmod 0600 /etc/civic-scanner/scanner.env
sudo cp deploy/systemd/civic-scanner-transcriber.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now civic-scanner-transcriber.service

# Operational health check (/healthz returns HTTP 200 ONLY when audio is fresh and storage/ASR are healthy)
curl -i http://127.0.0.1:8787/healthz
curl -H "Authorization: Bearer $SCANNER_API_TOKEN" http://127.0.0.1:8787/api/scanner/health

# Tail sanitized logs
sudo journalctl -u civic-scanner-transcriber.service -f
```

### 3. Online Hot Backup & Verified Restore
```bash
# Consistent online backup while service is running (uses sqlite3 backup API + PRAGMA integrity_check)
scanner-transcriber backup --dest /var/backups/civic-scanner/scanner-$(date -u +%Y%m%dT%H%M%SZ).sqlite3

# Restore procedure (stop writer first so exclusive feed lock & WAL files close cleanly)
sudo systemctl stop civic-scanner-transcriber.service
scanner-transcriber restore --src /var/backups/civic-scanner/scanner-20261021T180000Z.sqlite3
sudo systemctl start civic-scanner-transcriber.service
```

### 4. Bounded Live Smoke Verification
```bash
scanner-transcriber smoke --seconds 30 --require-audio
```

### 5. Clean Rollback Procedure
1. **Frontend rollback**: Set `NEXT_PUBLIC_SCANNER_API_BASE_URL=""` (or revert the frontend commit) — the `Signals` interface continues rendering the existing Broadcastify embed player cleanly while marking live machine transcription unconfigured.
2. **Backend rollback**: Stop `civic-scanner-transcriber` (`systemctl stop` or `docker compose down`), check out the prior release tag, restore the pre-upgrade SQLite snapshot via `scanner-transcriber restore --src <backup>` if schema changed, and restart.
