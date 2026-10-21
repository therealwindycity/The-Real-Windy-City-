"""Comprehensive automated test suite for the Civic Cheyenne live scanner transcription service.

Covers:
1. Real faster-whisper ASR inference on redistributable speech fixtures with expected phrases.
2. Production mode rejection of stub/test backends and unauthenticated configs.
3. Silence and carrier-hum filtering (no invented incidents or hallucinated dispatch text).
4. Capture UTC timestamps surviving artificial ASR processing delay unchanged.
5. Idempotent deduplication on repeated publication and monotonic out-of-order publication cursors.
6. Exclusive OS feed locking (prevents duplicate concurrent workers for feed 47003).
7. Clean crash/restart session recovery, stranded staged-segment flush, and worker_restart gap recording.
8. Live local HTTP audio streaming end-to-end (ffmpeg -> faster-whisper -> SQLite -> API/SSE),
   mid-stream disconnect health transition (`upstream_unavailable` / HTTP 503 `/healthz`),
   bounded reconnect backoff, and explicit coverage gap reporting.
9. Explicit `asr_failure` and `storage_failure` visibility via API health endpoints.
10. Stale audio detection (`stale: True`, `healthy: False` beyond `stale_after_seconds`).
11. Independent raw-audio vs. transcript retention + truthful `audio_retained: False` after purge
    + verified online SQLite backup & restore.
12. Endpoint authentication enforcement, credential redaction, and anti-SSRF URL restrictions.
"""

from __future__ import annotations

import datetime as dt
import http.server
import os
import socketserver
import threading
import time
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from scanner_transcriber.asr import ASRChunkResult, FasterWhisperBackend
from scanner_transcriber.capture import (
    BYTES_PER_SECOND,
    compute_backoff_seconds,
    resolve_stream_url,
    write_pcm16_wav,
)
from scanner_transcriber.config import (
    ConfigurationError,
    FeedConfig,
    ServiceConfig,
    SourceRestrictionError,
    redact_url,
    validate_source_url,
)
from scanner_transcriber.storage import (
    FeedFileLock,
    FeedLockError,
    ScannerStore,
    SegmentDraft,
    StorageFailureError,
    parse_utc,
)
from scanner_transcriber.api import create_app
from scanner_transcriber.worker import ScannerServiceRuntime

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
JFK_WAV = FIXTURES_DIR / "jfk_16k.wav"
EVER_TRIED_WAV = FIXTURES_DIR / "ever_tried_16k.wav"


@pytest.fixture(scope="module")
def real_whisper_backend(tmp_path_factory: pytest.TempPathFactory) -> FasterWhisperBackend:
    cfg = ServiceConfig(
        environment="production",
        data_dir=tmp_path_factory.mktemp("asr-data"),
        api_token="prod-secret-token-for-init",
        asr_backend="faster-whisper",
        asr_model_name="tiny.en",
        asr_cpu_threads=2,
    )
    return FasterWhisperBackend(cfg)


class TestRealASRAndSilenceFiltering:
    def test_real_faster_whisper_produces_expected_phrases(
        self, real_whisper_backend: FasterWhisperBackend
    ) -> None:
        res1 = real_whisper_backend.transcribe_wav(JFK_WAV)
        assert res1.kind == "speech"
        assert res1.asr_backend == "faster-whisper"
        assert "faster-whisper" in res1.asr_model
        normalized1 = res1.text.lower()
        assert "stub" not in normalized1
        assert "fellow americans" in normalized1
        assert "ask not what your country can do for you" in normalized1
        assert "whisper_avg_logprob" in res1.metrics
        assert "NOT a calibrated" in str(res1.metrics.get("metric_note", ""))

        res2 = real_whisper_backend.transcribe_wav(EVER_TRIED_WAV)
        assert res2.kind == "speech"
        assert "ever tried" in res2.text.lower()

    def test_silence_and_low_hum_do_not_invent_incidents(
        self, real_whisper_backend: FasterWhisperBackend, tmp_path: Path
    ) -> None:
        # 1. Pure digital silence (6 seconds)
        silent_wav = tmp_path / "silence.wav"
        silent_pcm = np.zeros(16_000 * 6, dtype=np.int16).tobytes()
        write_pcm16_wav(silent_pcm, silent_wav)

        res_silent = real_whisper_backend.transcribe_wav(silent_wav)
        assert res_silent.kind == "no_speech"
        assert res_silent.text == ""
        assert res_silent.metrics.get("gate_reason") == "acoustic_silence"

        # 2. Low-level squelch noise / 60Hz hum (-56 dBFS)
        t = np.linspace(0.0, 5.0, 16_000 * 5, endpoint=False)
        hum = (np.sin(2 * np.pi * 60.0 * t) * 40.0).astype(np.int16).tobytes()
        hum_wav = tmp_path / "hum.wav"
        write_pcm16_wav(hum, hum_wav)

        res_hum = real_whisper_backend.transcribe_wav(hum_wav)
        assert res_hum.kind == "no_speech"
        assert res_hum.text == ""

    def test_production_strictly_rejects_stub_backend_and_missing_auth(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ConfigurationError, match="strictly rejects"):
            ServiceConfig(
                environment="production",
                data_dir=tmp_path,
                asr_backend="stub",
                api_token="secret-token",
            ).validate()

        with pytest.raises(ConfigurationError, match="SCANNER_API_TOKEN"):
            ServiceConfig(
                environment="production",
                data_dir=tmp_path,
                asr_backend="faster-whisper",
                require_auth=True,
                api_token=None,
            ).validate()

        with pytest.raises(ConfigurationError, match="SCANNER_SOURCE_AUTHORIZED"):
            ServiceConfig(
                environment="production",
                data_dir=tmp_path,
                api_token="secret-token",
                feed=FeedConfig(
                    feed_id="47003",
                    direct_audio_url="https://broadcastify.cdnstream1.com/47003",
                    source_authorized=False,
                ),
            ).validate()


class TestStorageOrderingRecoveryAndRetention:
    def test_idempotency_and_out_of_order_monotonic_publication(self, tmp_path: Path) -> None:
        store = ScannerStore(tmp_path / "db" / "scanner.sqlite3")
        try:
            store.recover_and_start_session(
                session_id="sess-order",
                feed_id="47003",
                feed_name="Laramie County Law Enforcement",
                started_at_utc="2026-10-21T17:00:00Z",
                worker_revision="test-rev",
            )

            # Sequence 1 finishes transcription BEFORE sequence 0!
            seg1 = SegmentDraft(
                segment_id="seg-1",
                feed_id="47003",
                feed_name="Laramie County Law Enforcement",
                session_id="sess-order",
                sequence_no=1,
                audio_start_utc="2026-10-21T17:00:10Z",
                audio_end_utc="2026-10-21T17:00:20Z",
                duration_seconds=10.0,
                transcribed_at_utc="2026-10-21T17:00:21Z",
                asr_backend="faster-whisper",
                asr_model="faster-whisper/tiny.en",
                language="en",
                text="Second chunk finished first",
                audio_sha256="b" * 64,
                audio_bytes=320000,
            )
            persisted1 = store.persist_segment(seg1)
            # Persisted on disk immediately, NOT yet published while seq 0 is still in flight!
            assert persisted1["cursor"] is None
            assert store.count_unpublished("47003") == 1
            assert store.list_published_segments("47003")["segments"] == []

            # Now sequence 0 finishes later — BOTH publish atomically in strict capture order (cursor 1 then cursor 2)!
            seg0 = SegmentDraft(
                segment_id="seg-0",
                feed_id="47003",
                feed_name="Laramie County Law Enforcement",
                session_id="sess-order",
                sequence_no=0,
                audio_start_utc="2026-10-21T17:00:00Z",
                audio_end_utc="2026-10-21T17:00:10Z",
                duration_seconds=10.0,
                transcribed_at_utc="2026-10-21T17:00:24Z",
                asr_backend="faster-whisper",
                asr_model="faster-whisper/tiny.en",
                language="en",
                text="First chunk finished second",
                audio_sha256="a" * 64,
                audio_bytes=320000,
            )
            store.persist_segment(seg0)
            published = store.list_published_segments("47003")["segments"]
            assert [p["segment_id"] for p in published] == ["seg-0", "seg-1"]
            assert [p["cursor"] for p in published] == [1, 2]

            # Repeated publication of seg-0 is strictly idempotent (no duplicate row).
            dup = store.persist_segment(seg0)
            assert dup["cursor"] == 1
            assert len(store.list_published_segments("47003")["segments"]) == 2
        finally:
            store.close()

    def test_crash_restart_recovery_and_exclusive_feed_lock(self, tmp_path: Path) -> None:
        lock1 = FeedFileLock(tmp_path / "locks", "47003", "session-a")
        lock2 = FeedFileLock(tmp_path / "locks", "47003", "session-b")
        lock1.acquire()
        try:
            with pytest.raises(FeedLockError, match="already locked"):
                lock2.acquire()
        finally:
            lock1.release()

        # After lock1 releases, lock2 acquires cleanly.
        lock2.acquire()
        lock2.release()

        db_path = tmp_path / "db" / "scanner.sqlite3"
        store1 = ScannerStore(db_path)
        store1.recover_and_start_session(
            session_id="crashed-session",
            feed_id="47003",
            feed_name="Laramie County Law Enforcement",
            started_at_utc="2026-10-21T17:10:00Z",
            worker_revision="rev1",
        )
        # Stage sequence 2 without seq 0/1 to simulate an abrupt process kill mid-backlog.
        store1.persist_segment(
            SegmentDraft(
                segment_id="stranded-seg",
                feed_id="47003",
                feed_name="Laramie County Law Enforcement",
                session_id="crashed-session",
                sequence_no=2,
                audio_start_utc="2026-10-21T17:10:20Z",
                audio_end_utc="2026-10-21T17:10:30Z",
                duration_seconds=10.0,
                transcribed_at_utc="2026-10-21T17:10:31Z",
                asr_backend="faster-whisper",
                asr_model="faster-whisper/tiny.en",
                language="en",
                text="Recovered after sudden crash",
                audio_sha256="c" * 64,
                audio_bytes=320000,
            )
        )
        store1.close()

        # New worker starts 45 seconds later: flushes stranded segment AND records explicit worker_restart gap!
        store2 = ScannerStore(db_path)
        try:
            rec = store2.recover_and_start_session(
                session_id="new-session",
                feed_id="47003",
                feed_name="Laramie County Law Enforcement",
                started_at_utc="2026-10-21T17:11:15Z",
                worker_revision="rev2",
            )
            assert rec["recovered_segments"] == 1
            assert rec["restart_gap"] is not None
            assert rec["restart_gap"]["reason"] == "worker_restart"
            assert rec["restart_gap"]["duration_seconds"] == pytest.approx(45.0)

            segs = store2.list_published_segments("47003")["segments"]
            assert len(segs) == 1
            assert segs[0]["segment_id"] == "stranded-seg"
            assert segs[0]["cursor"] == 1
        finally:
            store2.close()

    def test_independent_audio_and_transcript_retention_plus_backup_restore(
        self, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "db" / "scanner.sqlite3"
        store = ScannerStore(db_path)
        audio_dir = tmp_path / "private_audio" / "47003"
        audio_dir.mkdir(parents=True, exist_ok=True)
        old_wav = audio_dir / "old.wav"
        mid_wav = audio_dir / "mid.wav"
        fresh_wav = audio_dir / "fresh.wav"
        for p in (old_wav, mid_wav, fresh_wav):
            write_pcm16_wav(b"\x00\x00" * 1600, p)
            assert (p.stat().st_mode & 0o777) == 0o600

        base_now = dt.datetime(2026, 10, 21, 18, 0, 0, tzinfo=dt.timezone.utc)
        store.recover_and_start_session(
            session_id="ret-sess",
            feed_id="47003",
            feed_name="Laramie County Law Enforcement",
            started_at_utc="2026-10-10T00:00:00Z",
            worker_revision="rev1",
        )
        # Segment 0: 10 days old (exceeds both 24h audio retention and 7d transcript retention)
        # Segment 1: 2 days old (exceeds 24h audio retention, within 7d transcript retention!)
        # Segment 2: 10 minutes old (within both retentions!)
        entries = [
            (0, "seg-old", base_now - dt.timedelta(days=10), old_wav),
            (1, "seg-mid", base_now - dt.timedelta(days=2), mid_wav),
            (2, "seg-fresh", base_now - dt.timedelta(minutes=10), fresh_wav),
        ]
        for seq, sid, end_t, wav_p in entries:
            start_t = end_t - dt.timedelta(seconds=10)
            store.persist_segment(
                SegmentDraft(
                    segment_id=sid,
                    feed_id="47003",
                    feed_name="Laramie County Law Enforcement",
                    session_id="ret-sess",
                    sequence_no=seq,
                    audio_start_utc=start_t.isoformat().replace("+00:00", "Z"),
                    audio_end_utc=end_t.isoformat().replace("+00:00", "Z"),
                    duration_seconds=10.0,
                    transcribed_at_utc=end_t.isoformat().replace("+00:00", "Z"),
                    asr_backend="faster-whisper",
                    asr_model="faster-whisper/tiny.en",
                    language="en",
                    text=f"Transcript for {sid}",
                    audio_sha256=f"{seq}" * 64,
                    audio_bytes=3244,
                    audio_retained=True,
                    private_audio_ref=f"private://audio/47003/{wav_p.name}",
                    private_audio_path=str(wav_p),
                )
            )

        sweep = store.enforce_retention(
            audio_retention_seconds=24 * 3600,
            transcript_retention_seconds=7 * 86400,
            now_utc=base_now,
        )
        assert sweep["purged_audio_files"] == 2
        assert sweep["purged_transcript_segments"] == 1
        assert not old_wav.exists()
        assert not mid_wav.exists()
        assert fresh_wav.exists()

        remaining = store.list_published_segments("47003")["segments"]
        assert [s["segment_id"] for s in remaining] == ["seg-mid", "seg-fresh"]
        # Critical truth-in-retention check: seg-mid NEVER claims raw audio is still preserved!
        seg_mid = remaining[0]
        assert seg_mid["audio_retained"] is False
        assert seg_mid["private_audio_ref"] is None
        assert seg_mid["audio_purged_at_utc"] is not None
        assert "private_audio_path" not in seg_mid

        seg_fresh = remaining[1]
        assert seg_fresh["audio_retained"] is True
        assert seg_fresh["private_audio_ref"] == "private://audio/47003/fresh.wav"
        assert "private_audio_path" not in seg_fresh

        # Online hot backup & restore verification
        backup_file = tmp_path / "backups" / "scanner-backup.sqlite3"
        meta = store.backup_to(backup_file)
        assert meta["bytes"] > 0
        store.close()

        restored_db = tmp_path / "restored" / "scanner.sqlite3"
        ScannerStore.restore_from(backup_file, restored_db)
        restored_store = ScannerStore(restored_db)
        try:
            restored_segs = restored_store.list_published_segments("47003")["segments"]
            assert [s["segment_id"] for s in restored_segs] == ["seg-mid", "seg-fresh"]
        finally:
            restored_store.close()


class _DelayedRealASRWrapper:
    """Wraps the real FasterWhisperBackend with a controlled sleep to prove capture timestamps
    are recorded at sample-arrival time and never drift when ASR lags."""

    def __init__(self, inner: FasterWhisperBackend, delay_seconds: float) -> None:
        self._inner = inner
        self._delay = delay_seconds

    @property
    def backend_name(self) -> str:
        return self._inner.backend_name

    @property
    def model_identifier(self) -> str:
        return self._inner.model_identifier

    def transcribe_wav(self, wav_path: Path) -> ASRChunkResult:
        time.sleep(self._delay)
        return self._inner.transcribe_wav(wav_path)


class _FailingASRStub:
    @property
    def backend_name(self) -> str:
        return "faster-whisper"

    @property
    def model_identifier(self) -> str:
        return "faster-whisper/fault-injection"

    def transcribe_wav(self, _wav_path: Path) -> ASRChunkResult:
        raise RuntimeError("Simulated CTranslate2 decoder crash")


class TestLiveHTTPVerticalSliceFaultsAndSecurity:
    def test_url_restrictions_auth_and_credential_redaction(self, tmp_path: Path) -> None:
        # 1. URL allowlist & SSRF checks
        with pytest.raises(SourceRestrictionError, match="SCANNER_ALLOWED_HOSTS"):
            validate_source_url(
                "https://evil.example.org/stream.mp3",
                allowed_hosts=("broadcastify.cdnstream1.com",),
            )

        with pytest.raises(SourceRestrictionError, match="forbidden"):
            validate_source_url(
                "http://169.254.169.254/latest/meta-data/",
                allowed_hosts=("169.254.169.254",),
            )

        with pytest.raises(SourceRestrictionError, match="option injection"):
            validate_source_url("-http://127.0.0.1/stream.wav", allowed_hosts=("127.0.0.1",))

        with pytest.raises(ConfigurationError, match="never both"):
            ServiceConfig(
                environment="test",
                data_dir=tmp_path,
                feed=FeedConfig(
                    feed_id="47003",
                    direct_audio_url="http://127.0.0.1:9000/a.mp3",
                    page_url="http://127.0.0.1:9000/live",
                ),
            ).validate()

        redacted = redact_url(
            "https://user:supersecret@broadcastify.cdnstream1.com/47003?token=mysecret&format=mp3"
        )
        assert redacted == "https://broadcastify.cdnstream1.com/47003?token=REDACTED&format=mp3"
        assert "supersecret" not in redacted
        assert "mysecret" not in redacted

    def test_end_to_end_http_stream_delay_timestamps_disconnect_and_api_auth(
        self, real_whisper_backend: FasterWhisperBackend, tmp_path: Path
    ) -> None:
        # Serve real JFK speech PCM streamed over a live local HTTP endpoint, then drop upstream!
        with wave.open(str(JFK_WAV), "rb") as wf:
            pcm_payload = wf.readframes(wf.getnframes())

        served_once = threading.Event()
        allow_stream = {"enabled": True}

        class LiveRadioHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if not allow_stream["enabled"]:
                    self.send_response(503)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.end_headers()
                # Write standard WAV header followed by real-time paced chunks
                import io

                hdr_buf = io.BytesIO()
                with wave.open(hdr_buf, "wb") as out_w:
                    out_w.setnchannels(1)
                    out_w.setsampwidth(2)
                    out_w.setframerate(16_000)
                    out_w.writeframes(pcm_payload)
                full_wav = hdr_buf.getvalue()
                step = BYTES_PER_SECOND // 4  # 0.25s chunks
                try:
                    for offset in range(0, len(full_wav), step):
                        self.wfile.write(full_wav[offset : offset + step])
                        self.wfile.flush()
                        time.sleep(0.05)
                    served_once.set()
                    # After delivering full speech, disable upstream to force disconnect state!
                    allow_stream["enabled"] = False
                except BrokenPipeError:
                    pass

            def log_message(self, _fmt: str, *_args: object) -> None:
                return

        httpd = socketserver.TCPServer(("127.0.0.1", 0), LiveRadioHandler)
        port = httpd.server_address[1]
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()

        delayed_asr = _DelayedRealASRWrapper(real_whisper_backend, delay_seconds=1.1)
        cfg = ServiceConfig(
            environment="production",
            data_dir=tmp_path / "live-e2e",
            api_token="top-secret-bearer-2026",
            require_auth=True,
            source_auth_header="Basic dXNlcjpwYXNz",
            allowed_hosts=("127.0.0.1",),
            chunk_seconds=5.5,
            min_flush_seconds=1.0,
            read_timeout_seconds=3.0,
            stale_after_seconds=2.5,
            reconnect_initial_seconds=0.4,
            reconnect_max_seconds=1.2,
            feed=FeedConfig(
                feed_id="47003",
                feed_name="Laramie County Law Enforcement",
                direct_audio_url=f"http://127.0.0.1:{port}/47003.wav?token=upstreamsecret",
                source_authorized=True,
            ),
            worker_revision="test-sha-001",
        )

        runtime = ScannerServiceRuntime(cfg, asr_backend=delayed_asr)
        app = create_app(runtime)
        auth_headers = {"Authorization": "Bearer top-secret-bearer-2026"}

        try:
            runtime.start()
            with TestClient(app) as client:
                # 1. Access control checks
                assert client.get("/api/scanner/health").status_code == 401
                assert (
                    client.get(
                        "/api/scanner/health",
                        headers={"Authorization": "Bearer wrong-token"},
                    ).status_code
                    == 401
                )
                # Anti-SSRF arbitrary URL parameter check
                ssrf_resp = client.get(
                    "/api/scanner/feeds/47003/segments?url=http://169.254.169.254/",
                    headers=auth_headers,
                )
                assert ssrf_resp.status_code == 403

                # Wait for real speech segments + disconnect transition
                deadline = time.monotonic() + 25.0
                segments = []
                saw_disconnect = False
                while time.monotonic() < deadline:
                    resp = client.get(
                        "/api/scanner/feeds/47003/segments?limit=20",
                        headers=auth_headers,
                    )
                    assert resp.status_code == 200
                    body = resp.json()
                    # Verify secrets NEVER appear in API JSON!
                    serialized = str(body)
                    assert "upstreamsecret" not in serialized
                    assert "dXNlcjpwYXNz" not in serialized
                    assert "top-secret-bearer-2026" not in serialized

                    segments = body["segments"]
                    h_status = body["health"]["status"]
                    if len(segments) >= 1 and h_status == "upstream_unavailable":
                        saw_disconnect = True
                        break
                    time.sleep(0.3)

                assert len(segments) >= 1, "Expected real faster-whisper segment from HTTP stream"
                full_transcript = " ".join(s["text"].lower() for s in segments)
                assert "fellow americans" in full_transcript or "country" in full_transcript

                # Verify capture timestamps survived the 1.1s artificial ASR delay!
                first_seg = segments[0]
                audio_end = parse_utc(first_seg["audio_end_utc"])
                transcribed_at = parse_utc(first_seg["transcribed_at_utc"])
                assert (transcribed_at - audio_end).total_seconds() >= 1.0
                assert first_seg["capture_to_publish_ms"] >= 1000
                assert first_seg["verification_status"] == "unverified_machine"
                assert first_seg["inferred_tags"] == []

                # Verify cursor polling returns strictly newer segments only!
                cursor_zero = client.get(
                    "/api/scanner/feeds/47003/segments?after_cursor=0&limit=1",
                    headers=auth_headers,
                ).json()
                assert len(cursor_zero["segments"]) == 1
                c1 = cursor_zero["next_cursor"]
                cursor_after_all = client.get(
                    f"/api/scanner/feeds/47003/segments?after_cursor={body['latest_cursor']}",
                    headers=auth_headers,
                ).json()
                assert cursor_after_all["segments"] == []
                assert c1 >= 1

                # Verify upstream disconnect sets health unhealthy & /healthz returns 503!
                assert saw_disconnect is True
                healthz = client.get("/healthz")
                assert healthz.status_code == 503
                assert healthz.json()["healthy"] is False
                assert healthz.json()["status"] == "upstream_unavailable"
                assert healthz.json()["current_error"] is not None

                # Wait past stale_after_seconds (2.5s) and verify `stale: True` is reported honestly!
                time.sleep(2.7)
                stale_health = client.get("/api/scanner/health", headers=auth_headers).json()
                assert stale_health["stale"] is True
                assert stale_health["healthy"] is False
        finally:
            runtime.stop()
            httpd.shutdown()
            httpd.server_close()

    def test_asr_failure_and_storage_failure_are_explicitly_visible(self, tmp_path: Path) -> None:
        wav_fixture = tmp_path / "speech_local.wav"
        wav_fixture.write_bytes(JFK_WAV.read_bytes())

        cfg = ServiceConfig(
            environment="test",
            data_dir=tmp_path / "fault-run",
            require_auth=False,
            allow_file_sources=True,
            chunk_seconds=2.0,
            feed=FeedConfig(
                feed_id="47003",
                feed_name="Laramie County Law Enforcement",
                direct_audio_url=f"file://{wav_fixture}",
                source_authorized=True,
            ),
        )
        runtime = ScannerServiceRuntime(cfg, asr_backend=_FailingASRStub())
        app = create_app(runtime)
        try:
            runtime.start()
            with TestClient(app) as client:
                deadline = time.monotonic() + 12.0
                saw_asr_failure = False
                while time.monotonic() < deadline:
                    snap = client.get("/api/scanner/health").json()
                    if (
                        snap["current_error"]
                        and snap["current_error"]["code"] == "asr_transcribe_failed"
                    ):
                        saw_asr_failure = True
                        assert snap["healthy"] is False
                        assert any(g["reason"] == "asr_failure" for g in snap["recent_gaps"])
                        break
                    time.sleep(0.25)
                assert saw_asr_failure, "Expected visible asr_failure error and gap"

                # Now close the underlying SQLite connection to trigger real storage_failure!
                runtime.store.close()
                healthz = client.get("/healthz")
                assert healthz.status_code == 503
                snap_storage = healthz.json()
                assert snap_storage["status"] == "storage_failure"
                assert snap_storage["healthy"] is False
        finally:
            runtime.stop()

    def test_backoff_is_strictly_bounded(self) -> None:
        delays = [
            compute_backoff_seconds(attempt, initial_seconds=1.0, multiplier=2.0, max_seconds=30.0)
            for attempt in range(1, 10)
        ]
        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0, 30.0]
        assert max(delays) <= 30.0
