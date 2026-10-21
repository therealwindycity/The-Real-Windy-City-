"""Validated configuration, credential redaction, and strict anti-SSRF source URL controls."""

from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class ConfigurationError(ValueError):
    """Raised when scanner service configuration violates safety or production invariants."""


class SourceRestrictionError(ValueError):
    """Raised when a source URL violates scheme, host allowlist, or SSRF restrictions."""


SENSITIVE_QUERY_KEYS = frozenset(
    {
        "token",
        "access_token",
        "auth",
        "apikey",
        "api_key",
        "key",
        "password",
        "pass",
        "pwd",
        "secret",
        "sig",
        "signature",
        "cookie",
        "session",
        "bcfyuser1",
    }
)

DEFAULT_ALLOWED_HOSTS = (
    "broadcastify.cdnstream1.com",
    "audio.broadcastify.com",
    "www.broadcastify.com",
    "127.0.0.1",
    "localhost",
)


def redact_url(raw_url: str | None) -> str | None:
    """Return a log/API-safe representation of a URL without userinfo or secret query values."""
    if not raw_url:
        return None
    try:
        parsed = urlsplit(raw_url.strip())
    except Exception:
        return "<invalid-url>"

    if parsed.scheme == "file":
        return f"file:///{Path(parsed.path).name}"

    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        netloc = f"[{hostname}]"
    else:
        netloc = hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"

    clean_query = []
    for k, v in parse_qsl(parsed.query, keep_blank_values=True):
        if k.lower() in SENSITIVE_QUERY_KEYS:
            clean_query.append((k, "REDACTED"))
        else:
            clean_query.append((k, v))

    return urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(clean_query), ""))


def source_origin_label(raw_url: str | None) -> str | None:
    """Return scheme://host[:port] (or file://local-fixture) with zero credentials or paths."""
    if not raw_url:
        return None
    parsed = urlsplit(raw_url.strip())
    if parsed.scheme == "file":
        return "file://local-authorized-fixture"
    host = parsed.hostname or "unknown"
    if parsed.port:
        return f"{parsed.scheme}://{host}:{parsed.port}"
    return f"{parsed.scheme}://{host}"


def validate_source_url(
    url: str,
    *,
    allowed_hosts: tuple[str, ...] | list[str],
    allow_file_scheme: bool = False,
) -> str:
    """Validate that a configured source URL cannot be used for SSRF or ffmpeg option injection."""
    if not url or not isinstance(url, str):
        raise SourceRestrictionError("Source URL must be a non-empty string.")
    cleaned = url.strip()
    if cleaned.startswith("-"):
        raise SourceRestrictionError("Source URL must not begin with '-' (option injection guard).")
    if any(ch in cleaned for ch in ("\r", "\n", "\x00")):
        raise SourceRestrictionError("Source URL contains forbidden control characters.")

    parsed = urlsplit(cleaned)
    scheme = parsed.scheme.lower()

    if scheme == "file":
        if not allow_file_scheme:
            raise SourceRestrictionError(
                "file:// audio sources are disabled unless SCANNER_ALLOW_FILE_SOURCES=true."
            )
        if parsed.netloc and parsed.netloc not in ("", "localhost"):
            raise SourceRestrictionError("Remote host file:// URLs are forbidden.")
        file_path = Path(parsed.path).resolve()
        if not file_path.is_file():
            raise SourceRestrictionError(f"Configured audio file does not exist: {file_path}")
        return f"file://{file_path}"

    if scheme not in ("http", "https"):
        raise SourceRestrictionError(
            f"Unsupported source URL scheme {scheme!r}; only http/https are permitted."
        )

    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        raise SourceRestrictionError("Source URL must specify a valid host.")

    normalized_allowlist = {h.lower().strip().rstrip(".") for h in allowed_hosts if h.strip()}
    if not normalized_allowlist:
        raise SourceRestrictionError("Source host allowlist is empty; all network URLs blocked.")

    # Always block link-local / cloud metadata addresses even if misconfigured.
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None

    if ip is not None and (ip.is_link_local or ip.is_multicast or ip.is_unspecified):
        raise SourceRestrictionError(
            f"Address {hostname} is forbidden (link-local/unspecified/multicast)."
        )

    host_allowed = hostname in normalized_allowlist or any(
        pattern.startswith("*.") and hostname.endswith(pattern[1:])
        for pattern in normalized_allowlist
    )
    if not host_allowed:
        raise SourceRestrictionError(
            f"Host {hostname!r} is not in SCANNER_ALLOWED_HOSTS ({sorted(normalized_allowlist)})."
        )

    return cleaned


_URL_IN_TEXT_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)


def sanitize_diagnostic_text(
    text: str, *, extra_secrets: tuple[str, ...] = ()
) -> str:
    """Scrub URL query/userinfo credentials and explicit secret strings from subprocess/error text."""
    if not text:
        return ""

    def _replace_match(match: re.Match[str]) -> str:
        candidate = match.group(0)
        trailing = ""
        while candidate and candidate[-1] in ".,;:)]":
            trailing = candidate[-1] + trailing
            candidate = candidate[:-1]
        return (redact_url(candidate) or "<redacted-url>") + trailing

    cleaned = _URL_IN_TEXT_RE.sub(_replace_match, text)
    for secret in extra_secrets:
        if secret and len(secret) >= 4:
            cleaned = cleaned.replace(secret, "[REDACTED]")
    return cleaned


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class FeedConfig:
    """Single scanner feed configuration. Default vertical slice: Broadcastify feed 47003."""

    feed_id: str = "47003"
    feed_name: str = "Laramie County Law Enforcement"
    # Direct audio URL and webpage URL are strictly separate settings.
    direct_audio_url: str | None = None
    page_url: str | None = None
    source_authorized: bool = False
    license_attribution: str = "Configured authorized radio stream (unverified machine transcription)"


@dataclass
class ServiceConfig:
    """Complete validated configuration for the scanner capture + ASR + API service."""

    environment: str = "production"  # 'production' | 'development' | 'test'
    data_dir: Path = field(default_factory=lambda: Path("/var/lib/civic-scanner"))
    feed: FeedConfig = field(default_factory=FeedConfig)

    # Server-only credentials (never serialized to logs or JSON responses)
    source_auth_header: str | None = None
    source_cookie_file: Path | None = None
    source_user_agent: str = "CivicCheyenneScannerTranscriber/0.1"

    # Anti-SSRF allowlist
    allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS
    allow_file_sources: bool = False

    # Audio capture parameters
    ffmpeg_bin: str = "ffmpeg"
    yt_dlp_bin: str = "yt-dlp"
    chunk_seconds: float = 10.0
    min_flush_seconds: float = 0.6
    read_timeout_seconds: float = 12.0
    stale_after_seconds: float = 35.0
    reconnect_initial_seconds: float = 1.0
    reconnect_max_seconds: float = 60.0
    reconnect_multiplier: float = 2.0
    max_pending_chunks: int = 32

    # ASR parameters
    asr_backend: str = "faster-whisper"  # 'faster-whisper' ONLY in production
    asr_model_name: str = "tiny.en"
    asr_model_dir: Path | None = None
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"
    asr_cpu_threads: int = 2
    asr_beam_size: int = 1
    asr_language: str = "en"
    silence_rms_dbfs: float = -52.0
    unintelligible_rms_dbfs: float = -30.0
    min_speech_frame_ratio: float = 0.03
    max_no_speech_prob: float = 0.85

    # Retention & privacy
    retain_private_audio: bool = True
    audio_retention_seconds: int = 24 * 3600
    transcript_retention_seconds: int = 7 * 86400
    retention_sweep_interval_seconds: float = 60.0

    # HTTP API & security
    bind_host: str = "127.0.0.1"
    bind_port: int = 8787
    api_token: str | None = None
    require_auth: bool = True
    cors_origins: tuple[str, ...] = ()
    worker_revision: str = "unknown"

    def validate(self) -> None:
        if self.environment not in ("production", "development", "test"):
            raise ConfigurationError(
                f"Invalid SCANNER_ENV={self.environment!r}; expected production, development, or test."
            )

        if self.environment == "production":
            if self.asr_backend != "faster-whisper":
                raise ConfigurationError(
                    f"Production mode strictly rejects non-Whisper/stub ASR backend: {self.asr_backend!r}."
                )
            if self.require_auth and not self.api_token:
                raise ConfigurationError(
                    "Production mode with SCANNER_REQUIRE_AUTH=true requires SCANNER_API_TOKEN."
                )

        if self.feed.direct_audio_url and self.feed.page_url:
            raise ConfigurationError(
                "Configure either direct_audio_url OR page_url for a feed, never both simultaneously."
            )

        if self.chunk_seconds <= 0 or self.chunk_seconds > 120:
            raise ConfigurationError("chunk_seconds must be in (0, 120].")
        if self.read_timeout_seconds <= 0:
            raise ConfigurationError("read_timeout_seconds must be positive.")
        if self.audio_retention_seconds < 0 or self.transcript_retention_seconds <= 0:
            raise ConfigurationError(
                "audio_retention_seconds must be >= 0 and transcript_retention_seconds must be > 0."
            )

        if self.feed.direct_audio_url:
            self.feed.direct_audio_url = validate_source_url(
                self.feed.direct_audio_url,
                allowed_hosts=self.allowed_hosts,
                allow_file_scheme=self.allow_file_sources,
            )
            if self.environment == "production" and not self.feed.source_authorized:
                raise ConfigurationError(
                    "Production mode requires explicit SCANNER_SOURCE_AUTHORIZED=true confirming stream access rights."
                )

        if self.feed.page_url:
            self.feed.page_url = validate_source_url(
                self.feed.page_url,
                allowed_hosts=self.allowed_hosts,
                allow_file_scheme=False,
            )
            if self.environment == "production" and not self.feed.source_authorized:
                raise ConfigurationError(
                    "Production mode requires explicit SCANNER_SOURCE_AUTHORIZED=true confirming stream access rights."
                )

        if self.source_cookie_file is not None and not self.source_cookie_file.is_file():
            raise ConfigurationError(
                f"Configured SCANNER_SOURCE_COOKIE_FILE does not exist: {self.source_cookie_file}"
            )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "db" / "scanner.sqlite3"

    @property
    def private_audio_dir(self) -> Path:
        return self.data_dir / "private_audio"

    @property
    def lock_dir(self) -> Path:
        return self.data_dir / "locks"

    @property
    def model_cache_dir(self) -> Path:
        if self.asr_model_dir is not None:
            return self.asr_model_dir
        return Path(
            os.environ.get("SCANNER_MODEL_CACHE_DIR", str(Path.home() / ".cache" / "scanner-models"))
        )

    @classmethod
    def from_env(cls) -> "ServiceConfig":
        allowed_raw = os.environ.get("SCANNER_ALLOWED_HOSTS", ",".join(DEFAULT_ALLOWED_HOSTS))
        cors_raw = os.environ.get("SCANNER_CORS_ORIGINS", "")
        cookie_raw = os.environ.get("SCANNER_SOURCE_COOKIE_FILE")
        model_dir_raw = os.environ.get("SCANNER_ASR_MODEL_DIR")
        env = os.environ.get("SCANNER_ENV", "production").strip().lower()

        cfg = cls(
            environment=env,
            data_dir=Path(os.environ.get("SCANNER_DATA_DIR", "/var/lib/civic-scanner")),
            feed=FeedConfig(
                feed_id=os.environ.get("SCANNER_FEED_ID", "47003").strip(),
                feed_name=os.environ.get(
                    "SCANNER_FEED_NAME", "Laramie County Law Enforcement"
                ).strip(),
                direct_audio_url=os.environ.get("SCANNER_DIRECT_AUDIO_URL") or None,
                page_url=os.environ.get("SCANNER_PAGE_URL") or None,
                source_authorized=_env_bool("SCANNER_SOURCE_AUTHORIZED", False),
                license_attribution=os.environ.get(
                    "SCANNER_SOURCE_ATTRIBUTION",
                    "Broadcastify Feed #47003 · Laramie County Law Enforcement (configured stream)",
                ),
            ),
            source_auth_header=os.environ.get("SCANNER_SOURCE_AUTH_HEADER") or None,
            source_cookie_file=Path(cookie_raw) if cookie_raw else None,
            source_user_agent=os.environ.get(
                "SCANNER_SOURCE_USER_AGENT", "CivicCheyenneScannerTranscriber/0.1"
            ),
            allowed_hosts=tuple(h.strip() for h in allowed_raw.split(",") if h.strip()),
            allow_file_sources=_env_bool("SCANNER_ALLOW_FILE_SOURCES", False),
            ffmpeg_bin=os.environ.get("SCANNER_FFMPEG_BIN", "ffmpeg"),
            yt_dlp_bin=os.environ.get("SCANNER_YTDLP_BIN", "yt-dlp"),
            chunk_seconds=float(os.environ.get("SCANNER_CHUNK_SECONDS", "10.0")),
            min_flush_seconds=float(os.environ.get("SCANNER_MIN_FLUSH_SECONDS", "0.6")),
            read_timeout_seconds=float(os.environ.get("SCANNER_READ_TIMEOUT_SECONDS", "12.0")),
            stale_after_seconds=float(os.environ.get("SCANNER_STALE_AFTER_SECONDS", "35.0")),
            reconnect_initial_seconds=float(
                os.environ.get("SCANNER_RECONNECT_INITIAL_SECONDS", "1.0")
            ),
            reconnect_max_seconds=float(os.environ.get("SCANNER_RECONNECT_MAX_SECONDS", "60.0")),
            reconnect_multiplier=float(os.environ.get("SCANNER_RECONNECT_MULTIPLIER", "2.0")),
            max_pending_chunks=int(os.environ.get("SCANNER_MAX_PENDING_CHUNKS", "32")),
            asr_backend=os.environ.get("SCANNER_ASR_BACKEND", "faster-whisper").strip(),
            asr_model_name=os.environ.get("SCANNER_ASR_MODEL", "tiny.en").strip(),
            asr_model_dir=Path(model_dir_raw) if model_dir_raw else None,
            asr_device=os.environ.get("SCANNER_ASR_DEVICE", "cpu").strip(),
            asr_compute_type=os.environ.get("SCANNER_ASR_COMPUTE_TYPE", "int8").strip(),
            asr_cpu_threads=int(os.environ.get("SCANNER_ASR_CPU_THREADS", "2")),
            asr_beam_size=int(os.environ.get("SCANNER_ASR_BEAM_SIZE", "1")),
            asr_language=os.environ.get("SCANNER_ASR_LANGUAGE", "en").strip(),
            silence_rms_dbfs=float(os.environ.get("SCANNER_SILENCE_RMS_DBFS", "-52.0")),
            unintelligible_rms_dbfs=float(
                os.environ.get("SCANNER_UNINTELLIGIBLE_RMS_DBFS", "-30.0")
            ),
            min_speech_frame_ratio=float(
                os.environ.get("SCANNER_MIN_SPEECH_FRAME_RATIO", "0.03")
            ),
            max_no_speech_prob=float(os.environ.get("SCANNER_MAX_NO_SPEECH_PROB", "0.85")),
            retain_private_audio=_env_bool("SCANNER_RETAIN_PRIVATE_AUDIO", True),
            audio_retention_seconds=int(
                os.environ.get("SCANNER_AUDIO_RETENTION_SECONDS", str(24 * 3600))
            ),
            transcript_retention_seconds=int(
                os.environ.get("SCANNER_TRANSCRIPT_RETENTION_SECONDS", str(7 * 86400))
            ),
            retention_sweep_interval_seconds=float(
                os.environ.get("SCANNER_RETENTION_SWEEP_SECONDS", "60.0")
            ),
            bind_host=os.environ.get("SCANNER_BIND_HOST", "127.0.0.1").strip(),
            bind_port=int(os.environ.get("SCANNER_BIND_PORT", "8787")),
            api_token=os.environ.get("SCANNER_API_TOKEN") or None,
            require_auth=_env_bool("SCANNER_REQUIRE_AUTH", env == "production"),
            cors_origins=tuple(o.strip() for o in cors_raw.split(",") if o.strip()),
            worker_revision=os.environ.get("SCANNER_WORKER_REVISION", "unknown").strip(),
        )
        cfg.validate()
        return cfg
