#!/usr/bin/env python3
"""
Render Research REST API Client

Purpose
-------
Fetches canonical ResearchResult v1 from the deployed Render API service
with bounded timeouts, retries for transient HTTP errors, strict schema
validation, and explicit (non-silent) local fallback behavior.

Safeguards:
1. Bounded 75-second timeout absorbs Render cold starts.
2. Bounded retries (max 2) strictly for transient 502/503/504 status codes.
3. Rigorous validation of JSON structure, symbol match, and schema.
4. No silent local fallback: fallback only executes when explicitly authorized
   and is explicitly labelled in the output.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from interfaces.research_cli import normalize_symbol

DEFAULT_RENDER_API_BASE = "https://stock-researcher-agent.onrender.com"
DEFAULT_TIMEOUT_SECONDS = 75.0
DEFAULT_MAX_RETRIES = 2
RETRYABLE_STATUS_CODES = {502, 503, 504}


class RenderAPIError(Exception):
    """Raised when Render API research request fails."""
    pass


class RenderSchemaValidationError(Exception):
    """Raised when Render API response fails schema validation."""
    pass


class ResearchClient:
    """Client for querying the deterministic stock research REST API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        schema_path: Optional[Path] = None,
    ):
        raw_url = base_url or os.environ.get("RENDER_RESEARCH_API_URL", DEFAULT_RENDER_API_BASE)
        self.base_url = raw_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.schema_path = schema_path or (PROJECT_ROOT / "schemas" / "research-result.v1.schema.json")
        self._validator = None
        self._init_schema_validator()

    def _init_schema_validator(self) -> None:
        """Load JSON schema validator if available."""
        if self.schema_path and self.schema_path.exists():
            try:
                import jsonschema
                with self.schema_path.open("r", encoding="utf-8") as f:
                    schema_data = json.load(f)
                self._validator = jsonschema.Draft202012Validator(schema_data)
            except Exception:
                self._validator = None

    def fetch_research(
        self,
        raw_symbol: str,
        allow_local_fallback: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetch canonical ResearchResult for the requested symbol.

        Parameters
        ----------
        raw_symbol: Ticker symbol (e.g. 'TCS', 'INFY').
        allow_local_fallback: If True, falls back to local pipeline only after
                              Render API fails, explicitly marking the provenance.
        """
        symbol = normalize_symbol(raw_symbol)
        endpoint = f"{self.base_url}/research/{symbol}"

        last_error: Optional[Exception] = None
        attempts = 0

        while attempts <= self.max_retries:
            attempts += 1
            try:
                resp = requests.get(
                    endpoint,
                    timeout=self.timeout,
                    headers={"Accept": "application/json"},
                )

                # Check if retryable transient server error
                if resp.status_code in RETRYABLE_STATUS_CODES and attempts <= self.max_retries:
                    time.sleep(2.0 * attempts)
                    continue

                if resp.status_code != 200:
                    raise RenderAPIError(
                        f"Render API returned HTTP {resp.status_code} for {symbol}: {resp.text[:200]}"
                    )

                data = resp.json()
                if not isinstance(data, dict):
                    raise RenderSchemaValidationError(
                        f"Render API returned non-object JSON for {symbol}"
                    )

                # Validate essential canonical fields
                self._validate_payload(data, symbol)
                data["_research_source"] = "RENDER_LIVE_API"
                return data

            except RenderSchemaValidationError:
                raise
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempts <= self.max_retries:
                    time.sleep(0.05 * attempts)
                    continue
                break
            except Exception as exc:
                last_error = exc
                break

        # If we reached here, Render API request failed
        err_msg = f"Failed to fetch research for {symbol} from {endpoint}: {last_error}"

        if not allow_local_fallback:
            raise RenderAPIError(err_msg) from last_error

        # Explicit local fallback (only when explicitly requested)
        try:
            from services.research_pipeline import run_pipeline
            local_result = run_pipeline(symbol)
            local_result["_research_source"] = "LOCAL_PIPELINE_FALLBACK"
            local_result["_fallback_warning"] = (
                f"Notice: Live Render API failed ({err_msg}). Result generated via authorized local fallback."
            )
            return local_result
        except Exception as local_exc:
            raise RenderAPIError(
                f"{err_msg}. Authorized local fallback also failed: {local_exc}"
            ) from local_exc

    def _validate_payload(self, data: Dict[str, Any], symbol: str) -> None:
        """Validate structure and essential ResearchResult v1 invariants."""
        if data.get("schema_version") != "1.0":
            raise RenderSchemaValidationError(
                f"Unsupported schema version: {data.get('schema_version')!r} (expected '1.0')"
            )

        payload_symbol = str(data.get("symbol", "")).upper()
        if payload_symbol != symbol:
            raise RenderSchemaValidationError(
                f"Symbol mismatch: requested {symbol!r}, received {payload_symbol!r}"
            )

        if "overall_status" not in data:
            raise RenderSchemaValidationError("Missing 'overall_status' in ResearchResult")

        if "technicals" not in data or "fundamentals" not in data:
            raise RenderSchemaValidationError("Missing technicals or fundamentals section")

        # Formal json-schema validation
        if self._validator:
            errors = list(self._validator.iter_errors(data))
            if errors:
                err_summary = "; ".join(e.message for e in errors[:3])
                raise RenderSchemaValidationError(f"JSON schema validation failed: {err_summary}")
