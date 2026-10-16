#!/usr/bin/env python3
"""
REST API interface for the Stock Researcher Agent.

Provides HTTP endpoints for research queries while wrapping the deterministic
research engine. Uses FastAPI with execution dispatched to a threadpool to ensure
long-running network scraping operations never block the event loop or health checks.

Security & Resilience:
    - X-API-Key authentication on /research endpoints (fail-closed if server key unset).
    - Public /health check without credentials.
    - Thread-safe in-memory rate limiting with LRU eviction and memory bounds.
    - In-memory concurrency limiter with bounded timeout to prevent server exhaustion.
    - Interactive documentation (/docs, /redoc, /openapi.json) disabled in production.

Endpoints:
    - GET  /health           : Service liveness and readiness check (public)
    - POST /research         : Execute research for requested symbol via JSON body (protected)
    - GET  /research/{symbol}: Execute research for requested symbol via path parameter (protected)
"""

from __future__ import annotations

import asyncio
import collections
import logging
import os
import secrets
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from intelligence.investment_assessment import evaluate_investment_assessment
from intelligence.track_record import calculate_track_record
from interfaces.research_cli import normalize_symbol
from services.research_pipeline import run_pipeline
from services.supabase_repo import SupabaseRepository, SupabaseRepositoryError

logger = logging.getLogger("stock_researcher_api")

# ----------------------------------------------------
# Production Detection & Configuration Defaults
# ----------------------------------------------------
def is_production_environment() -> bool:
    """
    Detect if running in production.
    Render automatically sets RENDER=true. Local defaults to development
    so local developers retain access to /docs.
    """
    if os.environ.get("RENDER") == "true":
        return True
    explicit = (
        os.environ.get("ENVIRONMENT")
        or os.environ.get("STOCK_RESEARCH_ENV")
        or "development"
    ).lower()
    return explicit in {"prod", "production"}


MAX_CONCURRENT_REQUESTS = int(os.environ.get("MAX_CONCURRENT_REQUESTS", "2"))
CONCURRENCY_TIMEOUT_SECONDS = float(os.environ.get("CONCURRENCY_TIMEOUT_SECONDS", "0.2"))
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "10"))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
MAX_TRACKED_IPS = int(os.environ.get("MAX_TRACKED_IPS", "10000"))

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_server_api_key() -> Optional[str]:
    """Retrieve server API key dynamically from environment."""
    return os.environ.get("RESEARCH_API_KEY")


def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """
    Verify X-API-Key header against server environment.
    Fails closed: if RESEARCH_API_KEY is unset or empty, logs internally and
    returns a generic 500 error without exposing internal configuration details.
    """
    server_key = get_server_api_key()
    if not server_key:
        logger.error("RESEARCH_API_KEY is not configured on the server. Rejecting request.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error.",
        )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: missing API key.",
        )
    if not secrets.compare_digest(api_key, server_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: invalid API key.",
        )
    return api_key


class BoundedIPRateLimiter:
    """
    Thread-safe, memory-bounded sliding window rate limiter.

    Limitations:
    - In-memory only: Limits apply per worker process and are not shared across
      multiple horizontally scaled processes or containers.
    - Ephemeral: All tracked counters reset upon server restart or redeployment.
    - Bounded: Enforces a maximum client IP capacity to prevent memory exhaustion
      from spoofed IP addresses. Stale entries are evicted.
    """
    def __init__(
        self,
        max_requests: int = RATE_LIMIT_REQUESTS,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
        max_tracked_ips: int = MAX_TRACKED_IPS,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_tracked_ips = max_tracked_ips
        self._lock = threading.Lock()
        self._ip_history: Dict[str, collections.deque[float]] = collections.OrderedDict()

    def check(self, request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self._lock:
            # Purge stale timestamps for this IP
            if client_ip in self._ip_history:
                timestamps = self._ip_history[client_ip]
                while timestamps and (now - timestamps[0]) > self.window_seconds:
                    timestamps.popleft()
                if not timestamps:
                    del self._ip_history[client_ip]

            # Check frequency limit
            current_timestamps = self._ip_history.get(client_ip)
            if current_timestamps and len(current_timestamps) >= self.max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded: maximum {self.max_requests} requests per {self.window_seconds} seconds.",
                )

            # Capacity bounds check: evict oldest entry if at capacity
            if len(self._ip_history) >= self.max_tracked_ips and client_ip not in self._ip_history:
                self._ip_history.popitem(last=False)

            if client_ip not in self._ip_history:
                self._ip_history[client_ip] = collections.deque()
            self._ip_history[client_ip].append(now)
            self._ip_history.move_to_end(client_ip)

    def configure(self, max_requests: int, window_seconds: int, max_tracked_ips: Optional[int] = None) -> None:
        """Explicitly reconfigure limits in tests without relying on ambient environment variables."""
        with self._lock:
            self.max_requests = max_requests
            self.window_seconds = window_seconds
            if max_tracked_ips is not None:
                self.max_tracked_ips = max_tracked_ips
            self._ip_history.clear()

    def reset_for_test(self) -> None:
        with self._lock:
            self._ip_history.clear()


_rate_limiter = BoundedIPRateLimiter()


def check_rate_limit(request: Request) -> None:
    _rate_limiter.check(request)


class ConcurrencyLimiter:
    """
    Manages bounded concurrency for long-running research pipelines.

    Guarantees:
    - Never replaces an active semaphore while requests are in flight.
    - Uses an explicit threading.Lock for lazy initialization to prevent race conditions.
    - Retains its reference for the lifetime of the application process.
    """
    def __init__(self, max_concurrent: int = MAX_CONCURRENT_REQUESTS, timeout_seconds: float = CONCURRENCY_TIMEOUT_SECONDS):
        self.max_concurrent = max_concurrent
        self.timeout_seconds = timeout_seconds
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._lock = threading.Lock()

    def get_semaphore(self) -> asyncio.Semaphore:
        """Returns the semaphore, initializing once in a thread-safe manner."""
        if self._semaphore is None:
            with self._lock:
                if self._semaphore is None:
                    self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore

    def reset_for_test(self, max_concurrent: Optional[int] = None) -> None:
        """Explicitly reset only for unit tests when no requests are running."""
        with self._lock:
            if max_concurrent is not None:
                self.max_concurrent = max_concurrent
            self._semaphore = asyncio.Semaphore(self.max_concurrent)


_concurrency_limiter = ConcurrencyLimiter()


def create_app() -> FastAPI:
    """Application factory applying environment-aware documentation settings."""
    is_prod = is_production_environment()
    application = FastAPI(
        title="Stock Researcher API",
        description="REST API for deterministic Indian equities research evidence.",
        version="1.0.0",
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )

    @application.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "ok": False,
                "error": {
                    "type": "HTTPException",
                    "message": exc.detail,
                },
            },
        )

    return application


app = create_app()


class ResearchRequest(BaseModel):
    symbol: str = Field(
        ...,
        description="Ticker symbol of the listed company (e.g. 'TCS', 'INFY')",
        examples=["TCS"],
    )


@app.get("/health", tags=["System"])
async def health_check() -> Dict[str, Any]:
    """Health check endpoint to verify service availability (public)."""
    return {
        "ok": True,
        "service": "stock-researcher-api",
        "status": "healthy",
    }


async def _execute_research(raw_symbol: str) -> JSONResponse:
    """Normalize input, check cache, execute pipeline in a worker thread, persist, and respond."""
    try:
        symbol = normalize_symbol(raw_symbol)
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "ok": False,
                "error": {
                    "type": "ValueError",
                    "message": str(exc),
                },
            },
        )

    sem = _concurrency_limiter.get_semaphore()
    acquired = False
    try:
        await asyncio.wait_for(sem.acquire(), timeout=CONCURRENCY_TIMEOUT_SECONDS)
        acquired = True
    except (asyncio.TimeoutError, TimeoutError):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "ok": False,
                "error": {
                    "type": "ConcurrencyLimitExceeded",
                    "message": f"Server busy: maximum {MAX_CONCURRENT_REQUESTS} concurrent operations active. Please retry shortly.",
                },
            },
        )

    try:
        repo = SupabaseRepository()

        # ------------------------------------------------------------------
        # 1. 6-hour cache check: return stored result if still fresh
        # ------------------------------------------------------------------
        if repo.is_configured:
            cached_rec, cached_snap = await run_in_threadpool(
                repo.get_cached_assessment, symbol
            )
            if cached_rec is not None and cached_snap is not None:
                baseline_rec = None
                try:
                    base_cand = await run_in_threadpool(repo.get_baseline_assessment, symbol)
                    if isinstance(base_cand, dict):
                        baseline_rec = base_cand
                except SupabaseRepositoryError:
                    baseline_rec = None
                track_record = calculate_track_record(cached_rec, baseline_rec)
                cached_rec["track_record"] = track_record
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        **cached_snap,
                        "_persistence": {
                            "saved": True,
                            "is_cached": True,
                            "recommendation_id": cached_rec.get("id"),
                            "snapshot_id": cached_snap.get("research_id"),
                            "track_record": track_record,
                        },
                    },
                )

        # ------------------------------------------------------------------
        # 2. Fresh pipeline run (offload blocking scraping to threadpool)
        # ------------------------------------------------------------------
        result = await run_in_threadpool(run_pipeline, symbol)

        # ------------------------------------------------------------------
        # 3. Deterministic investment assessment
        # ------------------------------------------------------------------
        recommendation = evaluate_investment_assessment(result)

        # ------------------------------------------------------------------
        # 4. Retrieve baseline BEFORE saving (prevents self-comparison)
        # ------------------------------------------------------------------
        baseline_rec = None
        baseline_lookup_failed = False
        if repo.is_configured:
            try:
                base_cand = await run_in_threadpool(repo.get_baseline_assessment, symbol)
                if isinstance(base_cand, dict):
                    baseline_rec = base_cand
            except SupabaseRepositoryError:
                baseline_lookup_failed = True

        if baseline_rec is not None:
            track_record = calculate_track_record(recommendation, baseline_rec)
        elif baseline_lookup_failed:
            track_record = {
                "status": "UNAVAILABLE",
                "note": "Historical track record temporarily unavailable due to database lookup error.",
            }
        elif not repo.is_configured:
            track_record = {
                "status": "UNAVAILABLE",
                "note": "Supabase not configured on server; historical track record unavailable.",
            }
        else:
            track_record = calculate_track_record(recommendation, None)

        recommendation["track_record"] = track_record

        # ------------------------------------------------------------------
        # 5. Append-only persistence to Supabase
        # ------------------------------------------------------------------
        persistence: Dict[str, Any] = {"saved": False, "is_cached": False, "warning": None}

        if repo.is_configured:
            snap_result = await run_in_threadpool(repo.save_research_snapshot, result)
            if snap_result.get("saved") and snap_result.get("id"):
                snapshot_id = snap_result["id"]
                rec_result = await run_in_threadpool(
                    repo.save_recommendation, recommendation, snapshot_id
                )
                if rec_result.get("saved"):
                    recommendation["id"] = rec_result.get("id")
                    persistence = {
                        "saved": True,
                        "is_cached": False,
                        "recommendation_id": rec_result.get("id"),
                        "snapshot_id": snapshot_id,
                        "is_duplicate": rec_result.get("is_duplicate", False),
                        "track_record": track_record,
                    }
                else:
                    persistence = {
                        "saved": False,
                        "is_cached": False,
                        "warning": rec_result.get("warning") or "Recommendation persistence failed.",
                        "snapshot_id": snapshot_id,
                        "track_record": track_record,
                    }
            else:
                persistence = {
                    "saved": False,
                    "is_cached": False,
                    "warning": snap_result.get("warning") or "Snapshot persistence failed.",
                    "track_record": track_record,
                }
        else:
            persistence = {
                "saved": False,
                "is_cached": False,
                "warning": "Supabase not configured on server; persistence skipped.",
                "track_record": track_record,
            }

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={**result, "_persistence": persistence},
        )

    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "ok": False,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            },
        )
    finally:
        if acquired:
            sem.release()


@app.post("/research", tags=["Research"], dependencies=[Depends(verify_api_key), Depends(check_rate_limit)])
async def create_research(request: ResearchRequest) -> JSONResponse:
    """Trigger stock research via JSON payload (protected)."""
    return await _execute_research(request.symbol)


@app.get("/research/{symbol}", tags=["Research"], dependencies=[Depends(verify_api_key), Depends(check_rate_limit)])
async def get_research(symbol: str) -> JSONResponse:
    """Trigger stock research via URL path parameter (protected)."""
    return await _execute_research(symbol)


def main() -> None:
    """CLI launcher for uvicorn server."""
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))

    uvicorn.run(
        "interfaces.api:app",
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
