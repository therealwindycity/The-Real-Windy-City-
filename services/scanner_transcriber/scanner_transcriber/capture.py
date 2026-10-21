"""Bounded PCM stream capture over ffmpeg with exact UTC timestamps, read timeouts, and backoff."""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import os
import selectors
import subprocess
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from .config import (
    ServiceConfig,
    SourceRestrictionError,
    redact_url,
    sanitize_diagnostic_text,
    validate_source_url,
)

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH_BYTES  # 32,000 bytes/sec


@dataclass(frozen=True)
class CapturedChunk:
    session_id: str
    sequence_no: int
    audio_start_utc: str
    audio_end_utc: str
    duration_seconds: float
    wav_path: Path
    audio_sha256: str
    audio_bytes: int
    retained: bool
    private_audio_ref: str | None


def format_utc(ts: dt.datetime) -> str:
    return ts.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def write_pcm16_wav(pcm_bytes: bytes, dest_path: Path) -> tuple[str, int]:
    """Write 16kHz mono s16le PCM to a mode-0600 WAV file and compute its SHA-256."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(dest_path.parent, 0o700)
    except OSError:
        pass

    tmp_path = dest_path.parent / f".tmp-{os.getpid()}-{dest_path.name}"
    with wave.open(str(tmp_path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH_BYTES)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    os.chmod(tmp_path, 0o600)
    tmp_path.replace(dest_path)

    raw_bytes = dest_path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    return digest, len(raw_bytes)


def compute_backoff_seconds(
    attempt: int,
    *,
    initial_seconds: float = 1.0,
    multiplier: float = 2.0,
    max_seconds: float = 60.0,
) -> float:
    """Deterministic bounded exponential reconnect backoff."""
    exp = initial_seconds * (multiplier ** max(0, attempt - 1))
    return round(min(max_seconds, max(0.05, exp)), 3)


def resolve_stream_url(config: ServiceConfig) -> tuple[str, str]:
    """Resolve `(media_url, source_kind)` strictly separating direct audio URLs from webpage URLs."""
    feed = config.feed
    if feed.direct_audio_url:
        validated = validate_source_url(
            feed.direct_audio_url,
            allowed_hosts=config.allowed_hosts,
            allow_file_scheme=config.allow_file_sources,
        )
        return validated, "direct_audio"

    if feed.page_url:
        validated_page = validate_source_url(
            feed.page_url,
            allowed_hosts=config.allowed_hosts,
            allow_file_scheme=False,
        )
        cmd = [
            config.yt_dlp_bin,
            "-g",
            "--no-playlist",
            "-f",
            "ba[protocol^=m3u8]/ba/best[protocol^=m3u8]/best",
            validated_page,
        ]
        res = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
        urls = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        if res.returncode != 0 or not urls:
            stderr_tail = (res.stderr or "yt-dlp returned no media URL").strip()[-240:]
            raise RuntimeError(f"Page URL stream resolution failed: {stderr_tail}")
        resolved = validate_source_url(
            urls[0],
            allowed_hosts=config.allowed_hosts,
            allow_file_scheme=False,
        )
        return resolved, "page_url"

    raise SourceRestrictionError(
        "No authorized scanner audio URL is configured (set SCANNER_DIRECT_AUDIO_URL or SCANNER_PAGE_URL)."
    )


def _cookie_header_from_netscape_jar(cookie_file: Path, target_host: str) -> str | None:
    """Extract matching cookies from a server-side mode-0600 Netscape cookie file without logging values."""
    pairs: list[str] = []
    host_lower = target_host.lower().lstrip(".")
    now_ts = int(time.time())
    for raw_line in cookie_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, _path, _secure, expiry_s, name, value = parts[:7]
        dom_clean = domain.lower().lstrip(".")
        if host_lower == dom_clean or host_lower.endswith(f".{dom_clean}"):
            try:
                exp = int(expiry_s)
                if exp > 0 and exp < now_ts:
                    continue
            except ValueError:
                pass
            pairs.append(f"{name}={value}")
    return "; ".join(pairs) if pairs else None


def build_ffmpeg_command(config: ServiceConfig, media_url: str) -> list[str]:
    """Construct an ffmpeg command writing mono 16kHz s16le PCM to pipe:1."""
    cmd = [config.ffmpeg_bin, "-nostdin", "-hide_banner", "-loglevel", "error"]
    parsed = urlsplit(media_url)

    if parsed.scheme in ("http", "https"):
        headers: list[str] = []
        if config.source_user_agent:
            headers.append(f"User-Agent: {config.source_user_agent}")
        if config.source_auth_header:
            headers.append(f"Authorization: {config.source_auth_header}")
        if config.source_cookie_file and parsed.hostname:
            cookie_val = _cookie_header_from_netscape_jar(
                config.source_cookie_file, parsed.hostname
            )
            if cookie_val:
                headers.append(f"Cookie: {cookie_val}")
        if headers:
            cmd.extend(["-headers", "\r\n".join(headers) + "\r\n"])
        # Use ffmpeg network read timeout in microseconds (rw_timeout) so hung TCP streams fail cleanly.
        rw_timeout_us = int(max(2.0, config.read_timeout_seconds) * 1_000_000)
        cmd.extend(["-rw_timeout", str(rw_timeout_us)])
    elif parsed.scheme == "file":
        # Read local fixture at real-time pace (-re) so live capture timestamps match real audio flow.
        cmd.append("-re")

    input_arg = parsed.path if parsed.scheme == "file" else media_url
    cmd.extend(
        [
            "-i",
            input_arg,
            "-vn",
            "-ac",
            str(CHANNELS),
            "-ar",
            str(SAMPLE_RATE),
            "-f",
            "s16le",
            "pipe:1",
        ]
    )
    return cmd


class StreamCaptureRunner:
    """Continuously captures bounded audio chunks, tracks exact UTC timestamps, and reports gaps."""

    def __init__(
        self,
        config: ServiceConfig,
        *,
        session_id: str,
        on_chunk: Callable[[CapturedChunk], None],
        on_audio_bytes: Callable[[dt.datetime], None],
        on_connecting: Callable[[int], None],
        on_upstream_error: Callable[[str, str], None],
        on_gap: Callable[[str, str, str], None],
        stop_event: object,
    ) -> None:
        self._config = config
        self._session_id = session_id
        self._on_chunk = on_chunk
        self._on_audio_bytes = on_audio_bytes
        self._on_connecting = on_connecting
        self._on_upstream_error = on_upstream_error
        self._on_gap = on_gap
        self._stop_event = stop_event
        self._sequence_no = 0
        self._last_audio_end: dt.datetime | None = None

    def _is_stopping(self) -> bool:
        return bool(self._stop_event.is_set())

    def _emit_buffer(
        self, pcm_buf: bytearray, chunk_start: dt.datetime, *, allow_short: bool
    ) -> dt.datetime | None:
        duration = len(pcm_buf) / float(BYTES_PER_SECOND)
        if duration <= 0:
            pcm_buf.clear()
            return None
        if not allow_short and duration < self._config.chunk_seconds:
            return None
        if allow_short and duration < self._config.min_flush_seconds:
            pcm_buf.clear()
            return None

        take_bytes = (
            len(pcm_buf)
            if allow_short
            else int(round(self._config.chunk_seconds * BYTES_PER_SECOND))
        )
        # Keep 2-byte sample alignment.
        take_bytes = min(len(pcm_buf), (take_bytes // 2) * 2)
        if take_bytes <= 0:
            return None

        raw_slice = bytes(pcm_buf[:take_bytes])
        del pcm_buf[:take_bytes]

        slice_dur = len(raw_slice) / float(BYTES_PER_SECOND)
        emit_utc = dt.datetime.now(dt.timezone.utc)
        projected_end = chunk_start + dt.timedelta(seconds=slice_dur)
        # Preserve sample-contiguous timestamps during 1.0x real-time streaming while enforcing physical
        # causality (`audio_end <= emit_utc`) when an Icecast/HTTP relay sends an initial pre-buffer burst.
        if projected_end > emit_utc:
            chunk_end = emit_utc
            effective_start = emit_utc - dt.timedelta(seconds=slice_dur)
        else:
            effective_start = chunk_start
            chunk_end = projected_end

        seq = self._sequence_no
        self._sequence_no += 1

        seg_stem = f"{self._session_id}-seq{seq:06d}"
        if self._config.retain_private_audio:
            date_folder = effective_start.strftime("%Y-%m-%d")
            wav_path = (
                self._config.private_audio_dir
                / self._config.feed.feed_id
                / date_folder
                / f"{seg_stem}.wav"
            )
            private_ref = f"private://audio/{self._config.feed.feed_id}/{date_folder}/{seg_stem}.wav"
        else:
            wav_path = self._config.data_dir / "tmp_chunks" / f"{seg_stem}.wav"
            private_ref = None

        sha256_hex, size_bytes = write_pcm16_wav(raw_slice, wav_path)
        self._last_audio_end = chunk_end

        chunk = CapturedChunk(
            session_id=self._session_id,
            sequence_no=seq,
            audio_start_utc=format_utc(effective_start),
            audio_end_utc=format_utc(chunk_end),
            duration_seconds=round(slice_dur, 3),
            wav_path=wav_path,
            audio_sha256=sha256_hex,
            audio_bytes=size_bytes,
            retained=self._config.retain_private_audio and self._config.audio_retention_seconds > 0,
            private_audio_ref=(
                private_ref
                if (self._config.retain_private_audio and self._config.audio_retention_seconds > 0)
                else None
            ),
        )
        self._on_chunk(chunk)
        return chunk_end

    def run(self) -> None:
        consecutive_failures = 0
        pending_gap_start: dt.datetime | None = None
        pending_gap_reason = "disconnect"

        while not self._is_stopping():
            self._on_connecting(consecutive_failures + 1)
            try:
                media_url, _source_kind = resolve_stream_url(self._config)
            except SourceRestrictionError as exc:
                self._on_upstream_error("source_unconfigured_or_restricted", str(exc))
                consecutive_failures += 1
                delay = compute_backoff_seconds(
                    consecutive_failures,
                    initial_seconds=self._config.reconnect_initial_seconds,
                    multiplier=self._config.reconnect_multiplier,
                    max_seconds=self._config.reconnect_max_seconds,
                )
                self._stop_event.wait(delay)
                continue
            except Exception as exc:
                self._on_upstream_error("source_resolution_failed", str(exc))
                consecutive_failures += 1
                delay = compute_backoff_seconds(
                    consecutive_failures,
                    initial_seconds=self._config.reconnect_initial_seconds,
                    multiplier=self._config.reconnect_multiplier,
                    max_seconds=self._config.reconnect_max_seconds,
                )
                self._stop_event.wait(delay)
                continue

            logger.info(
                "Starting ffmpeg audio capture for feed=%s source=%s",
                self._config.feed.feed_id,
                redact_url(media_url),
            )

            proc: subprocess.Popen[bytes] | None = None
            pcm_buf = bytearray()
            chunk_start: dt.datetime | None = None
            received_any_bytes = False
            timed_out = False

            try:
                cmd = build_ffmpeg_command(self._config, media_url)
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )
            except Exception as exc:
                self._on_upstream_error("ffmpeg_spawn_failed", str(exc))
                consecutive_failures += 1
                delay = compute_backoff_seconds(
                    consecutive_failures,
                    initial_seconds=self._config.reconnect_initial_seconds,
                    multiplier=self._config.reconnect_multiplier,
                    max_seconds=self._config.reconnect_max_seconds,
                )
                self._stop_event.wait(delay)
                continue

            assert proc.stdout is not None
            sel = selectors.DefaultSelector()
            sel.register(proc.stdout, selectors.EVENT_READ)

            try:
                while not self._is_stopping():
                    events = sel.select(timeout=min(1.0, self._config.read_timeout_seconds))
                    if not events:
                        if proc.poll() is not None:
                            break
                        last_rx = chunk_start + dt.timedelta(
                            seconds=len(pcm_buf) / float(BYTES_PER_SECOND)
                        ) if chunk_start else None
                        now_utc = dt.datetime.now(dt.timezone.utc)
                        # Check read timeout from start of attempt or last byte received.
                        ref_time = last_rx or pending_gap_start
                        if ref_time and (now_utc - ref_time).total_seconds() >= self._config.read_timeout_seconds:
                            timed_out = True
                            break
                        if not received_any_bytes:
                            # Track initial connect wait accurately via elapsed attribute.
                            elapsed_connect = getattr(self, "_attempt_started", None)
                            if elapsed_connect is None:
                                self._attempt_started = now_utc
                            elif (now_utc - elapsed_connect).total_seconds() >= self._config.read_timeout_seconds:
                                timed_out = True
                                break
                        continue

                    self._attempt_started = None
                    data = os.read(proc.stdout.fileno(), 16_384)
                    if not data:
                        break

                    now_utc = dt.datetime.now(dt.timezone.utc)
                    received_any_bytes = True
                    consecutive_failures = 0
                    self._on_audio_bytes(now_utc)

                    if pending_gap_start is not None:
                        self._on_gap(
                            format_utc(pending_gap_start),
                            format_utc(now_utc),
                            pending_gap_reason,
                        )
                        pending_gap_start = None

                    if chunk_start is None:
                        sample_dur = len(data) / float(BYTES_PER_SECOND)
                        chunk_start = now_utc - dt.timedelta(seconds=sample_dur)

                    pcm_buf.extend(data)
                    target_bytes = int(round(self._config.chunk_seconds * BYTES_PER_SECOND))
                    while len(pcm_buf) >= target_bytes:
                        next_start = self._emit_buffer(
                            pcm_buf, chunk_start, allow_short=False
                        )
                        if next_start is None:
                            break
                        chunk_start = next_start
            finally:
                self._attempt_started = None
                sel.close()
                if proc is not None and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=3)

                stderr_text = ""
                if proc is not None and proc.stderr is not None:
                    try:
                        raw_err = proc.stderr.read().decode("utf-8", errors="replace").strip()
                        stderr_text = sanitize_diagnostic_text(
                            raw_err,
                            extra_secrets=tuple(
                                s
                                for s in (
                                    self._config.api_token or "",
                                    self._config.source_auth_header or "",
                                )
                                if s
                            ),
                        )
                    except Exception:
                        stderr_text = ""

                # Always flush trailing buffered audio safely on stop OR upstream disconnect!
                if chunk_start is not None and len(pcm_buf) > 0:
                    self._emit_buffer(pcm_buf, chunk_start, allow_short=True)

            if self._is_stopping():
                break

            gap_anchor = self._last_audio_end or dt.datetime.now(dt.timezone.utc)
            if pending_gap_start is None:
                pending_gap_start = gap_anchor

            if timed_out:
                pending_gap_reason = "read_timeout"
                self._on_upstream_error(
                    "upstream_read_timeout",
                    f"No audio bytes received within {self._config.read_timeout_seconds:.1f}s timeout.",
                )
            elif received_any_bytes:
                pending_gap_reason = "upstream_restart_or_disconnect"
                detail = stderr_text[-200:] if stderr_text else "Upstream stream closed."
                self._on_upstream_error("upstream_disconnected", detail)
            else:
                pending_gap_reason = "upstream_connect_failed"
                detail = stderr_text[-200:] if stderr_text else "Upstream audio stream unreachable."
                self._on_upstream_error("upstream_unavailable", detail)

            consecutive_failures += 1
            delay = compute_backoff_seconds(
                consecutive_failures,
                initial_seconds=self._config.reconnect_initial_seconds,
                multiplier=self._config.reconnect_multiplier,
                max_seconds=self._config.reconnect_max_seconds,
            )
            logger.warning(
                "Upstream unavailable (%s); reconnecting in %.2fs (attempt #%d)",
                pending_gap_reason,
                delay,
                consecutive_failures,
            )
            self._stop_event.wait(delay)
