#!/usr/bin/env python3
"""
Unit tests for skills/stock-research/run.py

Verifies:
1. End-to-end execution on cache hit (server signals is_cached=True via _persistence).
2. End-to-end execution on cache miss (Fetch -> Assess -> Explain; persistence from _persistence block).
3. Unconfigured persistence handles gracefully and surfaces persistence notice.
4. CLI parsing and JSON output mode.
"""

from __future__ import annotations

import importlib
import io
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from services.research_client import RenderAPIError

_skill_run_mod = importlib.import_module("skills.stock-research.run")
execute_stock_research = _skill_run_mod.execute_stock_research


def _mock_research_result(symbol: str = "TCS") -> dict:
    return {
        "schema_version": "1.0",
        "research_id": f"{symbol.lower()}-run-123",
        "symbol": symbol,
        "exchange": "NSE",
        "company_name": f"{symbol} Limited",
        "overall_status": "PARTIAL",
        "technicals": {
            "provenance": {"as_of_date": "2026-10-10"},
            "cmp": {"value": 3500.0, "status": "VERIFIED"},
            "dma_50": {"value": 3400.0, "status": "VERIFIED"},
            "dma_200": {"value": 3200.0, "status": "VERIFIED"},
            "rsi_14": {"value": 55.0, "status": "VERIFIED"},
            "history_bars": {"value": 450, "status": "VERIFIED"},
            "obv_change_norm_14d": {"value": 0.05, "status": "VERIFIED"},
            "dma_slope_50": {"value": "RISING", "status": "VERIFIED"},
        },
        "fundamentals": {
            "provenance": {"as_of_date": "2026-06-30"},
            "roe": {"value": 25.0, "status": "VERIFIED"},
            "roce": {"value": 30.0, "status": "VERIFIED"},
            "sales_growth_3years_cagr": {"value": 12.0, "status": "VERIFIED"},
            "profit_growth_3years_cagr": {"value": 15.0, "status": "VERIFIED"},
            "pe_ratio": {"value": 28.0, "status": "VERIFIED"},
            "debt_to_equity": {"value": 0.0, "status": "VERIFIED"},
        },
        "institutional": {
            "promoter_pledge": {"value": 0.0, "status": "VERIFIED"},
        },
        "news": [],
        "data_quality_summary": {
            "verified": 20,
            "derived": 2,
            "unavailable": 0,
            "stale": 0,
            "conflicting": 0,
            "failed": 0,
        },
    }


def _mock_api_response(symbol: str = "TCS", persistence_override: dict | None = None) -> dict:
    """Return a simulated Render API response including a _persistence block."""
    base = _mock_research_result(symbol)
    base["_persistence"] = persistence_override if persistence_override is not None else {
        "saved": True,
        "is_cached": False,
        "recommendation_id": "rec-new-1",
        "snapshot_id": "snap-new-1",
        "is_duplicate": False,
        "track_record": {
            "status": "BASELINE_ESTABLISHED",
            "has_prior_history": False,
            "note": "Initial research baseline established.",
        },
        "warning": None,
    }
    return base


def _mock_cached_api_response(symbol: str = "TCS") -> dict:
    """Simulate a Render API response for a cache hit."""
    base = _mock_research_result(symbol)
    base["_persistence"] = {
        "saved": True,
        "is_cached": True,
        "recommendation_id": "rec-cached-1",
        "snapshot_id": "snap-cached-1",
        "is_duplicate": False,
        "track_record": {
            "status": "TRACK_RECORD_AVAILABLE",
            "has_prior_history": True,
            "first_researched_price": 3000.0,
            "latest_price": 3500.0,
            "price_change": 500.0,
            "price_return_pct": 16.67,
            "note": "Price return since initial baseline.",
        },
        "warning": None,
    }
    return base


class TestSkillRun(unittest.TestCase):

    @patch.object(_skill_run_mod, "ResearchClient")
    def test_cache_hit_execution(self, mock_client_cls):
        """When server signals is_cached=True in _persistence, execute_stock_research returns cached payload."""
        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_cached_api_response("TCS")
        mock_client_cls.return_value = mock_client

        result = execute_stock_research("tcs")

        self.assertTrue(result["ok"])
        self.assertTrue(result["is_cached"])
        self.assertEqual(result["persistence_status"]["id"], "rec-cached-1")
        mock_client.fetch_research.assert_called_once_with(
            raw_symbol="TCS",
            allow_local_fallback=False,
        )

    @patch.object(_skill_run_mod, "ResearchClient")
    def test_cache_miss_full_pipeline(self, mock_client_cls):
        """Cache miss: server runs fresh pipeline and returns persistence metadata in _persistence block."""
        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_api_response("INFY")
        mock_client_cls.return_value = mock_client

        result = execute_stock_research("INFY")

        self.assertTrue(result["ok"])
        self.assertFalse(result["is_cached"])
        self.assertEqual(result["symbol"], "INFY")
        self.assertEqual(result["persistence_status"]["id"], "rec-new-1")
        mock_client.fetch_research.assert_called_once_with(
            raw_symbol="INFY",
            allow_local_fallback=False,
        )

    @patch.object(_skill_run_mod, "ResearchClient")
    def test_unconfigured_persistence_surfaces_notice(self, mock_client_cls):
        """Server returns saved=False with warning; client surfaces persistence notice in markdown."""
        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_api_response(
            "RELIANCE",
            persistence_override={
                "saved": False,
                "is_cached": False,
                "recommendation_id": None,
                "snapshot_id": None,
                "is_duplicate": False,
                "track_record": {"status": "UNAVAILABLE", "note": "Supabase not configured on server."},
                "warning": "Supabase not configured on server; persistence skipped.",
            },
        )
        mock_client_cls.return_value = mock_client

        result = execute_stock_research("RELIANCE")

        self.assertTrue(result["ok"])
        self.assertFalse(result["persistence_status"]["saved"])
        self.assertIn("Audit Persistence Notice:", result["markdown_response"])

    @patch.object(_skill_run_mod, "ResearchClient")
    def test_snapshot_persistence_failure_includes_warning(self, mock_client_cls):
        """When server reports snapshot persistence failure, persistence_status reflects the warning."""
        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_api_response(
            "TCS",
            persistence_override={
                "saved": False,
                "is_cached": False,
                "recommendation_id": None,
                "snapshot_id": None,
                "is_duplicate": False,
                "track_record": {"status": "UNAVAILABLE", "note": "Persistence failed."},
                "warning": "Assessment generated successfully but snapshot persistence failed.",
            },
        )
        mock_client_cls.return_value = mock_client

        result = execute_stock_research("TCS")

        self.assertTrue(result["ok"])
        self.assertFalse(result["persistence_status"]["saved"])
        self.assertEqual(
            result["persistence_status"]["warning"],
            "Assessment generated successfully but snapshot persistence failed.",
        )

    @patch.object(_skill_run_mod, "ResearchClient")
    def test_recommendation_persistence_failure_includes_warning(self, mock_client_cls):
        """When server reports recommendation persistence failure, persistence_status reflects the warning."""
        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_api_response(
            "TCS",
            persistence_override={
                "saved": False,
                "is_cached": False,
                "recommendation_id": None,
                "snapshot_id": "snap-ok-1",
                "is_duplicate": False,
                "track_record": {"status": "UNAVAILABLE", "note": "Recommendation write failed."},
                "warning": "Assessment generated successfully but recommendation persistence failed.",
            },
        )
        mock_client_cls.return_value = mock_client

        result = execute_stock_research("TCS")

        self.assertTrue(result["ok"])
        self.assertFalse(result["persistence_status"]["saved"])
        self.assertEqual(
            result["persistence_status"]["warning"],
            "Assessment generated successfully but recommendation persistence failed.",
        )

    @patch.object(_skill_run_mod, "ResearchClient")
    def test_default_env_is_prod(self, mock_client_cls):
        """Default execution environment is PROD with Render API routing."""
        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_api_response("TCS")
        mock_client_cls.return_value = mock_client

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STOCK_RESEARCH_ENV", None)
            result = execute_stock_research("TCS")

        self.assertEqual(result["execution_env"], "prod")
        self.assertEqual(result["data_source"], "render_api")
        mock_client.fetch_research.assert_called_once_with(
            raw_symbol="TCS",
            allow_local_fallback=False,
        )

    def test_env_resolution_precedence_and_case_insensitivity(self):
        """CLI option takes precedence over STOCK_RESEARCH_ENV, both are case-insensitive."""
        resolve_env = _skill_run_mod.resolve_execution_env

        # Case insensitivity for explicit CLI argument
        for val in ["dev", "DEV", "Dev", "dEv"]:
            self.assertEqual(resolve_env(val), "dev")
        for val in ["prod", "PROD", "Prod", "pRoD"]:
            self.assertEqual(resolve_env(val), "prod")

        # Environment variable resolution when cli_env is None
        with patch.dict(os.environ, {"STOCK_RESEARCH_ENV": "dev"}):
            self.assertEqual(resolve_env(None), "dev")
        with patch.dict(os.environ, {"STOCK_RESEARCH_ENV": "DEV"}):
            self.assertEqual(resolve_env(None), "dev")
        with patch.dict(os.environ, {"STOCK_RESEARCH_ENV": "prod"}):
            self.assertEqual(resolve_env(None), "prod")
        with patch.dict(os.environ, {"STOCK_RESEARCH_ENV": "PROD"}):
            self.assertEqual(resolve_env(None), "prod")

        # CLI precedence over STOCK_RESEARCH_ENV
        with patch.dict(os.environ, {"STOCK_RESEARCH_ENV": "dev"}):
            self.assertEqual(resolve_env("prod"), "prod")
            self.assertEqual(resolve_env("PROD"), "prod")
        with patch.dict(os.environ, {"STOCK_RESEARCH_ENV": "prod"}):
            self.assertEqual(resolve_env("dev"), "dev")
            self.assertEqual(resolve_env("DEV"), "dev")
        with patch.dict(os.environ, {"STOCK_RESEARCH_ENV": "invalid_env"}):
            self.assertEqual(resolve_env("dev"), "dev")
            self.assertEqual(resolve_env("prod"), "prod")

    def test_invalid_env_raises_clean_error(self):
        """Invalid environment in CLI or env var raises ValueError and does not default silently."""
        resolve_env = _skill_run_mod.resolve_execution_env

        # Invalid CLI values
        for invalid in ["staging", "test", "local", "123", ""]:
            with self.assertRaises(ValueError) as ctx:
                resolve_env(invalid)
            self.assertIn("Must be 'dev' or 'prod'", str(ctx.exception))

        # Invalid STOCK_RESEARCH_ENV
        for invalid in ["staging", "uat", "qa"]:
            with patch.dict(os.environ, {"STOCK_RESEARCH_ENV": invalid}):
                with self.assertRaises(ValueError) as ctx:
                    resolve_env(None)
                self.assertIn("Must be 'dev' or 'prod'", str(ctx.exception))

        # Direct execute_stock_research call with invalid env
        with self.assertRaises(ValueError) as ctx:
            execute_stock_research("TCS", env="invalid_value")
        self.assertIn("Must be 'dev' or 'prod'", str(ctx.exception))

    @patch.object(_skill_run_mod, "ResearchClient")
    def test_prod_mode_never_allows_local_fallback_on_render_failure(self, mock_client_cls):
        """PROD mode strictly passes allow_local_fallback=False and raises on Render failure."""
        mock_client = MagicMock()
        mock_client.fetch_research.side_effect = RenderAPIError("Render API 503 Service Unavailable")
        mock_client_cls.return_value = mock_client

        with patch.object(_skill_run_mod, "run_pipeline") as mock_pipeline:
            with self.assertRaises(RenderAPIError):
                execute_stock_research("TCS", env="prod", allow_local_fallback=True)

            mock_client.fetch_research.assert_called_once_with(
                raw_symbol="TCS",
                allow_local_fallback=False,
            )
            mock_pipeline.assert_not_called()

    @patch.object(_skill_run_mod, "ResearchClient")
    def test_dev_mode_local_pipeline_and_supabase_bypass(self, mock_client_cls):
        """DEV mode routes to local pipeline and completely bypasses Supabase cache and persistence."""
        mock_pipeline_result = _mock_research_result("TCS")

        with patch.object(_skill_run_mod, "run_pipeline", return_value=mock_pipeline_result) as mock_local_run:
            result = execute_stock_research("tcs", env="dev")

            self.assertTrue(result["ok"])
            self.assertEqual(result["symbol"], "TCS")
            self.assertFalse(result["is_cached"])
            self.assertEqual(result["execution_env"], "dev")
            self.assertEqual(result["data_source"], "local_pipeline")
            self.assertEqual(
                result["persistence_status"],
                {"saved": False, "warning": "Supabase persistence skipped in DEV mode"},
            )
            self.assertIn(
                "Audit Persistence Notice: Supabase persistence skipped in DEV mode",
                result["markdown_response"],
            )

            mock_local_run.assert_called_once_with(symbol="TCS")
            mock_client_cls.assert_not_called()

    def test_dev_mode_invokes_pipeline_exactly_once(self):
        """DEV mode directly invokes run_pipeline exactly once using its verified signature."""
        mock_pipeline_result = _mock_research_result("RELIANCE")

        with patch.object(_skill_run_mod, "run_pipeline", return_value=mock_pipeline_result) as mock_run:
            result = execute_stock_research("reliance", env="dev")

        self.assertEqual(mock_run.call_count, 1)
        mock_run.assert_called_once_with(symbol="RELIANCE")
        self.assertEqual(result["symbol"], "RELIANCE")
        self.assertEqual(result["execution_env"], "dev")
        self.assertEqual(result["data_source"], "local_pipeline")

    @patch.object(_skill_run_mod, "ResearchClient")
    def test_backward_compatibility_positional_calls(self, mock_client_cls):
        """Existing positional calls retain their argument semantics without distortion."""
        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_api_response("TCS")
        mock_client_cls.return_value = mock_client

        # 1. Single positional argument: (raw_symbol)
        res1 = execute_stock_research("TCS")
        self.assertEqual(res1["execution_env"], "prod")

        # 2. Two positional arguments: (raw_symbol, force_refresh) — force_refresh ignored server-side
        res2 = execute_stock_research("TCS", True)
        self.assertEqual(res2["execution_env"], "prod")

        # 3. Three positional arguments: (raw_symbol, force_refresh, allow_local_fallback)
        res3 = execute_stock_research("TCS", False, True)
        self.assertEqual(res3["execution_env"], "prod")

        # 4. Four positional arguments: (raw_symbol, force_refresh, allow_local_fallback, use_gemini)
        res4 = execute_stock_research("TCS", False, False, False)
        self.assertEqual(res4["execution_env"], "prod")

        # 5. Positional environment string: (raw_symbol, env_string)
        mock_pipeline_result = _mock_research_result("TCS")
        with patch.object(_skill_run_mod, "run_pipeline", return_value=mock_pipeline_result) as mock_local_run:
            res5 = execute_stock_research("TCS", "dev")
            self.assertEqual(res5["execution_env"], "dev")
            self.assertEqual(res5["data_source"], "local_pipeline")
            mock_local_run.assert_called_once_with(symbol="TCS")

    @patch.object(_skill_run_mod, "ResearchClient")
    def test_cli_main_prod_mode(self, mock_client_cls):
        """CLI main in PROD mode outputs JSON with execution_env: prod and data_source: render_api."""
        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_api_response("INFY")
        mock_client_cls.return_value = mock_client

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            ret = _skill_run_mod.main(["INFY", "--env", "PROD", "--json"])

        self.assertEqual(ret, 0)
        output = json.loads(stdout_buf.getvalue())
        self.assertTrue(output["ok"])
        self.assertEqual(output["execution_env"], "prod")
        self.assertEqual(output["data_source"], "render_api")

    def test_cli_main_dev_mode(self):
        """CLI main in DEV mode outputs JSON with execution_env: dev and data_source: local_pipeline."""
        mock_pipeline_result = _mock_research_result("TCS")

        with patch.object(_skill_run_mod, "run_pipeline", return_value=mock_pipeline_result):
            stdout_buf = io.StringIO()
            with patch("sys.stdout", stdout_buf):
                ret = _skill_run_mod.main(["TCS", "--env", "dev", "--json"])

            self.assertEqual(ret, 0)
            output = json.loads(stdout_buf.getvalue())
            self.assertTrue(output["ok"])
            self.assertEqual(output["execution_env"], "dev")
            self.assertEqual(output["data_source"], "local_pipeline")
            self.assertFalse(output["is_cached"])
            self.assertEqual(
                output["persistence_status"],
                {"saved": False, "warning": "Supabase persistence skipped in DEV mode"},
            )

    def test_cli_main_invalid_env_returns_error(self):
        """CLI main with invalid --env returns exit code 1 with clean error payload in JSON mode."""
        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            ret = _skill_run_mod.main(["TCS", "--env", "staging", "--json"])

        self.assertEqual(ret, 1)
        output = json.loads(stdout_buf.getvalue())
        self.assertFalse(output["ok"])
        self.assertEqual(output["error"]["type"], "ValueError")
        self.assertIn("Must be 'dev' or 'prod'", output["error"]["message"])

    @patch.object(_skill_run_mod, "ResearchClient")
    def test_track_record_first_time_research_establishes_baseline(self, mock_client_cls):
        """Server signals BASELINE_ESTABLISHED in _persistence; client exposes it in track_record."""
        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_api_response(
            "TCS",
            persistence_override={
                "saved": True,
                "is_cached": False,
                "recommendation_id": "rec-1",
                "snapshot_id": "snap-1",
                "is_duplicate": False,
                "track_record": {
                    "status": "BASELINE_ESTABLISHED",
                    "has_prior_history": False,
                    "note": "Initial research baseline established. No prior history to compare.",
                },
                "warning": None,
            },
        )
        mock_client_cls.return_value = mock_client

        result = execute_stock_research("TCS")

        self.assertTrue(result["ok"])
        self.assertFalse(result["is_cached"])
        tr = result["track_record"]
        self.assertEqual(tr["status"], "BASELINE_ESTABLISHED")
        self.assertFalse(tr["has_prior_history"])
        self.assertIn("Initial research baseline established", tr["note"])
        self.assertIn("Initial baseline established", result["markdown_response"])

    @patch.object(_skill_run_mod, "ResearchClient")
    def test_track_record_subsequent_research_computes_return_against_baseline(self, mock_client_cls):
        """Server computes track record and returns it in _persistence; client exposes it correctly."""
        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_api_response(
            "TCS",
            persistence_override={
                "saved": True,
                "is_cached": False,
                "recommendation_id": "rec-2",
                "snapshot_id": "snap-2",
                "is_duplicate": False,
                "track_record": {
                    "status": "TRACK_RECORD_AVAILABLE",
                    "has_prior_history": True,
                    "first_researched_price": 3000.0,
                    "latest_price": 3500.0,
                    "price_change": 500.0,
                    "price_return_pct": 16.67,
                    "note": "Price return since initial baseline.",
                },
                "warning": None,
            },
        )
        mock_client_cls.return_value = mock_client

        result = execute_stock_research("TCS")

        self.assertTrue(result["ok"])
        tr = result["track_record"]
        self.assertEqual(tr["status"], "TRACK_RECORD_AVAILABLE")
        self.assertTrue(tr["has_prior_history"])
        self.assertEqual(tr["first_researched_price"], 3000.0)
        self.assertEqual(tr["latest_price"], 3500.0)
        self.assertEqual(tr["price_change"], 500.0)
        self.assertAlmostEqual(tr["price_return_pct"], 16.67, places=2)
        self.assertIn("First researched", result["markdown_response"])
        self.assertIn("Price Return (Research Baseline):", result["markdown_response"])
        self.assertIn("+16.67%", result["markdown_response"])

    @patch.object(_skill_run_mod, "ResearchClient")
    def test_track_record_cache_hit_preserves_history_with_zero_duplicate_inserts(self, mock_client_cls):
        """Cache hit: server returns is_cached=True and track record; client makes no extra DB calls."""
        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_cached_api_response("TCS")
        mock_client_cls.return_value = mock_client

        result = execute_stock_research("TCS")

        self.assertTrue(result["ok"])
        self.assertTrue(result["is_cached"])
        tr = result["track_record"]
        self.assertEqual(tr["status"], "TRACK_RECORD_AVAILABLE")
        self.assertEqual(tr["first_researched_price"], 3000.0)
        self.assertEqual(tr["latest_price"], 3500.0)
        self.assertEqual(tr["price_change"], 500.0)
        self.assertAlmostEqual(tr["price_return_pct"], 16.67, places=2)

        # Client makes exactly one API call; no Supabase calls from client side
        mock_client.fetch_research.assert_called_once()

    @patch.object(_skill_run_mod, "ResearchClient")
    def test_track_record_database_failure_resilience(self, mock_client_cls):
        """Server signals UNAVAILABLE track record on DB failure; client surfaces it without crashing."""
        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_api_response(
            "TCS",
            persistence_override={
                "saved": True,
                "is_cached": False,
                "recommendation_id": "rec-1",
                "snapshot_id": "snap-1",
                "is_duplicate": False,
                "track_record": {
                    "status": "UNAVAILABLE",
                    "note": "Historical track record temporarily unavailable due to database lookup error.",
                },
                "warning": None,
            },
        )
        mock_client_cls.return_value = mock_client

        result = execute_stock_research("TCS")

        self.assertTrue(result["ok"])
        tr = result["track_record"]
        self.assertEqual(tr["status"], "UNAVAILABLE")
        self.assertIn("temporarily unavailable", tr["note"])
        self.assertIn(
            "Historical track record temporarily unavailable due to database lookup error",
            result["markdown_response"],
        )

    def test_track_record_dev_mode_indicates_bypass(self):
        """DEV mode bypasses Supabase and explicitly flags track record as UNAVAILABLE."""
        mock_pipeline_result = _mock_research_result("TCS")

        with patch.object(_skill_run_mod, "run_pipeline", return_value=mock_pipeline_result):
            result = execute_stock_research("TCS", env="dev")

        self.assertTrue(result["ok"])
        self.assertEqual(result["execution_env"], "dev")
        tr = result["track_record"]
        self.assertEqual(tr["status"], "UNAVAILABLE")
        self.assertIn("disabled in local DEV mode", tr["note"])
        self.assertIn("Track record disabled in local DEV mode", result["markdown_response"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
