#!/usr/bin/env python3
"""
REST API interface for the Stock Researcher Agent.

Provides HTTP endpoints for research queries while wrapping the deterministic
research engine. Uses FastAPI with execution dispatched to a threadpool to ensure
long-running network scraping operations never block the event loop or health checks.

Endpoints:
    - GET  /health           : Service liveness and readiness check
    - POST /research         : Execute research for requested symbol via JSON body
    - GET  /research/{symbol}: Execute research for requested symbol via path parameter
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from interfaces.research_cli import normalize_symbol
from services.research_pipeline import run_pipeline

app = FastAPI(
    title="Stock Researcher API",
    description="REST API for deterministic Indian equities research evidence.",
    version="1.0.0",
)


class ResearchRequest(BaseModel):
    symbol: str = Field(
        ...,
        description="Ticker symbol of the listed company (e.g. 'TCS', 'INFY')",
        examples=["TCS"],
    )


@app.get("/health", tags=["System"])
async def health_check() -> Dict[str, Any]:
    """Health check endpoint to verify service availability."""
    return {
        "ok": True,
        "service": "stock-researcher-api",
        "status": "healthy",
    }


async def _execute_research(raw_symbol: str) -> JSONResponse:
    """Normalize input, execute pipeline in a worker thread, and format response."""
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

    try:
        # Offload the synchronous, long-running scraper/pipeline to threadpool
        result = await run_in_threadpool(run_pipeline, symbol)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=result,
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


@app.post("/research", tags=["Research"])
async def create_research(request: ResearchRequest) -> JSONResponse:
    """Trigger stock research via JSON payload."""
    return await _execute_research(request.symbol)


@app.get("/research/{symbol}", tags=["Research"])
async def get_research(symbol: str) -> JSONResponse:
    """Trigger stock research via URL path parameter."""
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
