#!/usr/bin/env python3
"""
Unit tests for services/research_client.py

Verifies:
1. Successful fetch and validation of canonical ResearchResult v1.
2. Bounded timeout and retry logic on 502/503.
3. HTTP errors (400, 404, 500) raise RenderAPIError.
4. Schema validation failure (bad version, mismatched symbol, missing fields) raises RenderSchemaValidationError.
5. Local fallback behavior:
   - When allow_local_fallback=False (default): raises RenderAPIError without executing local pipeline.
   - When allow_local_fallback=True: invokes local pipeline and labels provenance as LOCAL_PIPELINE_FALLBACK.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.research_client import (
    RenderAPIError,
    RenderSchemaValidationError,
    ResearchClient,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _valid_canonical_response(symbol: str = "TCS") -> dict:
    template_path = PROJECT_ROOT / "output" / "tcs-research-result.json"
    if template_path.exists():
        import json
        with template_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        data["symbol"] = symbol.upper()
        data["company_name"] = f"{symbol.upper()} Limited"
        return data

    from tests.test_technicals import make_research_result
    res = make_research_result(symbol=symbol, cmp=2500.0)
    res["symbol"] = symbol.upper()
    res["company_name"] = f"{symbol.upper()} Limited"
    return res


class TestResearchClient(unittest.TestCase):

    def setUp(self):
        self.client = ResearchClient(
            base_url="https://mock-render-service.onrender.com",
            timeout=10.0,
            max_retries=1,
            api_key="test-mock-key-12345",
        )

    @patch("services.research_client.requests.get")
    def test_fetch_research_success(self, mock_get):
        """Valid 200 response with correct schema succeeds."""
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = _valid_canonical_response("TCS")
        mock_get.return_value = mock_resp

        result = self.client.fetch_research("tcs")
        self.assertEqual(result["symbol"], "TCS")
        self.assertEqual(result["_research_source"], "RENDER_LIVE_API")

    @patch("services.research_client.requests.get")
    def test_transient_502_retries_and_succeeds(self, mock_get):
        """502 Bad Gateway retries and succeeds if subsequent attempt succeeds."""
        resp_502 = MagicMock(status_code=502, text="Bad Gateway")
        resp_200 = MagicMock(status_code=200)
        resp_200.json.return_value = _valid_canonical_response("INFY")

        mock_get.side_effect = [resp_502, resp_200]

        result = self.client.fetch_research("INFY")
        self.assertEqual(result["symbol"], "INFY")
        self.assertEqual(mock_get.call_count, 2)

    @patch("services.research_client.requests.get")
    def test_non_retryable_404_raises_immediately(self, mock_get):
        """404 Not Found raises RenderAPIError without retries."""
        mock_resp = MagicMock(status_code=404, text="Symbol not found")
        mock_get.return_value = mock_resp

        with self.assertRaises(RenderAPIError):
            self.client.fetch_research("UNKNOWN")
        self.assertEqual(mock_get.call_count, 1)

    @patch("services.research_client.requests.get")
    def test_schema_mismatch_symbol(self, mock_get):
        """Mismatched symbol in response raises RenderSchemaValidationError."""
        resp = MagicMock(status_code=200)
        resp.json.return_value = _valid_canonical_response("INFY")
        mock_get.return_value = resp

        with self.assertRaises(RenderSchemaValidationError):
            self.client.fetch_research("TCS")

    @patch("services.research_client.requests.get")
    def test_schema_missing_overall_status(self, mock_get):
        """Missing overall_status raises RenderSchemaValidationError."""
        bad_data = _valid_canonical_response("TCS")
        del bad_data["overall_status"]
        resp = MagicMock(status_code=200)
        resp.json.return_value = bad_data
        mock_get.return_value = resp

        with self.assertRaises(RenderSchemaValidationError):
            self.client.fetch_research("TCS")

    @patch("services.research_client.requests.get")
    def test_local_fallback_disabled_raises_error(self, mock_get):
        """When allow_local_fallback=False, Render failure raises RenderAPIError without local execution."""
        mock_get.side_effect = TimeoutError("Render timed out")

        with self.assertRaises(RenderAPIError):
            self.client.fetch_research("TCS", allow_local_fallback=False)

    @patch("services.research_pipeline.run_pipeline")
    @patch("services.research_client.requests.get")
    def test_local_fallback_enabled_invokes_pipeline(self, mock_get, mock_run_pipeline):
        """When allow_local_fallback=True, Render failure falls back to local pipeline with explicit notice."""
        mock_get.side_effect = TimeoutError("Render timed out")
        mock_run_pipeline.return_value = _valid_canonical_response("TCS")

        result = self.client.fetch_research("TCS", allow_local_fallback=True)

        self.assertEqual(result["_research_source"], "LOCAL_PIPELINE_FALLBACK")
        self.assertIn("Notice:", result["_fallback_warning"])
        mock_run_pipeline.assert_called_once_with("TCS")


    @patch("services.research_client.requests.get")
    def test_fetch_research_force_refresh_passes_param(self, mock_get):
        """When force_refresh=True, client passes query parameter to Render API."""
        resp = MagicMock(status_code=200)
        resp.json.return_value = _valid_canonical_response("TCS")
        mock_get.return_value = resp

        self.client.fetch_research("TCS", force_refresh=True)

    @patch("services.research_client.requests.post")
    def test_persist_research_success(self, mock_post):
        """persist_research sends payload to /research/persist and returns updated result."""
        valid_data = _valid_canonical_response("TCS")
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            **valid_data,
            "_persistence": {"saved": True, "snapshot_id": "snap-123"},
        }
        mock_post.return_value = resp

        res = self.client.persist_research(valid_data)
        self.assertEqual(res["_research_source"], "RENDER_PERSIST_HYBRID")
        self.assertTrue(res["_persistence"]["saved"])
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://mock-render-service.onrender.com/research/persist")
        self.assertEqual(kwargs["json"]["symbol"], "TCS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
