"""Durable SQLite storage, single-worker feed locking, monotonic publication, retention, and backup."""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class FeedLockError(RuntimeError):
    """Raised when another worker process already holds the exclusive lock for a feed."""


class StorageFailureError(RuntimeError):
    """Raised when durable SQLite persistence fails."""


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(ts: str) -> dt.datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(ts)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


class FeedFileLock:
    """OS-level exclusive flock preventing duplicate capture workers for the same feed."""

    def __init__(self, lock_dir: Path, feed_id: str, session_id: str) -> None:
        self._lock_dir = lock_dir
        self._feed_id = feed_id
        self._session_id = session_id
        self._fd: int | None = None
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in feed_id)
        self.lock_path = lock_dir / f"feed-{safe_id}.lock"

    def acquire(self) -> None:
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self._lock_dir, 0o700)
        except OSError:
            pass
        fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            owner_info = ""
            try:
                owner_info = os.pread(fd, 512, 0).decode("utf-8", errors="replace").strip()
            except OSError:
                pass
            os.close(fd)
            raise FeedLockError(
                f"Feed {self._feed_id!r} is already locked by another active worker "
                f"({owner_info or str(self.lock_path)})."
            ) from exc

        payload = json.dumps(
            {
                "pid": os.getpid(),
                "feed_id": self._feed_id,
                "session_id": self._session_id,
                "acquired_at_utc": utc_now_iso(),
            }
        ).encode("utf-8")
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, payload)
        os.fsync(fd)
        self._fd = fd

    def release(self) -> None:
        if self._fd is not None:
            fd = self._fd
            self._fd = None
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(fd)
            except OSError:
                pass


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS capture_sessions (
    session_id TEXT PRIMARY KEY,
    feed_id TEXT NOT NULL,
    feed_name TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    stopped_at_utc TEXT,
    status TEXT NOT NULL,
    worker_pid INTEGER NOT NULL,
    worker_revision TEXT NOT NULL,
    last_audio_end_utc TEXT
);

CREATE TABLE IF NOT EXISTS segments (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    published_seq INTEGER UNIQUE,
    segment_id TEXT NOT NULL UNIQUE,
    feed_id TEXT NOT NULL,
    feed_name TEXT NOT NULL,
    session_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    audio_start_utc TEXT NOT NULL,
    audio_end_utc TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    transcribed_at_utc TEXT NOT NULL,
    published_at_utc TEXT,
    capture_to_publish_ms INTEGER,
    asr_backend TEXT NOT NULL,
    asr_model TEXT NOT NULL,
    language TEXT NOT NULL,
    text TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'unverified_machine',
    audio_sha256 TEXT,
    audio_bytes INTEGER,
    audio_retained INTEGER NOT NULL DEFAULT 0,
    private_audio_ref TEXT,
    private_audio_path TEXT,
    audio_purged_at_utc TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    inferred_tags_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE(session_id, sequence_no),
    UNIQUE(feed_id, audio_start_utc, audio_end_utc, audio_sha256)
);

CREATE INDEX IF NOT EXISTS idx_segments_feed_pub
    ON segments(feed_id, published_seq);
CREATE INDEX IF NOT EXISTS idx_segments_audio_end
    ON segments(audio_end_utc);

CREATE TABLE IF NOT EXISTS capture_gaps (
    gap_id TEXT PRIMARY KEY,
    feed_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    gap_start_utc TEXT NOT NULL,
    gap_end_utc TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    reason TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gaps_feed_end
    ON capture_gaps(feed_id, gap_end_utc DESC);
"""


@dataclass(frozen=True)
class SegmentDraft:
    segment_id: str
    feed_id: str
    feed_name: str
    session_id: str
    sequence_no: int
    audio_start_utc: str
    audio_end_utc: str
    duration_seconds: float
    transcribed_at_utc: str
    asr_backend: str
    asr_model: str
    language: str
    text: str
    verification_status: str = "unverified_machine"
    audio_sha256: str | None = None
    audio_bytes: int | None = None
    audio_retained: bool = False
    private_audio_ref: str | None = None
    private_audio_path: str | None = None
    metrics: dict[str, Any] | None = None
    inferred_tags: list[str] | None = None


class ScannerStore:
    """Thread-safe SQLite store guaranteeing persist-before-publish, idempotency, and ordered cursors."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        # Track completed non-speech / failed sequence numbers per session so out-of-order
        # transcription of speech segments still publishes strictly in sequence order.
        self._completed_sequences: dict[str, set[int]] = {}
        self._next_expected_seq: dict[str, int] = {}
        self._open()

    def _open(self) -> None:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(self.db_path.parent, 0o700)
            except OSError:
                pass
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=FULL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute("PRAGMA busy_timeout=5000;")
            conn.executescript(SCHEMA_SQL)
            conn.commit()
            try:
                os.chmod(self.db_path, 0o600)
            except OSError:
                pass
            self._conn = conn
        except Exception as exc:
            raise StorageFailureError(f"Failed to initialize SQLite storage at {self.db_path}: {exc}") from exc

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise StorageFailureError("SQLite connection is closed.")
        return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None

    def ping(self) -> None:
        with self._lock:
            try:
                self.conn.execute("SELECT 1;").fetchone()
            except Exception as exc:
                raise StorageFailureError(f"Storage health check failed: {exc}") from exc

    def recover_and_start_session(
        self,
        *,
        session_id: str,
        feed_id: str,
        feed_name: str,
        started_at_utc: str,
        worker_revision: str,
    ) -> dict[str, Any]:
        """Recover any prior unclosed session, publish any stranded staged segments, and record restart gap."""
        with self._lock:
            try:
                prev = self.conn.execute(
                    """
                    SELECT session_id, started_at_utc, stopped_at_utc, status, last_audio_end_utc
                    FROM capture_sessions
                    WHERE feed_id = ?
                    ORDER BY started_at_utc DESC, rowid DESC
                    LIMIT 1
                    """,
                    (feed_id,),
                ).fetchone()

                recovered_segments = 0
                restart_gap: dict[str, Any] | None = None

                if prev is not None and prev["status"] == "active":
                    self.conn.execute(
                        """
                        UPDATE capture_sessions
                        SET status = 'recovered_after_crash', stopped_at_utc = ?
                        WHERE session_id = ?
                        """,
                        (started_at_utc, prev["session_id"]),
                    )

                # Publish any staged rows left unpublished by an earlier session in strict capture order.
                unpublished = self.conn.execute(
                    """
                    SELECT row_id, audio_end_utc
                    FROM segments
                    WHERE feed_id = ? AND published_seq IS NULL
                    ORDER BY audio_start_utc ASC, sequence_no ASC, row_id ASC
                    """,
                    (feed_id,),
                ).fetchall()
                for row in unpublished:
                    self._assign_next_publication_seq(row["row_id"], row["audio_end_utc"])
                    recovered_segments += 1

                # Record explicit restart coverage gap if prior audio existed before this session started.
                if prev is not None and prev["last_audio_end_utc"]:
                    gap_start = prev["last_audio_end_utc"]
                    gap_dur = (parse_utc(started_at_utc) - parse_utc(gap_start)).total_seconds()
                    if gap_dur > 0.25:
                        gap_id = str(uuid.uuid4())
                        self.conn.execute(
                            """
                            INSERT INTO capture_gaps (
                                gap_id, feed_id, session_id, gap_start_utc, gap_end_utc,
                                duration_seconds, reason, recorded_at_utc
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                gap_id,
                                feed_id,
                                session_id,
                                gap_start,
                                started_at_utc,
                                round(gap_dur, 3),
                                "worker_restart",
                                utc_now_iso(),
                            ),
                        )
                        restart_gap = {
                            "gap_id": gap_id,
                            "feed_id": feed_id,
                            "session_id": session_id,
                            "gap_start_utc": gap_start,
                            "gap_end_utc": started_at_utc,
                            "duration_seconds": round(gap_dur, 3),
                            "reason": "worker_restart",
                        }

                self.conn.execute(
                    """
                    INSERT INTO capture_sessions (
                        session_id, feed_id, feed_name, started_at_utc, status, worker_pid, worker_revision
                    ) VALUES (?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (session_id, feed_id, feed_name, started_at_utc, os.getpid(), worker_revision),
                )
                self.conn.commit()
                self._completed_sequences[session_id] = set()
                self._next_expected_seq[session_id] = 0
                return {
                    "recovered_segments": recovered_segments,
                    "restart_gap": restart_gap,
                }
            except StorageFailureError:
                raise
            except Exception as exc:
                self.conn.rollback()
                raise StorageFailureError(f"Session startup/recovery failed: {exc}") from exc

    def update_session_audio_progress(self, session_id: str, audio_end_utc: str) -> None:
        with self._lock:
            try:
                self.conn.execute(
                    "UPDATE capture_sessions SET last_audio_end_utc = ? WHERE session_id = ?",
                    (audio_end_utc, session_id),
                )
                self.conn.commit()
            except Exception as exc:
                self.conn.rollback()
                raise StorageFailureError(f"Failed updating session progress: {exc}") from exc

    def close_session(self, session_id: str, stopped_at_utc: str | None = None) -> None:
        with self._lock:
            try:
                # Flush any remaining unpublished segments for this session before marking stopped.
                self._flush_session_unpublished_locked(session_id)
                self.conn.execute(
                    """
                    UPDATE capture_sessions
                    SET status = 'stopped', stopped_at_utc = ?
                    WHERE session_id = ?
                    """,
                    (stopped_at_utc or utc_now_iso(), session_id),
                )
                self.conn.commit()
                self._completed_sequences.pop(session_id, None)
                self._next_expected_seq.pop(session_id, None)
            except Exception as exc:
                self.conn.rollback()
                raise StorageFailureError(f"Failed closing session {session_id}: {exc}") from exc

    def record_gap(
        self,
        *,
        feed_id: str,
        session_id: str,
        gap_start_utc: str,
        gap_end_utc: str,
        reason: str,
    ) -> dict[str, Any] | None:
        dur = (parse_utc(gap_end_utc) - parse_utc(gap_start_utc)).total_seconds()
        if dur <= 0.05:
            return None
        gap_id = str(uuid.uuid4())
        recorded_at = utc_now_iso()
        with self._lock:
            try:
                self.conn.execute(
                    """
                    INSERT INTO capture_gaps (
                        gap_id, feed_id, session_id, gap_start_utc, gap_end_utc,
                        duration_seconds, reason, recorded_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        gap_id,
                        feed_id,
                        session_id,
                        gap_start_utc,
                        gap_end_utc,
                        round(dur, 3),
                        reason,
                        recorded_at,
                    ),
                )
                self.conn.commit()
                return {
                    "gap_id": gap_id,
                    "feed_id": feed_id,
                    "session_id": session_id,
                    "gap_start_utc": gap_start_utc,
                    "gap_end_utc": gap_end_utc,
                    "duration_seconds": round(dur, 3),
                    "reason": reason,
                    "recorded_at_utc": recorded_at,
                }
            except Exception as exc:
                self.conn.rollback()
                raise StorageFailureError(f"Failed recording capture gap: {exc}") from exc

    def persist_segment(self, draft: SegmentDraft) -> dict[str, Any]:
        """Persist a segment durably first (published_seq=NULL), deduplicating idempotently,
        then publish contiguous ready sequence numbers in strict monotonic order."""
        with self._lock:
            try:
                existing = self.conn.execute(
                    """
                    SELECT * FROM segments
                    WHERE segment_id = ?
                       OR (session_id = ? AND sequence_no = ?)
                       OR (
                            feed_id = ?
                        AND audio_start_utc = ?
                        AND audio_end_utc = ?
                        AND audio_sha256 IS NOT NULL
                        AND audio_sha256 = ?
                       )
                    LIMIT 1
                    """,
                    (
                        draft.segment_id,
                        draft.session_id,
                        draft.sequence_no,
                        draft.feed_id,
                        draft.audio_start_utc,
                        draft.audio_end_utc,
                        draft.audio_sha256,
                    ),
                ).fetchone()

                if existing is not None:
                    self._mark_sequence_ready_locked(draft.session_id, draft.sequence_no)
                    self.conn.commit()
                    refreshed = self.conn.execute(
                        "SELECT * FROM segments WHERE row_id = ?", (existing["row_id"],)
                    ).fetchone()
                    return self._row_to_public_dict(refreshed)

                # Step 1: Durably persist BEFORE assigning published_seq!
                cur = self.conn.execute(
                    """
                    INSERT INTO segments (
                        published_seq, segment_id, feed_id, feed_name, session_id, sequence_no,
                        audio_start_utc, audio_end_utc, duration_seconds, transcribed_at_utc,
                        asr_backend, asr_model, language, text, verification_status,
                        audio_sha256, audio_bytes, audio_retained, private_audio_ref,
                        private_audio_path, metrics_json, inferred_tags_json
                    ) VALUES (
                        NULL, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?
                    )
                    """,
                    (
                        draft.segment_id,
                        draft.feed_id,
                        draft.feed_name,
                        draft.session_id,
                        draft.sequence_no,
                        draft.audio_start_utc,
                        draft.audio_end_utc,
                        round(draft.duration_seconds, 3),
                        draft.transcribed_at_utc,
                        draft.asr_backend,
                        draft.asr_model,
                        draft.language,
                        draft.text,
                        draft.verification_status,
                        draft.audio_sha256,
                        draft.audio_bytes,
                        1 if draft.audio_retained else 0,
                        draft.private_audio_ref if draft.audio_retained else None,
                        draft.private_audio_path if draft.audio_retained else None,
                        json.dumps(draft.metrics or {}, sort_keys=True),
                        json.dumps(draft.inferred_tags or []),
                    ),
                )
                row_id = cur.lastrowid
                self.conn.execute(
                    "UPDATE capture_sessions SET last_audio_end_utc = ? WHERE session_id = ?",
                    (draft.audio_end_utc, draft.session_id),
                )
                self.conn.commit()

                # Step 2: Advance contiguous monotonic publication window.
                self._mark_sequence_ready_locked(draft.session_id, draft.sequence_no)
                self.conn.commit()

                saved = self.conn.execute(
                    "SELECT * FROM segments WHERE row_id = ?", (row_id,)
                ).fetchone()
                return self._row_to_public_dict(saved)
            except StorageFailureError:
                raise
            except Exception as exc:
                self.conn.rollback()
                raise StorageFailureError(f"Failed persisting segment {draft.segment_id}: {exc}") from exc

    def mark_non_speech_sequence_complete(
        self, session_id: str, sequence_no: int, audio_end_utc: str | None = None
    ) -> list[dict[str, Any]]:
        """Record that a non-speech or failed sequence slot finished so subsequent speech chunks publish in order."""
        with self._lock:
            try:
                if audio_end_utc:
                    self.conn.execute(
                        "UPDATE capture_sessions SET last_audio_end_utc = ? WHERE session_id = ?",
                        (audio_end_utc, session_id),
                    )
                newly_published = self._mark_sequence_ready_locked(session_id, sequence_no)
                self.conn.commit()
                return newly_published
            except Exception as exc:
                self.conn.rollback()
                raise StorageFailureError(f"Failed advancing sequence state: {exc}") from exc

    def _assign_next_publication_seq(self, row_id: int, audio_end_utc: str) -> dict[str, Any]:
        max_row = self.conn.execute("SELECT COALESCE(MAX(published_seq), 0) AS m FROM segments").fetchone()
        next_pub = int(max_row["m"]) + 1
        published_at = utc_now_iso()
        lag_ms = max(
            0, int(round((parse_utc(published_at) - parse_utc(audio_end_utc)).total_seconds() * 1000))
        )
        self.conn.execute(
            """
            UPDATE segments
            SET published_seq = ?, published_at_utc = ?, capture_to_publish_ms = ?
            WHERE row_id = ? AND published_seq IS NULL
            """,
            (next_pub, published_at, lag_ms, row_id),
        )
        updated = self.conn.execute("SELECT * FROM segments WHERE row_id = ?", (row_id,)).fetchone()
        return self._row_to_public_dict(updated)

    def _mark_sequence_ready_locked(self, session_id: str, sequence_no: int) -> list[dict[str, Any]]:
        done_set = self._completed_sequences.setdefault(session_id, set())
        done_set.add(sequence_no)
        expected = self._next_expected_seq.setdefault(session_id, 0)
        published_now: list[dict[str, Any]] = []

        while expected in done_set:
            staged = self.conn.execute(
                """
                SELECT row_id, audio_end_utc
                FROM segments
                WHERE session_id = ? AND sequence_no = ? AND published_seq IS NULL
                """,
                (session_id, expected),
            ).fetchone()
            if staged is not None:
                published_now.append(
                    self._assign_next_publication_seq(staged["row_id"], staged["audio_end_utc"])
                )
            done_set.discard(expected)
            expected += 1

        self._next_expected_seq[session_id] = expected
        return published_now

    def _flush_session_unpublished_locked(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT row_id, audio_end_utc
            FROM segments
            WHERE session_id = ? AND published_seq IS NULL
            ORDER BY sequence_no ASC, audio_start_utc ASC, row_id ASC
            """,
            (session_id,),
        ).fetchall()
        out = []
        for row in rows:
            out.append(self._assign_next_publication_seq(row["row_id"], row["audio_end_utc"]))
        return out

    def flush_session(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            try:
                out = self._flush_session_unpublished_locked(session_id)
                self.conn.commit()
                return out
            except Exception as exc:
                self.conn.rollback()
                raise StorageFailureError(f"Failed flushing staged segments: {exc}") from exc

    def list_published_segments(
        self,
        feed_id: str,
        *,
        limit: int = 50,
        after_cursor: int | None = None,
    ) -> dict[str, Any]:
        """Return published segments in monotonic cursor order."""
        clamped_limit = max(1, min(200, int(limit)))
        with self._lock:
            try:
                if after_cursor is not None:
                    rows = self.conn.execute(
                        """
                        SELECT * FROM segments
                        WHERE feed_id = ? AND published_seq IS NOT NULL AND published_seq > ?
                        ORDER BY published_seq ASC
                        LIMIT ?
                        """,
                        (feed_id, int(after_cursor), clamped_limit + 1),
                    ).fetchall()
                    has_more = len(rows) > clamped_limit
                    sliced = rows[:clamped_limit]
                else:
                    # Latest N published segments returned in ascending monotonic publication order.
                    rows = self.conn.execute(
                        """
                        SELECT * FROM (
                            SELECT * FROM segments
                            WHERE feed_id = ? AND published_seq IS NOT NULL
                            ORDER BY published_seq DESC
                            LIMIT ?
                        )
                        ORDER BY published_seq ASC
                        """,
                        (feed_id, clamped_limit),
                    ).fetchall()
                    has_more = False
                    sliced = rows

                items = [self._row_to_public_dict(r) for r in sliced]
                latest_row = self.conn.execute(
                    """
                    SELECT COALESCE(MAX(published_seq), 0) AS latest_cursor,
                           COUNT(*) AS total_count
                    FROM segments
                    WHERE feed_id = ? AND published_seq IS NOT NULL
                    """,
                    (feed_id,),
                ).fetchone()
                next_cursor = (
                    items[-1]["cursor"]
                    if items
                    else (after_cursor if after_cursor is not None else int(latest_row["latest_cursor"]))
                )
                return {
                    "segments": items,
                    "next_cursor": int(next_cursor),
                    "latest_cursor": int(latest_row["latest_cursor"]),
                    "total_published": int(latest_row["total_count"]),
                    "has_more": has_more,
                }
            except Exception as exc:
                raise StorageFailureError(f"Failed querying segments: {exc}") from exc

    def count_unpublished(self, feed_id: str) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT COUNT(*) AS c FROM segments WHERE feed_id = ? AND published_seq IS NULL",
                (feed_id,),
            ).fetchone()
            return int(row["c"])

    def list_recent_gaps(self, feed_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT gap_id, feed_id, session_id, gap_start_utc, gap_end_utc,
                       duration_seconds, reason, recorded_at_utc
                FROM capture_gaps
                WHERE feed_id = ?
                ORDER BY gap_end_utc DESC
                LIMIT ?
                """,
                (feed_id, max(1, min(100, int(limit)))),
            ).fetchall()
            return [dict(r) for r in rows]

    def enforce_retention(
        self,
        *,
        audio_retention_seconds: int,
        transcript_retention_seconds: int,
        now_utc: dt.datetime | None = None,
    ) -> dict[str, int]:
        """Apply independent retention to private raw audio files and persisted transcripts."""
        ref_now = now_utc or dt.datetime.now(dt.timezone.utc)
        audio_cutoff_iso = (
            ref_now - dt.timedelta(seconds=max(0, audio_retention_seconds))
        ).isoformat().replace("+00:00", "Z")
        transcript_cutoff_iso = (
            ref_now - dt.timedelta(seconds=max(1, transcript_retention_seconds))
        ).isoformat().replace("+00:00", "Z")
        purged_at_iso = ref_now.isoformat().replace("+00:00", "Z")

        purged_audio = 0
        purged_transcripts = 0

        with self._lock:
            try:
                # 1. Purge expired private audio files and truthfully clear audio_retained/private_audio_ref!
                expired_audio = self.conn.execute(
                    """
                    SELECT row_id, private_audio_path
                    FROM segments
                    WHERE audio_retained = 1 AND audio_end_utc <= ?
                    """,
                    (audio_cutoff_iso,),
                ).fetchall()

                for row in expired_audio:
                    audio_path = row["private_audio_path"]
                    if audio_path:
                        try:
                            Path(audio_path).unlink(missing_ok=True)
                        except OSError:
                            pass
                    self.conn.execute(
                        """
                        UPDATE segments
                        SET audio_retained = 0,
                            private_audio_ref = NULL,
                            private_audio_path = NULL,
                            audio_purged_at_utc = ?
                        WHERE row_id = ?
                        """,
                        (purged_at_iso, row["row_id"]),
                    )
                    purged_audio += 1

                # 2. Delete expired transcript segments & delete any associated private audio file too.
                expired_segments = self.conn.execute(
                    """
                    SELECT row_id, private_audio_path
                    FROM segments
                    WHERE audio_end_utc <= ?
                    """,
                    (transcript_cutoff_iso,),
                ).fetchall()

                for row in expired_segments:
                    if row["private_audio_path"]:
                        try:
                            Path(row["private_audio_path"]).unlink(missing_ok=True)
                        except OSError:
                            pass
                if expired_segments:
                    cur = self.conn.execute(
                        "DELETE FROM segments WHERE audio_end_utc <= ?",
                        (transcript_cutoff_iso,),
                    )
                    purged_transcripts = cur.rowcount or 0

                self.conn.commit()
                return {
                    "purged_audio_files": purged_audio,
                    "purged_transcript_segments": purged_transcripts,
                }
            except Exception as exc:
                self.conn.rollback()
                raise StorageFailureError(f"Retention sweep failed: {exc}") from exc

    def backup_to(self, destination_path: Path) -> dict[str, Any]:
        """Create a consistent hot backup using sqlite3's online backup API and verify integrity."""
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            dest_conn = sqlite3.connect(str(destination_path))
            try:
                self.conn.backup(dest_conn)
                dest_conn.commit()
                check = dest_conn.execute("PRAGMA integrity_check;").fetchone()[0]
                if check != "ok":
                    raise StorageFailureError(f"Backup failed integrity_check: {check}")
            finally:
                dest_conn.close()
        try:
            os.chmod(destination_path, 0o600)
        except OSError:
            pass
        return {
            "backup_path": str(destination_path),
            "bytes": destination_path.stat().st_size,
            "verified_at_utc": utc_now_iso(),
        }

    @staticmethod
    def restore_from(backup_path: Path, target_db_path: Path) -> dict[str, Any]:
        """Verify an existing SQLite backup file and restore it atomically to `target_db_path`."""
        if not backup_path.is_file():
            raise StorageFailureError(f"Backup file does not exist: {backup_path}")
        check_conn = sqlite3.connect(str(backup_path))
        try:
            check = check_conn.execute("PRAGMA integrity_check;").fetchone()[0]
            if check != "ok":
                raise StorageFailureError(f"Refusing to restore corrupt backup ({check}).")
        finally:
            check_conn.close()

        target_db_path.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(f"{target_db_path}{suffix}").unlink(missing_ok=True)
        tmp_target = target_db_path.parent / f".restore-{os.getpid()}.sqlite3"
        src_conn = sqlite3.connect(str(backup_path))
        dst_conn = sqlite3.connect(str(tmp_target))
        try:
            src_conn.backup(dst_conn)
            dst_conn.commit()
        finally:
            src_conn.close()
            dst_conn.close()
        os.chmod(tmp_target, 0o600)
        tmp_target.replace(target_db_path)
        return {
            "restored_to": str(target_db_path),
            "bytes": target_db_path.stat().st_size,
            "restored_at_utc": utc_now_iso(),
        }

    @staticmethod
    def _row_to_public_dict(row: sqlite3.Row) -> dict[str, Any]:
        # Note: `private_audio_path` is strictly excluded from public API serialization.
        audio_retained = bool(row["audio_retained"])
        return {
            "cursor": row["published_seq"],
            "segment_id": row["segment_id"],
            "feed_id": row["feed_id"],
            "feed_name": row["feed_name"],
            "session_id": row["session_id"],
            "sequence_no": row["sequence_no"],
            "audio_start_utc": row["audio_start_utc"],
            "audio_end_utc": row["audio_end_utc"],
            "duration_seconds": row["duration_seconds"],
            "transcribed_at_utc": row["transcribed_at_utc"],
            "published_at_utc": row["published_at_utc"],
            "capture_to_publish_ms": row["capture_to_publish_ms"],
            "asr_backend": row["asr_backend"],
            "asr_model": row["asr_model"],
            "language": row["language"],
            "text": row["text"],
            "verification_status": row["verification_status"],
            "audio_sha256": row["audio_sha256"],
            "audio_bytes": row["audio_bytes"],
            "audio_retained": audio_retained,
            "private_audio_ref": row["private_audio_ref"] if audio_retained else None,
            "audio_purged_at_utc": row["audio_purged_at_utc"],
            "metrics": json.loads(row["metrics_json"] or "{}"),
            "inferred_tags": json.loads(row["inferred_tags_json"] or "[]"),
        }
