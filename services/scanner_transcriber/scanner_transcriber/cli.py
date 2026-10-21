"""CLI entrypoints for running, bounded smoke testing, backing up, and restoring the service."""

from __future__ import annotations

import argparse
import json
import logging
import resource
import signal
import sys
import time
from pathlib import Path

import uvicorn

from .api import create_app
from .config import ServiceConfig
from .storage import ScannerStore
from .worker import ScannerServiceRuntime


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)sZ %(levelname)s [%(name)s] %(message)s",
    )


def cmd_serve(_args: argparse.Namespace) -> int:
    config = ServiceConfig.from_env()
    runtime = ScannerServiceRuntime(config)
    app = create_app(runtime)

    runtime.start()
    try:
        uvicorn.run(
            app,
            host=config.bind_host,
            port=config.bind_port,
            log_level="info",
            access_log=False,
        )
    finally:
        runtime.stop()
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    """Run a bounded live/fixture capture + ASR smoke test and emit measured acceptance telemetry."""
    config = ServiceConfig.from_env()
    runtime = ScannerServiceRuntime(config)
    stop_flag = False

    def _handle_sig(_signum: int, _frame: object) -> None:
        nonlocal stop_flag
        stop_flag = True

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    t0 = time.monotonic()
    runtime.start()
    try:
        deadline = t0 + float(args.seconds)
        while time.monotonic() < deadline and not stop_flag:
            time.sleep(0.5)
    finally:
        final_live_health = runtime.health_snapshot()
        segments_payload = runtime.store.list_published_segments(
            config.feed.feed_id, limit=100
        )
        runtime.stop()

    rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    latencies = [
        s["capture_to_publish_ms"]
        for s in segments_payload["segments"]
        if isinstance(s.get("capture_to_publish_ms"), int)
    ]

    report = {
        "duration_seconds": round(time.monotonic() - t0, 2),
        "feed_id": config.feed.feed_id,
        "feed_name": config.feed.feed_name,
        "final_live_status": final_live_health["status"],
        "healthy_before_stop": final_live_health["healthy"],
        "last_audio_received_at": final_live_health["last_audio_received_at"],
        "last_transcribed_audio_end_at": final_live_health["last_transcribed_audio_end_at"],
        "last_published_at": final_live_health["last_published_at"],
        "current_error": final_live_health["current_error"],
        "published_segment_count": len(segments_payload["segments"]),
        "capture_to_publish_latency_ms": {
            "min": min(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
            "mean": round(sum(latencies) / len(latencies), 1) if latencies else None,
        },
        "peak_rss_mib": round(rss_kb / 1024.0, 2),
        "recent_gaps": final_live_health["recent_gaps"],
        "sample_segments": segments_payload["segments"][:5],
    }
    print(json.dumps(report, indent=2))
    if args.require_audio and not final_live_health["last_audio_received_at"]:
        return 2
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    config = ServiceConfig.from_env()
    store = ScannerStore(config.db_path)
    try:
        result = store.backup_to(Path(args.dest).resolve())
    finally:
        store.close()
    print(json.dumps(result, indent=2))
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    config = ServiceConfig.from_env()
    result = ScannerStore.restore_from(Path(args.src).resolve(), config.db_path)
    print(json.dumps(result, indent=2))
    return 0


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(
        prog="scanner-transcriber",
        description="Civic Cheyenne live scanner capture, ASR, storage, and API service.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="Start the continuous capture + ASR worker and HTTP API.")

    smoke_p = sub.add_parser(
        "smoke", help="Run a bounded smoke test and emit JSON health, segments, and latency stats."
    )
    smoke_p.add_argument("--seconds", type=float, default=30.0)
    smoke_p.add_argument("--require-audio", action="store_true")

    backup_p = sub.add_parser("backup", help="Create a verified hot SQLite backup.")
    backup_p.add_argument("--dest", required=True, help="Destination backup sqlite3 file path.")

    restore_p = sub.add_parser("restore", help="Verify and restore a SQLite backup (service stopped).")
    restore_p.add_argument("--src", required=True, help="Source backup sqlite3 file path.")

    args = parser.parse_args()
    handlers = {
        "serve": cmd_serve,
        "smoke": cmd_smoke,
        "backup": cmd_backup,
        "restore": cmd_restore,
    }
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
