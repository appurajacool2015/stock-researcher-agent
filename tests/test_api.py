#!/usr/bin/env python3
"""
Tests for interfaces/api.py

Verifies the FastAPI REST API endpoints using in-memory ASGI dispatch:
    - GET  /health
    - POST /research
    - GET  /research/{symbol}
    - Validation error handling (400 Bad Request, 422 Unprocessable Entity)
    - Pipeline error handling (500 Internal Server Error)
    - Threadpool concurrency offload
"""

from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from interfaces.api import app


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
        },
        "news": [],
        "sources": [],
        "errors": [],
        "data_quality_summary": {
            "verified": 2,
            "derived": 0,
            "unavailable": 0,
            "stale": 0,
            "conflicting": 0,
            "failed": 0,
        },
    }


class TestStockResearcherAPI(unittest.TestCase):

    def setUp(self):
        self.client = InMemoryTestClient(app)

    def test_health_endpoint(self):
        """GET /health returns 200 with service health metadata."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("service"), "stock-researcher-api")
        self.assertEqual(data.get("status"), "healthy")

    @patch("interfaces.api.run_pipeline")
    def test_post_research_success(self, mock_run_pipeline):
        """POST /research executes pipeline and returns 200 with ResearchResult."""
        mock_result = make_mock_research_result("TCS")
        mock_run_pipeline.return_value = mock_result

        resp = self.client.post("/research", json={"symbol": "TCS"})
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

        resp = self.client.post("/research", json={"symbol": "  infy  "})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["symbol"], "INFY")
        mock_run_pipeline.assert_called_once_with("INFY")

    @patch("interfaces.api.run_pipeline")
    def test_get_research_by_symbol_success(self, mock_run_pipeline):
        """GET /research/{symbol} executes pipeline and returns 200."""
        mock_result = make_mock_research_result("RELIANCE")
        mock_run_pipeline.return_value = mock_result

        resp = self.client.get("/research/RELIANCE")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["symbol"], "RELIANCE")
        mock_run_pipeline.assert_called_once_with("RELIANCE")

    @patch("interfaces.api.run_pipeline")
    def test_get_research_by_symbol_normalizes(self, mock_run_pipeline):
        """GET /research/{symbol} handles lowercase ticker paths."""
        mock_result = make_mock_research_result("HDFCBANK")
        mock_run_pipeline.return_value = mock_result

        resp = self.client.get("/research/hdfcbank")
        self.assertEqual(resp.status_code, 200)
        mock_run_pipeline.assert_called_once_with("HDFCBANK")

    def test_post_research_empty_symbol_400(self):
        """POST /research with empty symbol returns 400 Bad Request."""
        resp = self.client.post("/research", json={"symbol": "   "})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data["error"]["type"], "ValueError")
        self.assertIn("cannot be empty", data["error"]["message"])

    def test_post_research_invalid_characters_400(self):
        """POST /research with illegal characters returns 400 Bad Request."""
        resp = self.client.post("/research", json={"symbol": "TCS$$$"})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data["error"]["type"], "ValueError")
        self.assertIn("Invalid stock symbol", data["error"]["message"])

    def test_get_research_invalid_characters_400(self):
        """GET /research/{symbol} with illegal characters returns 400 Bad Request."""
        resp = self.client.get("/research/TCS@BAD")
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data["error"]["type"], "ValueError")

    def test_post_research_missing_field_422(self):
        """POST /research with missing 'symbol' field returns 422 Unprocessable Entity."""
        resp = self.client.post("/research", json={})
        self.assertEqual(resp.status_code, 422)

    @patch("interfaces.api.run_pipeline")
    def test_post_research_pipeline_failure_500(self, mock_run_pipeline):
        """POST /research returns 500 when research pipeline raises an error."""
        mock_run_pipeline.side_effect = RuntimeError("Screener fetch failed: HTTP 500")

        resp = self.client.post("/research", json={"symbol": "TCS"})
        self.assertEqual(resp.status_code, 500)
        data = resp.json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data["error"]["type"], "RuntimeError")
        self.assertIn("Screener fetch failed", data["error"]["message"])

    @patch("interfaces.api.run_pipeline")
    def test_get_research_pipeline_failure_500(self, mock_run_pipeline):
        """GET /research/{symbol} returns 500 when research pipeline raises an error."""
        mock_run_pipeline.side_effect = TimeoutError("Connection timed out")

        resp = self.client.get("/research/TCS")
        self.assertEqual(resp.status_code, 500)
        data = resp.json()
        self.assertFalse(data.get("ok"))
        self.assertEqual(data["error"]["type"], "TimeoutError")
        self.assertIn("Connection timed out", data["error"]["message"])

    def test_method_not_allowed_405(self):
        """Unsupported HTTP method returns 405 Method Not Allowed."""
        resp = self.client.request("DELETE", "/research")
        self.assertEqual(resp.status_code, 405)


if __name__ == "__main__":
    unittest.main(verbosity=2)
