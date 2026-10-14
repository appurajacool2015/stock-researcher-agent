#!/usr/bin/env python3
"""
Unit tests for skills/stock-research/run.py

Verifies:
1. End-to-end execution on cache hit.
2. End-to-end execution on cache miss (Fetch -> Assess -> Persist -> Explain).
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


class TestSkillRun(unittest.TestCase):

    @patch.object(_skill_run_mod, "SupabaseRepository")
    def test_cache_hit_execution(self, mock_repo_cls):
        """When cache returns valid data, execute_stock_research returns cached payload directly."""
        mock_repo = MagicMock()
        mock_rec = {
            "id": "rec-cached-1",
            "symbol": "TCS",
            "company_name": "Tata Consultancy Services Ltd",
            "technical_classification": "BUY_CANDIDATE",
            "investment_action": "BUY_CANDIDATE",
            "is_cached": True,
        }
        mock_snap = _mock_research_result("TCS")
        mock_repo.get_cached_assessment.return_value = (mock_rec, mock_snap)
        mock_repo_cls.return_value = mock_repo

        result = execute_stock_research("tcs")

        self.assertTrue(result["ok"])
        self.assertTrue(result["is_cached"])
        self.assertEqual(result["recommendation"]["id"], "rec-cached-1")
        mock_repo.get_cached_assessment.assert_called_once_with(
            symbol="TCS",
            force_refresh=False,
        )

    @patch.object(_skill_run_mod, "ResearchClient")
    @patch.object(_skill_run_mod, "SupabaseRepository")
    def test_cache_miss_full_pipeline(self, mock_repo_cls, mock_client_cls):
        """Cache miss fetches from Render, evaluates assessment, and persists to Supabase."""
        mock_repo = MagicMock()
        mock_repo.is_configured = True
        mock_repo.get_cached_assessment.return_value = (None, None)
        mock_repo.save_research_snapshot.return_value = {"saved": True, "id": "snap-new-1"}
        mock_repo.save_recommendation.return_value = {"saved": True, "id": "rec-new-1"}
        mock_repo_cls.return_value = mock_repo

        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_research_result("INFY")
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
    @patch.object(_skill_run_mod, "SupabaseRepository")
    def test_unconfigured_persistence_surfaces_notice(self, mock_repo_cls, mock_client_cls):
        """Unconfigured Supabase repo surfaces persistence notice in markdown without failing."""
        mock_repo = MagicMock()
        mock_repo.is_configured = False
        mock_repo.get_cached_assessment.return_value = (None, None)
        mock_repo_cls.return_value = mock_repo

        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_research_result("RELIANCE")
        mock_client_cls.return_value = mock_client

        result = execute_stock_research("RELIANCE")

        self.assertTrue(result["ok"])
        self.assertFalse(result["persistence_status"]["saved"])
        self.assertIn("Audit Persistence Notice:", result["markdown_response"])

    @patch.object(_skill_run_mod, "ResearchClient")
    @patch.object(_skill_run_mod, "SupabaseRepository")
    def test_snapshot_persistence_failure_includes_error(self, mock_repo_cls, mock_client_cls):
        """When snapshot persistence fails, persistence_status includes the repository error."""
        mock_repo = MagicMock()
        mock_repo.is_configured = True
        mock_repo.get_cached_assessment.return_value = (None, None)
        mock_repo.save_research_snapshot.return_value = {
            "saved": False,
            "id": None,
            "error": 'HTTP 403: {"code":"42501","message":"new row violates row-level security policy"}',
            "warning": "Assessment generated successfully but snapshot persistence failed.",
        }
        mock_repo_cls.return_value = mock_repo

        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_research_result("TCS")
        mock_client_cls.return_value = mock_client

        result = execute_stock_research("TCS")

        self.assertTrue(result["ok"])
        self.assertFalse(result["persistence_status"]["saved"])
        self.assertEqual(
            result["persistence_status"]["warning"],
            "Assessment generated successfully but snapshot persistence failed.",
        )
        self.assertEqual(
            result["persistence_status"]["error"],
            'HTTP 403: {"code":"42501","message":"new row violates row-level security policy"}',
        )
        mock_repo.save_recommendation.assert_not_called()

    @patch.object(_skill_run_mod, "ResearchClient")
    @patch.object(_skill_run_mod, "SupabaseRepository")
    def test_recommendation_persistence_failure_includes_error(self, mock_repo_cls, mock_client_cls):
        """When recommendation persistence fails, persistence_status includes the repository error."""
        mock_repo = MagicMock()
        mock_repo.is_configured = True
        mock_repo.get_cached_assessment.return_value = (None, None)
        mock_repo.save_research_snapshot.return_value = {"saved": True, "id": "snap-ok-1"}
        mock_repo.save_recommendation.return_value = {
            "saved": False,
            "id": None,
            "error": 'HTTP 400: {"message":"invalid input syntax for type numeric"}',
            "warning": "Assessment generated successfully but recommendation persistence failed.",
        }
        mock_repo_cls.return_value = mock_repo

        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_research_result("TCS")
        mock_client_cls.return_value = mock_client

        result = execute_stock_research("TCS")

        self.assertTrue(result["ok"])
        self.assertFalse(result["persistence_status"]["saved"])
        self.assertEqual(
            result["persistence_status"]["warning"],
            "Assessment generated successfully but recommendation persistence failed.",
        )
        self.assertEqual(
            result["persistence_status"]["error"],
            'HTTP 400: {"message":"invalid input syntax for type numeric"}',
        )

    @patch.object(_skill_run_mod, "ResearchClient")
    @patch.object(_skill_run_mod, "SupabaseRepository")
    def test_default_env_is_prod(self, mock_repo_cls, mock_client_cls):
        """Default execution environment is PROD with Render API routing and Supabase persistence."""
        mock_repo = MagicMock()
        mock_repo.is_configured = False
        mock_repo.get_cached_assessment.return_value = (None, None)
        mock_repo_cls.return_value = mock_repo

        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_research_result("TCS")
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
    @patch.object(_skill_run_mod, "SupabaseRepository")
    def test_prod_mode_never_allows_local_fallback_on_render_failure(self, mock_repo_cls, mock_client_cls):
        """PROD mode strictly passes allow_local_fallback=False and raises on Render failure."""
        mock_repo = MagicMock()
        mock_repo.get_cached_assessment.return_value = (None, None)
        mock_repo_cls.return_value = mock_repo

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
            mock_repo.save_research_snapshot.assert_not_called()

    @patch.object(_skill_run_mod, "ResearchClient")
    @patch.object(_skill_run_mod, "SupabaseRepository")
    def test_dev_mode_local_pipeline_and_supabase_bypass(self, mock_repo_cls, mock_client_cls):
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
            mock_repo_cls.assert_not_called()

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
    @patch.object(_skill_run_mod, "SupabaseRepository")
    def test_backward_compatibility_positional_calls(self, mock_repo_cls, mock_client_cls):
        """Existing positional calls retain their argument semantics without distortion."""
        mock_repo = MagicMock()
        mock_repo.is_configured = False
        mock_repo.get_cached_assessment.return_value = (None, None)
        mock_repo_cls.return_value = mock_repo

        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_research_result("TCS")
        mock_client_cls.return_value = mock_client

        # 1. Single positional argument: (raw_symbol)
        res1 = execute_stock_research("TCS")
        self.assertEqual(res1["execution_env"], "prod")
        mock_repo.get_cached_assessment.assert_called_with(symbol="TCS", force_refresh=False)

        # 2. Two positional arguments: (raw_symbol, force_refresh)
        res2 = execute_stock_research("TCS", True)
        self.assertEqual(res2["execution_env"], "prod")
        mock_repo.get_cached_assessment.assert_called_with(symbol="TCS", force_refresh=True)

        # 3. Three positional arguments: (raw_symbol, force_refresh, allow_local_fallback)
        res3 = execute_stock_research("TCS", False, True)
        self.assertEqual(res3["execution_env"], "prod")
        mock_repo.get_cached_assessment.assert_called_with(symbol="TCS", force_refresh=False)

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
    @patch.object(_skill_run_mod, "SupabaseRepository")
    def test_cli_main_prod_mode(self, mock_repo_cls, mock_client_cls):
        """CLI main in PROD mode outputs JSON with execution_env: prod and data_source: render_api."""
        mock_repo = MagicMock()
        mock_repo.is_configured = False
        mock_repo.get_cached_assessment.return_value = (None, None)
        mock_repo_cls.return_value = mock_repo

        mock_client = MagicMock()
        mock_client.fetch_research.return_value = _mock_research_result("INFY")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
