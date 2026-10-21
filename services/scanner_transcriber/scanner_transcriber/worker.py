"""Continuous worker coordinator connecting capture, ASR, SQLite storage, retention, and health."""

from __future__ import annotations

import collections
import datetime as dt
import logging
import queue
import threading
import time
import uuid
from typing import Any

from .asr import ASRBackend, build_asr_backend
from .capture import CapturedChunk, StreamCaptureRunner, format_utc
from .config import (
    ServiceConfig,
    redact_url,
    sanitize_diagnostic_text,
    source_origin_label,
)
from .storage import (
    FeedFileLock,
    ScannerStore,
    SegmentDraft,
    StorageFailureError,
    parse_utc,
    utc_now_iso,
)

logger = logging.getLogger(__name__)

VALID_HEALTH_STATUSES = frozenset(
    {
        "connecting",
        "receiving_audio",
        "no_speech_detected",
        "transcription_pending",
        "publishing",
        "upstream_unavailable",
        "asr_failure",
        "storage_failure",
        "stopped",
    }
)


class EventBroadcaster:
    """Thread-safe bounded fan-out pub/sub queue for optional SSE live clients."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: set[queue.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=128)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        msg = {"event": event_type, "data": payload, "at_utc": utc_now_iso()}
        with self._lock:
            targets = list(self._subscribers)
        for q in targets:
            try:
                q.put_nowait(msg)
            except queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait(msg)
                except Exception:
                    pass


class ScannerServiceRuntime:
    """Manages exclusive feed lock, capture loop, ASR worker, retention loop, and health state."""

    def __init__(
        self,
        config: ServiceConfig,
        *,
        asr_backend: ASRBackend | None = None,
        store: ScannerStore | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.session_id = str(uuid.uuid4())
        self.events = EventBroadcaster()

        self._state_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._chunk_queue: queue.Queue[CapturedChunk | None] = queue.Queue(
            maxsize=config.max_pending_chunks
        )

        self._feed_lock = FeedFileLock(config.lock_dir, config.feed.feed_id, self.session_id)
        self.store = store or ScannerStore(config.db_path)
        self._owns_store = store is None
        self.asr: ASRBackend | None = asr_backend

        self._status = "stopped"
        self._current_error: dict[str, str] | None = None
        self._last_audio_received_at: str | None = None
        self._last_transcribed_audio_end_at: str | None = None
        self._last_published_at: str | None = None
        self._last_capture_to_publish_ms: int | None = None
        self._in_flight_asr = 0
        self._asr_durations_ms: collections.deque[float] = collections.deque(maxlen=20)
        self._started_at_utc: str | None = None

        self._capture_thread: threading.Thread | None = None
        self._asr_thread: threading.Thread | None = None
        self._retention_thread: threading.Thread | None = None
        self._started = False

    def start(self) -> None:
        with self._state_lock:
            if self._started:
                return
            self._stop_event.clear()
            self._feed_lock.acquire()

        try:
            if self.asr is None:
                try:
                    self.asr = build_asr_backend(self.config)
                except Exception as exc:
                    self._set_fault("asr_failure", "asr_init_failed", str(exc))
                    raise

            now_iso = utc_now_iso()
            self._started_at_utc = now_iso
            recovery = self.store.recover_and_start_session(
                session_id=self.session_id,
                feed_id=self.config.feed.feed_id,
                feed_name=self.config.feed.feed_name,
                started_at_utc=now_iso,
                worker_revision=self.config.worker_revision,
            )
            if recovery.get("restart_gap"):
                self.events.publish("gap", recovery["restart_gap"])

            self._set_status("connecting", clear_error=True)

            self._asr_thread = threading.Thread(
                target=self._asr_worker_loop,
                name=f"scanner-asr-{self.config.feed.feed_id}",
                daemon=True,
            )
            self._capture_thread = threading.Thread(
                target=self._capture_worker_loop,
                name=f"scanner-capture-{self.config.feed.feed_id}",
                daemon=True,
            )
            self._retention_thread = threading.Thread(
                target=self._retention_worker_loop,
                name=f"scanner-retention-{self.config.feed.feed_id}",
                daemon=True,
            )
            self._started = True
            self._asr_thread.start()
            self._capture_thread.start()
            self._retention_thread.start()
        except Exception:
            self._feed_lock.release()
            raise

    def stop(self, timeout: float = 30.0) -> None:
        with self._state_lock:
            if not self._started:
                self._status = "stopped"
                self._feed_lock.release()
                if self._owns_store:
                    self.store.close()
                return
            self._started = False

        self._stop_event.set()
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=timeout)

        # Signal ASR worker to drain all queued chunks cleanly and finish publishing.
        try:
            self._chunk_queue.put(None, timeout=5.0)
        except queue.Full:
            pass
        if self._asr_thread is not None:
            self._asr_thread.join(timeout=timeout)
        if self._retention_thread is not None:
            self._retention_thread.join(timeout=5.0)

        try:
            self.store.close_session(self.session_id, utc_now_iso())
        except Exception as exc:
            logger.error("Error closing capture session %s: %s", self.session_id, exc)

        with self._state_lock:
            self._status = "stopped"
        self.events.publish("status", self.health_snapshot())
        self._feed_lock.release()
        if self._owns_store:
            self.store.close()

    def _set_status(self, status: str, *, clear_error: bool = False) -> None:
        assert status in VALID_HEALTH_STATUSES, f"Invalid status: {status}"
        with self._state_lock:
            self._status = status
            if clear_error:
                self._current_error = None
        self.events.publish("status", {"status": status, "at_utc": utc_now_iso()})

    def _set_fault(self, status: str, code: str, message: str) -> None:
        assert status in VALID_HEALTH_STATUSES
        safe_msg = sanitize_diagnostic_text(
            message,
            extra_secrets=tuple(
                s
                for s in (
                    self.config.api_token or "",
                    self.config.source_auth_header or "",
                )
                if s
            ),
        )
        err = {"code": code, "message": safe_msg[:400], "at_utc": utc_now_iso()}
        with self._state_lock:
            self._status = status
            self._current_error = err
        logger.error("Scanner status=%s code=%s message=%s", status, code, safe_msg)
        self.events.publish("status", {"status": status, "error": err})

    def _capture_worker_loop(self) -> None:
        runner = StreamCaptureRunner(
            self.config,
            session_id=self.session_id,
            on_chunk=self._enqueue_captured_chunk,
            on_audio_bytes=self._handle_audio_bytes,
            on_connecting=self._handle_connecting,
            on_upstream_error=self._handle_upstream_error,
            on_gap=self._handle_gap,
            stop_event=self._stop_event,
        )
        runner.run()

    def _handle_connecting(self, _attempt: int) -> None:
        with self._state_lock:
            if self._status not in ("upstream_unavailable", "storage_failure", "asr_failure"):
                self._status = "connecting"

    def _handle_audio_bytes(self, received_at: dt.datetime) -> None:
        ts = format_utc(received_at)
        with self._state_lock:
            self._last_audio_received_at = ts
            if self._status in ("connecting", "upstream_unavailable"):
                self._status = "receiving_audio"
                self._current_error = None

    def _handle_upstream_error(self, code: str, detail: str) -> None:
        self._set_fault("upstream_unavailable", code, detail)

    def _handle_gap(self, gap_start_utc: str, gap_end_utc: str, reason: str) -> None:
        try:
            gap = self.store.record_gap(
                feed_id=self.config.feed.feed_id,
                session_id=self.session_id,
                gap_start_utc=gap_start_utc,
                gap_end_utc=gap_end_utc,
                reason=reason,
            )
            if gap:
                self.events.publish("gap", gap)
        except StorageFailureError as exc:
            self._set_fault("storage_failure", "gap_persist_failed", str(exc))

    def _enqueue_captured_chunk(self, chunk: CapturedChunk) -> None:
        try:
            self._chunk_queue.put(chunk, timeout=5.0)
            with self._state_lock:
                if self._status in ("receiving_audio", "no_speech_detected"):
                    self._status = "transcription_pending"
        except queue.Full:
            # Never silently drop audio coverage: delete temporary WAV if needed and record explicit gap!
            chunk.wav_path.unlink(missing_ok=True)
            self._handle_gap(chunk.audio_start_utc, chunk.audio_end_utc, "queue_backpressure_drop")

    def _asr_worker_loop(self) -> None:
        while True:
            chunk = self._chunk_queue.get()
            if chunk is None:
                self._chunk_queue.task_done()
                break

            with self._state_lock:
                self._in_flight_asr += 1
                if self._status not in ("storage_failure",):
                    self._status = "transcription_pending"

            t0 = time.perf_counter()
            try:
                assert self.asr is not None
                result = self.asr.transcribe_wav(chunk.wav_path)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                with self._state_lock:
                    self._asr_durations_ms.append(elapsed_ms)
                    self._last_transcribed_audio_end_at = chunk.audio_end_utc
                    if self._status == "asr_failure":
                        self._current_error = None
            except Exception as exc:
                if not chunk.retained:
                    chunk.wav_path.unlink(missing_ok=True)
                self._set_fault("asr_failure", "asr_transcribe_failed", str(exc))
                try:
                    self._handle_gap(chunk.audio_start_utc, chunk.audio_end_utc, "asr_failure")
                    self.store.mark_non_speech_sequence_complete(
                        chunk.session_id, chunk.sequence_no, chunk.audio_end_utc
                    )
                except StorageFailureError as store_exc:
                    self._set_fault("storage_failure", "sequence_advance_failed", str(store_exc))
                finally:
                    with self._state_lock:
                        self._in_flight_asr = max(0, self._in_flight_asr - 1)
                    self._chunk_queue.task_done()
                continue

            # Remove temporary unretained WAV before publishing so no raw audio leaks on disk.
            if not chunk.retained:
                chunk.wav_path.unlink(missing_ok=True)

            try:
                if result.kind != "speech" or not result.text.strip():
                    newly_pub = self.store.mark_non_speech_sequence_complete(
                        chunk.session_id, chunk.sequence_no, chunk.audio_end_utc
                    )
                    for item in newly_pub:
                        self._record_published_item(item)
                    with self._state_lock:
                        if self._chunk_queue.empty() and self._status not in ("upstream_unavailable",):
                            self._status = "no_speech_detected"
                else:
                    self._set_status("publishing")
                    seg_id = str(
                        uuid.uuid5(
                            uuid.NAMESPACE_OID,
                            f"{chunk.session_id}:{chunk.sequence_no}:{chunk.audio_sha256}",
                        )
                    )
                    draft = SegmentDraft(
                        segment_id=seg_id,
                        feed_id=self.config.feed.feed_id,
                        feed_name=self.config.feed.feed_name,
                        session_id=chunk.session_id,
                        sequence_no=chunk.sequence_no,
                        audio_start_utc=chunk.audio_start_utc,
                        audio_end_utc=chunk.audio_end_utc,
                        duration_seconds=chunk.duration_seconds,
                        transcribed_at_utc=result.transcribed_at_utc,
                        asr_backend=result.asr_backend,
                        asr_model=result.asr_model,
                        language=result.language,
                        text=result.text,
                        verification_status="unverified_machine",
                        audio_sha256=chunk.audio_sha256,
                        audio_bytes=chunk.audio_bytes,
                        audio_retained=chunk.retained,
                        private_audio_ref=chunk.private_audio_ref,
                        private_audio_path=str(chunk.wav_path) if chunk.retained else None,
                        metrics=result.metrics,
                        inferred_tags=[],
                    )
                    published_row = self.store.persist_segment(draft)
                    if published_row.get("cursor") is not None:
                        self._record_published_item(published_row)
                    with self._state_lock:
                        if self._chunk_queue.empty() and self._status not in ("upstream_unavailable",):
                            self._status = "receiving_audio"
            except StorageFailureError as exc:
                self._set_fault("storage_failure", "segment_persist_failed", str(exc))
            finally:
                with self._state_lock:
                    self._in_flight_asr = max(0, self._in_flight_asr - 1)
                self._chunk_queue.task_done()

    def _record_published_item(self, item: dict[str, Any]) -> None:
        with self._state_lock:
            self._last_published_at = item.get("published_at_utc")
            self._last_capture_to_publish_ms = item.get("capture_to_publish_ms")
        self.events.publish("segment", item)

    def _retention_worker_loop(self) -> None:
        while not self._stop_event.wait(self.config.retention_sweep_interval_seconds):
            try:
                self.store.enforce_retention(
                    audio_retention_seconds=self.config.audio_retention_seconds,
                    transcript_retention_seconds=self.config.transcript_retention_seconds,
                )
            except StorageFailureError as exc:
                self._set_fault("storage_failure", "retention_failed", str(exc))

    def health_snapshot(self, now_utc: dt.datetime | None = None) -> dict[str, Any]:
        """Compute truthful operational health — never healthy merely because HTTP is listening."""
        ref_now = now_utc or dt.datetime.now(dt.timezone.utc)
        storage_ok = True
        unpublished_count = 0
        recent_gaps: list[dict[str, Any]] = []
        latest_cursor = 0
        total_published = 0

        try:
            self.store.ping()
            unpublished_count = self.store.count_unpublished(self.config.feed.feed_id)
            recent_gaps = self.store.list_recent_gaps(self.config.feed.feed_id, limit=10)
            summary = self.store.list_published_segments(self.config.feed.feed_id, limit=1)
            latest_cursor = summary["latest_cursor"]
            total_published = summary["total_published"]
        except Exception as exc:
            storage_ok = False
            with self._state_lock:
                self._status = "storage_failure"
                self._current_error = {
                    "code": "storage_health_check_failed",
                    "message": str(exc)[:400],
                    "at_utc": utc_now_iso(),
                }

        with self._state_lock:
            status = self._status
            last_audio = self._last_audio_received_at
            last_transcribed = self._last_transcribed_audio_end_at
            last_published = self._last_published_at
            last_lag_ms = self._last_capture_to_publish_ms
            in_flight = self._in_flight_asr
            queued = self._chunk_queue.qsize()
            mean_asr_ms = (
                sum(self._asr_durations_ms) / len(self._asr_durations_ms)
                if self._asr_durations_ms
                else 800.0
            )
            current_error = dict(self._current_error) if self._current_error else None

        pending_backlog = queued + in_flight + unpublished_count

        audio_age_seconds: float | None = None
        stale = True
        if last_audio is not None:
            audio_age_seconds = round(
                max(0.0, (ref_now - parse_utc(last_audio)).total_seconds()), 3
            )
            stale = audio_age_seconds > self.config.stale_after_seconds

        estimated_lag_ms: int | None
        if pending_backlog > 0:
            estimated_lag_ms = int(round(pending_backlog * mean_asr_ms + (last_lag_ms or 0)))
        else:
            estimated_lag_ms = last_lag_ms

        healthy = (
            storage_ok
            and status
            in ("receiving_audio", "no_speech_detected", "transcription_pending", "publishing")
            and not stale
            and current_error is None
        )

        configured_url = self.config.feed.direct_audio_url or self.config.feed.page_url
        source_type = (
            "direct_audio"
            if self.config.feed.direct_audio_url
            else ("page_url" if self.config.feed.page_url else "unconfigured")
        )

        return {
            "status": status,
            "healthy": healthy,
            "stale": stale,
            "checked_at_utc": format_utc(ref_now),
            "feed": {
                "feed_id": self.config.feed.feed_id,
                "feed_name": self.config.feed.feed_name,
                "source_type": source_type,
                "source_origin": source_origin_label(configured_url),
                "source_url_redacted": redact_url(configured_url),
                "source_authorized": self.config.feed.source_authorized,
                "attribution": self.config.feed.license_attribution,
            },
            "session_id": self.session_id,
            "worker_revision": self.config.worker_revision,
            "asr_model": self.asr.model_identifier if self.asr else self.config.asr_model_name,
            "last_audio_received_at": last_audio,
            "audio_age_seconds": audio_age_seconds,
            "stale_after_seconds": self.config.stale_after_seconds,
            "last_transcribed_audio_end_at": last_transcribed,
            "last_published_at": last_published,
            "pending_backlog": pending_backlog,
            "estimated_processing_lag_ms": estimated_lag_ms,
            "last_capture_to_publish_ms": last_lag_ms,
            "total_published_segments": total_published,
            "latest_cursor": latest_cursor,
            "current_error": current_error,
            "recent_gaps": recent_gaps,
            "disclaimer": (
                "Automatic radio transcription. May contain errors or omissions. "
                "Not verified dispatch information and not for emergency response."
            ),
        }
