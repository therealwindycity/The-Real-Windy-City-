"""FastAPI HTTP & SSE API for health, feed metadata, recent transcripts, and cursor polling.

Security & provenance controls:
- Constant-time token authentication when `require_auth` is enabled.
- Strictly forbids caller-supplied URL parameters (anti-SSRF guard).
- `/healthz` returns HTTP 503 whenever operationally unhealthy so process probes never mistake a
  wedged/disconnected worker for a healthy live scanner service.
- `/api/scanner/health` returns structured JSON diagnostics with exact status enum values.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import queue
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .storage import StorageFailureError
from .worker import ScannerServiceRuntime

FORBIDDEN_URL_PARAMS = frozenset(
    {"url", "source_url", "stream_url", "media_url", "page_url", "target", "fetch", "feed_url"}
)


def create_app(runtime: ScannerServiceRuntime) -> FastAPI:
    app = FastAPI(
        title="Civic Cheyenne Live Scanner Transcription API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    if runtime.config.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(runtime.config.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "OPTIONS"],
            allow_headers=["Authorization", "X-Scanner-Token", "Accept"],
        )

    @app.middleware("http")
    async def reject_arbitrary_url_params(request: Request, call_next: Any) -> Any:
        supplied = FORBIDDEN_URL_PARAMS.intersection(
            {k.lower() for k in request.query_params.keys()}
        )
        if supplied:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "arbitrary_url_forbidden",
                    "detail": (
                        f"Caller-supplied source URL parameters ({sorted(supplied)}) are forbidden; "
                        "scanner feeds use server-configured allowlisted streams only."
                    ),
                },
            )
        return await call_next(request)

    def verify_access(
        authorization: str | None = Header(default=None),
        x_scanner_token: str | None = Header(default=None),
    ) -> None:
        if not runtime.config.require_auth:
            return
        expected = runtime.config.api_token or ""
        provided = ""
        if authorization and authorization.lower().startswith("bearer "):
            provided = authorization[7:].strip()
        elif x_scanner_token:
            provided = x_scanner_token.strip()

        if not expected or not provided or not hmac.compare_digest(provided, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Valid scanner service authentication token required.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/healthz")
    def container_healthz() -> JSONResponse:
        snap = runtime.health_snapshot()
        http_code = status.HTTP_200_OK if snap["healthy"] else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(status_code=http_code, content=snap)

    @app.get("/api/scanner/health", dependencies=[Depends(verify_access)])
    def scanner_health() -> dict[str, Any]:
        return runtime.health_snapshot()

    @app.get("/api/scanner/feeds", dependencies=[Depends(verify_access)])
    def list_feeds() -> dict[str, Any]:
        snap = runtime.health_snapshot()
        return {
            "feeds": [
                {
                    **snap["feed"],
                    "status": snap["status"],
                    "healthy": snap["healthy"],
                    "stale": snap["stale"],
                    "latest_cursor": snap["latest_cursor"],
                    "total_published_segments": snap["total_published_segments"],
                }
            ],
            "checked_at_utc": snap["checked_at_utc"],
        }

    @app.get("/api/scanner/feeds/{feed_id}/segments", dependencies=[Depends(verify_access)])
    def get_feed_segments(
        feed_id: str,
        limit: int = Query(default=50, ge=1, le=200),
        after_cursor: int | None = Query(default=None, ge=0),
    ) -> dict[str, Any]:
        if feed_id != runtime.config.feed.feed_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Feed {feed_id!r} is not configured on this worker.",
            )
        snap = runtime.health_snapshot()
        try:
            listing = runtime.store.list_published_segments(
                feed_id, limit=limit, after_cursor=after_cursor
            )
        except StorageFailureError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Transcript storage unavailable: {exc}",
            ) from exc

        return {
            "feed": snap["feed"],
            "health": {
                "status": snap["status"],
                "healthy": snap["healthy"],
                "stale": snap["stale"],
                "checked_at_utc": snap["checked_at_utc"],
                "last_audio_received_at": snap["last_audio_received_at"],
                "audio_age_seconds": snap["audio_age_seconds"],
                "stale_after_seconds": snap["stale_after_seconds"],
                "last_transcribed_audio_end_at": snap["last_transcribed_audio_end_at"],
                "last_published_at": snap["last_published_at"],
                "pending_backlog": snap["pending_backlog"],
                "estimated_processing_lag_ms": snap["estimated_processing_lag_ms"],
                "last_capture_to_publish_ms": snap["last_capture_to_publish_ms"],
                "current_error": snap["current_error"],
            },
            "recent_gaps": snap["recent_gaps"],
            "segments": listing["segments"],
            "next_cursor": listing["next_cursor"],
            "latest_cursor": listing["latest_cursor"],
            "total_published": listing["total_published"],
            "has_more": listing["has_more"],
            "disclaimer": snap["disclaimer"],
        }

    @app.get("/api/scanner/feeds/{feed_id}/stream", dependencies=[Depends(verify_access)])
    async def stream_feed_events(request: Request, feed_id: str) -> StreamingResponse:
        if feed_id != runtime.config.feed.feed_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Feed {feed_id!r} is not configured on this worker.",
            )

        sub_q = runtime.events.subscribe()

        async def event_generator() -> Any:
            try:
                initial = runtime.health_snapshot()
                yield f"event: status\ndata: {json.dumps(initial)}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        item = await asyncio.to_thread(sub_q.get, True, 5.0)
                        yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
                    except queue.Empty:
                        hb = runtime.health_snapshot()
                        yield f"event: status\ndata: {json.dumps(hb)}\n\n"
            finally:
                runtime.events.unsubscribe(sub_q)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app
