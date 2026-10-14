#!/usr/bin/env python3
"""
Tests for interfaces/api.py

Verifies the FastAPI REST API endpoints using in-memory ASGI dispatch:
    - GET  /health (public)
    - POST /research (protected with X-API-Key)
    - GET  /research/{symbol} (protected with X-API-Key)
    - Authentication verification and fail-closed generic 500 behavior
    - Thread-safe, bounded in-memory rate limiting with LRU eviction
    - Concurrency limiting, saturation timeout, cancellation, and recovery
    - Production vs. development API documentation visibility
    - Validation error handling (400 Bad Request, 422 Unprocessable Entity)
    - Pipeline error handling (500 Internal Server Error)
    - Threadpool concurrency offload
"""

from __future__ import annotations

import asyncio
import json
import time
import unittest
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from interfaces.api import (
    BoundedIPRateLimiter,
    _concurrency_limiter,
    _rate_limiter,
    app,
    create_app,
    is_production_environment,
)
from services.research_client import RenderAPIError, ResearchClient


class ASGIResponse:
    """Represents a simulated HTTP response from ASGI dispatch."""

    def __init__(self, status_code: int, headers: Dict[str, str], body: bytes):
        self.status_code = status_code
        self.headers = headers
        self.body = body

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class InMemoryTestClient:
    """
    Lightweight, dependency-free in-memory ASGI test client.
    Executes directly against the FastAPI/Starlette app without opening network sockets.
    """

    def __init__(self, asgi_app):
        self.app = asgi_app

    def request(
        self,
        method: str,
        path: str,
        json_body: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ASGIResponse:
        return asyncio.run(self._request_async(method, path, json_body, headers))

    async def _request_async(
        self,
        method: str,
        path: str,
        json_body: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ASGIResponse:
        raw_headers = []
        if headers:
            for k, v in headers.items():
                raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

        body_bytes = b""
        if json_body is not None:
            body_bytes = json.dumps(json_body).encode("utf-8")
            raw_headers.append((b"content-type", b"application/json"))
            raw_headers.append((b"content-length", str(len(body_bytes)).encode("latin-1")))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("latin-1"),
            "query_string": b"",
            "headers": raw_headers,
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 80),
        }

        messages = []

        async def receive():
            return {
                "type": "http.request",
                "body": body_bytes,
                "more_body": False,
            }

        async def send(message):
            messages.append(message)

        await self.app(scope, receive, send)

        status_code = 500
        response_headers = {}
        response_body = b""

        for msg in messages:
            if msg["type"] == "http.response.start":
                status_code = msg["status"]
                for header_key, header_val in msg.get("headers", []):
                    response_headers[header_key.decode("latin-1")] = header_val.decode("latin-1")
            elif msg["type"] == "http.response.body":
                response_body += msg.get("body", b"")

        return ASGIResponse(status_code, response_headers, response_body)

    def get(self, path: str, headers: Optional[Dict[str, str]] = None) -> ASGIResponse:
        return self.request("GET", path, headers=headers)

    def post(self, path: str, json: Optional[Any] = None, headers: Optional[Dict[str, str]] = None) -> ASGIResponse:
        return self.request("POST", path, json_body=json, headers=headers)


def make_mock_research_result(symbol: str) -> Dict[str, Any]:
    """Generate a canonical ResearchResult v1 fixture."""
    return {
        "schema_version": "1.0",
        "research_id": f"{symbol.lower()}-test-id",
        "symbol": symbol.upper(),
        "exchange": "NSE",
        "isin": None,
        "company_name": f"{symbol.upper()} Test Limited",
        "symbol_match_confidence": "EXACT",
        "requested_at": "2026-10-10T12:00:00Z",
        "completed_at": "2026-10-10T12:00:05Z",
        "overall_status": "PARTIAL",
        "fundamentals": {
            "provenance": {
                "source": "screener",
                "source_url": f"https://www.screener.in/company/{symbol.upper()}/",
                "retrieved_at": "2026-10-10T12:00:01Z",
                "as_of_date": "2026-06-30",
            },
            "pe_ratio": {
                "value": 28.5,
                "unit": "RATIO",
                "status": "VERIFIED",
                "provenance": {
                    "source": "screener",
                    "source_url": None,
                    "retrieved_at": "2026-10-10T12:00:01Z",
                    "as_of_date": "2026-06-30",
                },
                "conflicting_values": [],
                "notes": None,
            },
        },
        "technicals": {
            "provenance": {
                "source": "market_data",
                "source_url": None,
                "retrieved_at": "2026-10-10T12:00:02Z",
                "as_of_date": "2026-10-09",
            },
            "cmp": {
                "value": 3500.0,
                "unit": "INR",
                "status": "VERIFIED",
                "provenance": {
                    "source": "market_data",
                    "source_url": None,
                    "retrieved_at": "2026-10-10T12:00:02Z",
                    "as_of_date": "2026-10-09",
                },
                "conflicting_values": [],
                "notes": None,
            },
        },
        "institutional": {
            "provenance": {
                "source": "screener",
                "source_url": None,
                "retrieved_at": "2026-10-10T12:00:01Z",
                "as_of_date": "2026-06-30",
            },
            "fii_holding": {
                "value": 18.2,
                "unit": "PERCENT",
                "status": "VERIFIED",
                "provenance": {
                    "source": "screener",
                    "source_url": None,
                    "retrieved_at": "2026-10-10T12:00:01Z",
                    "as_of_date": "2026-06-30",
                },
                "conflicting_values": [],
                "notes": None,
            },
        },
        "news": {
            "provenance": {
                "source": "news",
                "source_url": None,
                "retrieved_at": "2026-10-10T12:00:03Z",
                "as_of_date": "2026-10-10",
            },
            "recent_items": [],
        },
        "sources": {
            "screener": {"status": "SUCCESS", "error": None},
            "market_data": {"status": "SUCCESS", "error": None},
            "news": {"status": "SUCCESS", "error": None},
        },
        "errors": [],
        "data_quality_summary": {
            "total_fields": 3,
            "verified_fields": 3,
            "derived_fields": 0,
            "unavailable_fields": 0,
            "stale_fields": 0,
            "conflicting_fields": 0,
            "failed_fields": 0,
            "quality_score": 1.0,
        },
    }


class TestStockResearcherAPI(unittest.TestCase):

    def setUp(self):
        self.client = InMemoryTestClient(app)
        self.test_key = "test-secret-key-12345"
        self.auth_headers = {"X-API-Key": self.test_key}
        self.env_patcher = patch.dict("os.environ", {"RESEARCH_API_KEY": self.test_key})
        self.env_patcher.start()
        _rate_limiter.reset_for_test()
        _concurrency_limiter.reset_for_test()

    def tearDown(self):
        self.env_patcher.stop()
        _rate_limiter.reset_for_test()
        _concurrency_limiter.reset_for_test()

    def test_health_endpoint_public(self):
        """GET /health returns 200 without requiring any credentials."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("service"), "stock-researcher-api")
        self.assertEqual(data.get("status"), "healthy")

    # ----------------------------------------------------
    # Authentication Tests
    # ----------------------------------------------------

    def test_protected_routes_reject_missing_api_key(self):
        """POST /research and GET /research/{symbol} reject calls without X-API-Key."""
        resp_post = self.client.post("/research", json={"symbol": "TCS"})
        self.assertEqual(resp_post.status_code, 401)
        self.assertFalse(resp_post.json()["ok"])
        self.assertIn("missing", resp_post.json()["error"]["message"].lower())

        resp_get = self.client.get("/research/TCS")
        self.assertEqual(resp_get.status_code, 401)
        self.assertFalse(resp_get.json()["ok"])
        self.assertIn("missing", resp_get.json()["error"]["message"].lower())

    def test_protected_routes_reject_invalid_api_key(self):
        """POST /research and GET /research/{symbol} reject invalid X-API-Key values."""
        bad_headers = {"X-API-Key": "wrong-key-value"}
        resp_post = self.client.post("/research", json={"symbol": "TCS"}, headers=bad_headers)
        self.assertEqual(resp_post.status_code, 401)
        self.assertIn("invalid", resp_post.json()["error"]["message"].lower())

        resp_get = self.client.get("/research/TCS", headers=bad_headers)
        self.assertEqual(resp_get.status_code, 401)
        self.assertIn("invalid", resp_get.json()["error"]["message"].lower())

    def test_protected_routes_fail_closed_with_generic_error_when_server_key_unset(self):
        """Protected endpoints fail closed with generic 500 when server key is not configured."""
        with patch("interfaces.api.get_server_api_key", return_value=None):
            resp_post = self.client.post("/research", json={"symbol": "TCS"}, headers={"X-API-Key": "any-key"})
            self.assertEqual(resp_post.status_code, 500)
            self.assertFalse(resp_post.json()["ok"])
            self.assertEqual(resp_post.json()["error"]["message"], "Internal server error.")

            resp_get = self.client.get("/research/TCS", headers={"X-API-Key": "any-key"})
            self.assertEqual(resp_get.status_code, 500)
            self.assertEqual(resp_get.json()["error"]["message"], "Internal server error.")

    # ----------------------------------------------------
    # Research Execution Tests (Authenticated)
    # ----------------------------------------------------

    @patch("interfaces.api.run_pipeline")
    def test_post_research_success(self, mock_run_pipeline):
        """POST /research executes pipeline and returns 200 with ResearchResult."""
        mock_result = make_mock_research_result("TCS")
        mock_run_pipeline.return_value = mock_result

        resp = self.client.post("/research", json={"symbol": "TCS"}, headers=self.auth_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["symbol"], "TCS")
        self.assertEqual(data["schema_version"], "1.0")
        mock_run_pipeline.assert_called_once_with("TCS")

    @patch("interfaces.api.run_pipeline")
    def test_post_research_normalizes_symbol(self, mock_run_pipeline):
        """POST /research strips and uppercases input symbols."""
        mock_result = make_mock_research_result("INFY")
        mock_run_pipeline.return_value = mock_result

        resp = self.client.post("/research", json={"symbol": "  infy  "}, headers=self.auth_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["symbol"], "INFY")
        mock_run_pipeline.assert_called_once_with("INFY")

    @patch("interfaces.api.run_pipeline")
    def test_get_research_by_symbol_success(self, mock_run_pipeline):
        """GET /research/{symbol} executes pipeline with valid key and returns 200."""
        mock_result = make_mock_research_result("RELIANCE")
        mock_run_pipeline.return_value = mock_result

        resp = self.client.get("/research/RELIANCE", headers=self.auth_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["symbol"], "RELIANCE")
        mock_run_pipeline.assert_called_once_with("RELIANCE")

    @patch("interfaces.api.run_pipeline")
    def test_get_research_by_symbol_normalizes(self, mock_run_pipeline):
        """GET /research/{symbol} handles lowercase ticker paths."""
        mock_result = make_mock_research_result("HDFCBANK")
        mock_run_pipeline.return_value = mock_result

        resp = self.client.get("/research/hdfcbank", headers=self.auth_headers)
        self.assertEqual(resp.status_code, 200)
        mock_run_pipeline.assert_called_once_with("HDFCBANK")

    def test_post_research_empty_symbol_400(self):
        """POST /research with empty symbol returns 400 Bad Request."""
        resp = self.client.post("/research", json={"symbol": "   "}, headers=self.auth_headers)
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data["error"]["type"], "ValueError")
        self.assertIn("cannot be empty", data["error"]["message"])

    def test_post_research_invalid_characters_400(self):
        """POST /research with illegal characters returns 400 Bad Request."""
        resp = self.client.post("/research", json={"symbol": "TCS$$$"}, headers=self.auth_headers)
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data["error"]["type"], "ValueError")
        self.assertIn("Invalid stock symbol", data["error"]["message"])

    def test_get_research_invalid_characters_400(self):
        """GET /research/{symbol} with illegal characters returns 400 Bad Request."""
        resp = self.client.get("/research/TCS@BAD", headers=self.auth_headers)
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data["error"]["type"], "ValueError")

    def test_post_research_missing_field_422(self):
        """POST /research with missing 'symbol' field returns 422 Unprocessable Entity."""
        resp = self.client.post("/research", json={}, headers=self.auth_headers)
        self.assertEqual(resp.status_code, 422)

    @patch("interfaces.api.run_pipeline")
    def test_post_research_pipeline_failure_500(self, mock_run_pipeline):
        """POST /research returns 500 when research pipeline raises an error."""
        mock_run_pipeline.side_effect = RuntimeError("Screener fetch failed: HTTP 500")

        resp = self.client.post("/research", json={"symbol": "TCS"}, headers=self.auth_headers)
        self.assertEqual(resp.status_code, 500)
        data = resp.json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data["error"]["type"], "RuntimeError")
        self.assertIn("Screener fetch failed", data["error"]["message"])

    @patch("interfaces.api.run_pipeline")
    def test_get_research_pipeline_failure_500(self, mock_run_pipeline):
        """GET /research/{symbol} returns 500 when research pipeline raises an error."""
        mock_run_pipeline.side_effect = TimeoutError("Connection timed out")

        resp = self.client.get("/research/TCS", headers=self.auth_headers)
        self.assertEqual(resp.status_code, 500)
        data = resp.json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data["error"]["type"], "TimeoutError")
        self.assertIn("Connection timed out", data["error"]["message"])

    def test_method_not_allowed_405(self):
        """Unsupported HTTP method returns 405 Method Not Allowed."""
        resp = self.client.request("DELETE", "/research", headers=self.auth_headers)
        self.assertEqual(resp.status_code, 405)

    # ----------------------------------------------------
    # Rate Limiter Tests
    # ----------------------------------------------------

    @patch("interfaces.api.run_pipeline")
    def test_rate_limiter_explicit_configuration(self, mock_pipeline):
        """Limiter explicitly reconfigured in test rejects excess requests with 429."""
        mock_pipeline.return_value = make_mock_research_result("TCS")
        _rate_limiter.configure(max_requests=2, window_seconds=60)

        resp1 = self.client.get("/research/TCS", headers=self.auth_headers)
        resp2 = self.client.get("/research/TCS", headers=self.auth_headers)
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)

        resp3 = self.client.get("/research/TCS", headers=self.auth_headers)
        self.assertEqual(resp3.status_code, 429)
        self.assertIn("rate limit exceeded", resp3.json()["error"]["message"].lower())

    def test_rate_limiter_stale_entry_cleanup(self):
        """Stale client timestamp entries outside window are purged on access."""
        limiter = BoundedIPRateLimiter(max_requests=2, window_seconds=1.0)
        mock_req = MagicMock(client=MagicMock(host="10.0.0.1"))

        limiter.check(mock_req)
        self.assertIn("10.0.0.1", limiter._ip_history)

        # Advance time by 2.0s (past window)
        with patch("time.monotonic", return_value=time.monotonic() + 2.0):
            limiter.check(mock_req)
            self.assertEqual(len(limiter._ip_history["10.0.0.1"]), 1)

    def test_rate_limiter_capacity_bounds_and_eviction(self):
        """Limiter bounds tracking memory and evicts oldest entry upon saturation."""
        limiter = BoundedIPRateLimiter(max_requests=5, window_seconds=60, max_tracked_ips=3)

        for i in range(5):
            req = MagicMock(client=MagicMock(host=f"10.0.0.{i}"))
            limiter.check(req)

        self.assertEqual(len(limiter._ip_history), 3)
        self.assertNotIn("10.0.0.0", limiter._ip_history)
        self.assertNotIn("10.0.0.1", limiter._ip_history)
        self.assertIn("10.0.0.4", limiter._ip_history)

    # ----------------------------------------------------
    # Concurrency and Recovery Tests (Single Event Loop)
    # ----------------------------------------------------

    @patch("interfaces.api.run_pipeline")
    def test_concurrency_saturation_timeout_and_recovery(self, mock_pipeline):
        """Excess concurrent requests time out with 429, recovering when permits are released."""
        mock_pipeline.return_value = make_mock_research_result("TCS")

        async def run_scenario():
            sem = _concurrency_limiter.get_semaphore()

            # Acquire both permits on the active event loop
            await sem.acquire()
            await sem.acquire()

            # Request while saturated times out and returns 429
            resp_busy = await self.client._request_async("GET", "/research/TCS", headers=self.auth_headers)
            self.assertEqual(resp_busy.status_code, 429)
            self.assertIn("server busy", resp_busy.json()["error"]["message"].lower())

            # Release one permit on the active event loop
            sem.release()

            # Request immediately recovers with 200
            resp_ok = await self.client._request_async("GET", "/research/TCS", headers=self.auth_headers)
            self.assertEqual(resp_ok.status_code, 200)
            self.assertEqual(resp_ok.json()["symbol"], "TCS")

            # Clean up second permit
            sem.release()

        asyncio.run(run_scenario())

    @patch("interfaces.api.run_pipeline")
    def test_concurrency_permit_released_after_success(self, mock_pipeline):
        """Permit is safely returned to semaphore after successful request."""
        mock_pipeline.return_value = make_mock_research_result("TCS")

        async def run_scenario():
            sem = _concurrency_limiter.get_semaphore()
            initial_permits = sem._value

            resp = await self.client._request_async("GET", "/research/TCS", headers=self.auth_headers)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(sem._value, initial_permits)

        asyncio.run(run_scenario())

    @patch("interfaces.api.run_pipeline", side_effect=RuntimeError("Pipeline crash"))
    def test_concurrency_permit_released_after_pipeline_exception(self, mock_pipeline):
        """Permit is safely returned to semaphore even when pipeline raises an exception."""
        async def run_scenario():
            sem = _concurrency_limiter.get_semaphore()
            initial_permits = sem._value

            resp = await self.client._request_async("GET", "/research/TCS", headers=self.auth_headers)
            self.assertEqual(resp.status_code, 500)
            self.assertEqual(sem._value, initial_permits)

        asyncio.run(run_scenario())

    @patch("interfaces.api.run_pipeline")
    def test_concurrency_permit_released_on_request_cancellation(self, mock_pipeline):
        """Permit is released when an in-flight request task is cancelled."""
        def slow_pipeline(symbol):
            time.sleep(0.4)
            return make_mock_research_result(symbol)

        mock_pipeline.side_effect = slow_pipeline

        async def run_scenario():
            sem = _concurrency_limiter.get_semaphore()
            initial_permits = sem._value

            task = asyncio.create_task(
                self.client._request_async("GET", "/research/TCS", headers=self.auth_headers)
            )
            await asyncio.sleep(0.05)
            self.assertEqual(sem._value, initial_permits - 1)

            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

            self.assertEqual(sem._value, initial_permits)

        asyncio.run(run_scenario())

    # ----------------------------------------------------
    # Production Detection & Documentation Tests
    # ----------------------------------------------------

    def test_production_detection_flags(self):
        """Detect production environment via Render platform or explicit environment variables."""
        with patch.dict("os.environ", {"RENDER": "true"}):
            self.assertTrue(is_production_environment())

        with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
            self.assertTrue(is_production_environment())

        with patch.dict("os.environ", {"STOCK_RESEARCH_ENV": "prod"}):
            self.assertTrue(is_production_environment())

        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(is_production_environment())

    def test_docs_endpoints_disabled_in_production(self):
        """Interactive docs (/docs, /redoc, /openapi.json) return 404 in production."""
        with patch.dict("os.environ", {"RENDER": "true"}):
            prod_app = create_app()
            client = InMemoryTestClient(prod_app)
            self.assertEqual(client.get("/docs").status_code, 404)
            self.assertEqual(client.get("/redoc").status_code, 404)
            self.assertEqual(client.get("/openapi.json").status_code, 404)

    def test_docs_endpoints_enabled_in_development(self):
        """Interactive docs (/docs, /redoc, /openapi.json) return 200 in development."""
        with patch.dict("os.environ", {"ENVIRONMENT": "development"}):
            dev_app = create_app()
            client = InMemoryTestClient(dev_app)
            self.assertEqual(client.get("/docs").status_code, 200)
            self.assertEqual(client.get("/redoc").status_code, 200)
            self.assertEqual(client.get("/openapi.json").status_code, 200)

    # ----------------------------------------------------
    # ResearchClient Pre-Request Validation Tests
    # ----------------------------------------------------

    @patch("requests.get")
    def test_research_client_fails_locally_when_key_missing(self, mock_http_get):
        """ResearchClient raises RenderAPIError without sending HTTP requests when key is missing."""
        with patch.dict("os.environ", {}, clear=True):
            client = ResearchClient(base_url="https://fake-render-api.com", api_key=None)
            with self.assertRaises(RenderAPIError) as ctx:
                client.fetch_research("TCS")

            self.assertIn("RESEARCH_API_KEY", str(ctx.exception))
            mock_http_get.assert_not_called()

    @patch("requests.get")
    def test_research_client_attaches_api_key_header(self, mock_http_get):
        """ResearchClient sends X-API-Key header in outbound HTTP request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = make_mock_research_result("TCS")
        mock_http_get.return_value = mock_response

        client = ResearchClient(base_url="https://fake-render-api.com", api_key="my-secret-key")
        client._validate_payload = MagicMock()
        result = client.fetch_research("TCS")

        self.assertEqual(result["symbol"], "TCS")
        mock_http_get.assert_called_once()
        called_headers = mock_http_get.call_args[1]["headers"]
        self.assertEqual(called_headers.get("X-API-Key"), "my-secret-key")


if __name__ == "__main__":
    unittest.main(verbosity=2)
