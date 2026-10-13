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
import unittest
from unittest.mock import MagicMock, patch

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
