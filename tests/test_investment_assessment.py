#!/usr/bin/env python3
"""
Unit tests for intelligence/investment_assessment.py

Verifies:
1. Mutually exclusive classifications (Rules 1 to 5).
2. Rule 1: INSUFFICIENT_DATA on missing/failed price or fundamentals.
3. Rule 2: REDUCE_SELL_REVIEW on breakdown, severe pledge, or high leverage.
4. Rule 3: AVOID_NEW_ENTRY on technical avoid or extreme valuation.
5. Rule 4: BUY_CANDIDATE multi-factor confluence.
6. Guardrail: Technical BUY degraded to HOLD or AVOID when fundamentals fail.
7. Sector Applicability Guard: Banks/NBFCs debt-to-equity not penalized.
8. Debt-Free company handling (D/E = 0.0).
9. Missing/stale/conflicting data represented as limitations.
10. Custom configurable thresholds.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict

from intelligence.investment_assessment import (
    DEFAULT_THRESHOLDS,
    InvestmentThresholds,
    evaluate_investment_assessment,
)


def _base_mock_result(symbol: str = "TCS") -> Dict[str, Any]:
    """Create a healthy base mock ResearchResult v1."""
    return {
        "schema_version": "1.0",
        "research_id": f"{symbol.lower()}-test-run-001",
        "symbol": symbol,
        "exchange": "NSE",
        "company_name": f"{symbol} Limited",
        "overall_status": "VERIFIED",
        "requested_at": "2026-10-11T12:00:00Z",
        "completed_at": "2026-10-11T12:00:05Z",
        "technicals": {
            "provenance": {"as_of_date": "2026-10-10"},
            "cmp": {"value": 104.0, "status": "VERIFIED", "unit": "INR"},
            "dma_50": {"value": 100.0, "status": "VERIFIED", "unit": "INR"},
            "dma_200": {"value": 90.0, "status": "VERIFIED", "unit": "INR"},
            "pct_from_50_dma": {"value": 4.0, "status": "VERIFIED", "unit": "PERCENT"},
            "dma_alignment": {"value": "50_DMA_ABOVE_200_DMA", "status": "VERIFIED"},
            "dma_slope_50": {"value": "RISING", "status": "VERIFIED"},
            "rsi_14": {"value": 58.0, "status": "VERIFIED", "unit": "INDEX"},
            "atr_14": {"value": 5.0, "status": "VERIFIED", "unit": "INR"},
            "clv": {"value": 0.25, "status": "VERIFIED", "unit": "RATIO"},
            "clv_14_avg": {"value": 0.15, "status": "VERIFIED", "unit": "RATIO"},
            "obv_change_norm_14d": {"value": 0.25, "status": "VERIFIED", "unit": "RATIO"},
            "history_bars": {"value": 450, "status": "VERIFIED"},
            "volume_vs_20_dma_pct": {"value": 15.0, "status": "VERIFIED"},
            "swing_high_20": {"value": 115.0, "status": "VERIFIED", "unit": "INR"},
            "swing_high_confirmation_date": {"value": "2026-08-15", "status": "VERIFIED", "unit": "DATE"},
            "pct_from_swing_high": {"value": -9.56, "status": "VERIFIED", "unit": "PERCENT"},
            "swing_low_20": {"value": 95.0, "status": "VERIFIED"},
            "fifty_two_week_high": {"value": 120.0, "status": "VERIFIED"},
            "fifty_two_week_low": {"value": 80.0, "status": "VERIFIED"},
        },
        "fundamentals": {
            "provenance": {"as_of_date": "2026-06-30"},
            "roe": {"value": 25.0, "status": "VERIFIED", "unit": "PERCENT"},
            "roce": {"value": 30.0, "status": "VERIFIED", "unit": "PERCENT"},
            "sales_growth_3y_cagr": {"value": 12.0, "status": "VERIFIED", "unit": "PERCENT"},
            "profit_growth_3y_cagr": {"value": 15.0, "status": "VERIFIED", "unit": "PERCENT"},
            "pe_ratio": {"value": 28.0, "status": "VERIFIED", "unit": "RATIO"},
            "pb_ratio": {"value": 6.0, "status": "VERIFIED", "unit": "RATIO"},
            "debt_to_equity": {"value": 0.10, "status": "VERIFIED", "unit": "RATIO"},
            "market_cap": {"value": 1200000.0, "status": "VERIFIED", "unit": "CRORE"},
        },
        "institutional": {
            "promoter_holding": {"value": 72.0, "status": "VERIFIED", "unit": "PERCENT"},
            "promoter_pledge_pct": {"value": 0.0, "status": "VERIFIED", "unit": "PERCENT"},
            "fii_holding": {"value": 15.0, "status": "VERIFIED", "unit": "PERCENT"},
            "dii_holding": {"value": 8.0, "status": "VERIFIED", "unit": "PERCENT"},
        },
        "news": [],
        "data_quality_summary": {
            "verified": 25,
            "derived": 4,
            "unavailable": 0,
            "stale": 0,
            "conflicting": 0,
            "failed": 0,
        },
    }


class TestInvestmentAssessment(unittest.TestCase):

    def test_buy_candidate_confluence(self):
        """Rule 4: Full confluence between technical BUY and strong fundamentals produces BUY_CANDIDATE."""
        data = _base_mock_result("TCS")
        rec = evaluate_investment_assessment(data)

        self.assertEqual(rec["investment_action"], "BUY_CANDIDATE")
        self.assertEqual(rec["technical_classification"], "BUY_CANDIDATE")
        self.assertGreaterEqual(rec["investment_score"], 70.0)
        self.assertIn("RULE4_MULTI_FACTOR_BUY_CONFLUENCE", rec["reason_codes"])
        self.assertGreater(len(rec["positive_factors"]), 0)

    def test_rule1_insufficient_data_pipeline_failed(self):
        """Rule 1: Overall pipeline failure triggers INSUFFICIENT_DATA."""
        data = _base_mock_result("FAILED_CO")
        data["overall_status"] = "FAILED"
        rec = evaluate_investment_assessment(data)

        self.assertEqual(rec["investment_action"], "INSUFFICIENT_DATA")
        self.assertIsNone(rec["investment_score"])
        self.assertIn("RULE1_PIPELINE_STATUS_FAILED", rec["reason_codes"])

    def test_rule1_insufficient_data_missing_cmp(self):
        """Rule 1: Missing CMP triggers INSUFFICIENT_DATA."""
        data = _base_mock_result("NO_CMP")
        data["technicals"]["cmp"] = {"value": None, "status": "UNAVAILABLE"}
        rec = evaluate_investment_assessment(data)

        self.assertEqual(rec["investment_action"], "INSUFFICIENT_DATA")
        self.assertIn("RULE1_CRITICAL_PRICE_DATA_MISSING", rec["reason_codes"])

    def test_rule1_insufficient_data_missing_profitability(self):
        """Rule 1: Both ROE and ROCE missing triggers INSUFFICIENT_DATA."""
        data = _base_mock_result("NO_PROFIT")
        data["fundamentals"]["roe"] = {"value": None, "status": "UNAVAILABLE"}
        data["fundamentals"]["roce"] = {"value": None, "status": "UNAVAILABLE"}
        rec = evaluate_investment_assessment(data)

        self.assertEqual(rec["investment_action"], "INSUFFICIENT_DATA")
        self.assertIn("RULE1_PROFITABILITY_METRICS_UNAVAILABLE", rec["reason_codes"])

    def test_rule2_reduce_sell_on_severe_pledge(self):
        """Rule 2: Promoter pledge > 25% triggers REDUCE_SELL_REVIEW regardless of technicals."""
        data = _base_mock_result("HIGH_PLEDGE")
        data["institutional"]["promoter_pledge_pct"] = {"value": 45.0, "status": "VERIFIED"}
        rec = evaluate_investment_assessment(data)

        self.assertEqual(rec["investment_action"], "REDUCE_SELL_REVIEW")
        self.assertIn("RULE2_CRITICAL_PROMOTER_PLEDGE", rec["reason_codes"])

    def test_rule2_reduce_sell_on_technical_breakdown(self):
        """Rule 2: Technical breakdown triggers REDUCE_SELL_REVIEW."""
        data = _base_mock_result("BREAKDOWN")
        # Simulate breakdown: CMP below 200 DMA (90.0) + negative OBV
        data["technicals"]["cmp"]["value"] = 80.0
        data["technicals"]["obv_change_norm_14d"]["value"] = -0.35
        rec = evaluate_investment_assessment(data)

        self.assertEqual(rec["technical_classification"], "REDUCE_SELL_CANDIDATE")
        self.assertEqual(rec["investment_action"], "REDUCE_SELL_REVIEW")
        self.assertIn("RULE2_TECHNICAL_BREAKDOWN", rec["reason_codes"])

    def test_rule3_avoid_new_entry_extreme_pe(self):
        """Rule 3: Extreme P/E ratio (> 65.0) without super-growth triggers AVOID_NEW_ENTRY."""
        data = _base_mock_result("EXPENSIVE")
        data["fundamentals"]["pe_ratio"] = {"value": 95.0, "status": "VERIFIED"}
        data["fundamentals"]["sales_growth_3years_cagr"] = {"value": 8.0, "status": "VERIFIED"}
        rec = evaluate_investment_assessment(data)

        self.assertEqual(rec["investment_action"], "AVOID_NEW_ENTRY")
        self.assertIn("RULE3_EXTREME_PE_VALUATION", rec["reason_codes"])

    def test_technical_buy_degrades_when_fundamentals_weak(self):
        """Guardrail: Technical BUY degraded to HOLD_REVIEW when ROE/ROCE fails threshold."""
        data = _base_mock_result("LOW_ROE")
        # Technicals are BUY_CANDIDATE, but ROE is 6% and ROCE is 7%
        data["fundamentals"]["roe"] = {"value": 6.0, "status": "VERIFIED"}
        data["fundamentals"]["roce"] = {"value": 7.0, "status": "VERIFIED"}
        rec = evaluate_investment_assessment(data)

        self.assertEqual(rec["technical_classification"], "BUY_CANDIDATE")
        self.assertEqual(rec["investment_action"], "HOLD_REVIEW")
        self.assertIn("BUY_CRITERIA_UNMET_DEGRADED_TO_HOLD", rec["reason_codes"])

    def test_bank_nbfc_debt_guard(self):
        """Sector Guard: Bank/NBFC not penalized for high/missing Debt-to-Equity."""
        data = _base_mock_result("HDFCBANK")
        data["company_name"] = "HDFC Bank Limited"
        # Bank has no standard debt-to-equity or high leverage
        data["fundamentals"]["debt_to_equity"] = {"value": 7.5, "status": "VERIFIED"}
        rec = evaluate_investment_assessment(data)

        self.assertIn("LEVERAGE_NOT_APPLICABLE_FINANCIAL", rec["reason_codes"])
        # With other criteria passing, HDFC Bank remains eligible for BUY_CANDIDATE
        self.assertEqual(rec["investment_action"], "BUY_CANDIDATE")

    def test_debt_free_company(self):
        """Debt-Free Guard: D/E = 0.0 recognized as positive debt-free status."""
        data = _base_mock_result("INFY")
        data["fundamentals"]["debt_to_equity"] = {"value": 0.0, "status": "VERIFIED"}
        rec = evaluate_investment_assessment(data)

        self.assertIn("COMPANY_DEBT_FREE", rec["reason_codes"])
        self.assertTrue(any("debt-free" in factor.lower() for factor in rec["positive_factors"]))

    def test_stale_and_conflicting_data_representation(self):
        """Stale and conflicting data must be flagged in limitations and cautionary factors."""
        data = _base_mock_result("STALE_CO")
        data["fundamentals"]["roe"] = {"value": 18.0, "status": "STALE"}
        data["fundamentals"]["pe_ratio"] = {"value": 22.0, "status": "CONFLICTING"}
        rec = evaluate_investment_assessment(data)

        # Confirm tracked in limitations
        self.assertTrue(any("STALE" in lim for lim in rec["limitations"]))
        self.assertTrue(any("conflict" in lim.lower() for lim in rec["limitations"]))

    def test_custom_configurable_thresholds(self):
        """Configurable thresholds alter the assessment boundary properly."""
        data = _base_mock_result("CUSTOM_PE")
        data["fundamentals"]["pe_ratio"] = {"value": 35.0, "status": "VERIFIED"}

        # Stricter P/E max buy threshold of 30.0
        strict_thresholds = InvestmentThresholds(pe_max_buy=30.0)
        rec = evaluate_investment_assessment(data, thresholds=strict_thresholds)

        # Degrades from BUY to HOLD because PE of 35 exceeds strict 30 threshold
        self.assertEqual(rec["investment_action"], "HOLD_REVIEW")
        self.assertIn("BUY_CRITERIA_UNMET_DEGRADED_TO_HOLD", rec["reason_codes"])

    def test_canonical_field_names_supported(self):
        """Canonical ResearchResult v1 fields (sales_growth_3y_cagr, profit_growth_3y_cagr, promoter_pledge_pct) are supported."""
        data = _base_mock_result("CANONICAL")
        rec = evaluate_investment_assessment(data)
        self.assertEqual(rec["investment_action"], "BUY_CANDIDATE")
        # Ensure no bogus limitations for available canonical growth metrics
        self.assertFalse(any("3y Sales CAGR is unavailable" in lim for lim in rec["limitations"]))
        self.assertFalse(any("3y Profit CAGR is unavailable" in lim for lim in rec["limitations"]))

    def test_fallback_field_names_supported(self):
        """Legacy fallback fields (sales_growth_3years_cagr, profit_growth_3years_cagr, promoter_pledge) are supported."""
        data = _base_mock_result("FALLBACK")
        # Swap canonical keys for legacy keys
        data["fundamentals"]["sales_growth_3years_cagr"] = data["fundamentals"].pop("sales_growth_3y_cagr")
        data["fundamentals"]["profit_growth_3years_cagr"] = data["fundamentals"].pop("profit_growth_3y_cagr")
        data["institutional"]["promoter_pledge"] = data["institutional"].pop("promoter_pledge_pct")

        rec = evaluate_investment_assessment(data)
        self.assertEqual(rec["investment_action"], "BUY_CANDIDATE")
        self.assertFalse(any("3y Sales CAGR is unavailable" in lim for lim in rec["limitations"]))

    def test_growth_strictly_positive(self):
        """Strictly positive growth (> 0) satisfies BUY_CANDIDATE growth criteria."""
        data = _base_mock_result("POS_GROWTH")
        data["fundamentals"]["sales_growth_3y_cagr"]["value"] = 0.1
        data["fundamentals"]["profit_growth_3y_cagr"]["value"] = 0.5
        rec = evaluate_investment_assessment(data)
        self.assertEqual(rec["investment_action"], "BUY_CANDIDATE")

    def test_growth_zero_degrades_buy(self):
        """Zero growth (0.0%) fails strictly positive growth check (> 0.0) and degrades BUY to HOLD_REVIEW."""
        data = _base_mock_result("ZERO_GROWTH")
        data["fundamentals"]["sales_growth_3y_cagr"]["value"] = 0.0
        data["fundamentals"]["profit_growth_3y_cagr"]["value"] = 0.0
        rec = evaluate_investment_assessment(data)
        self.assertEqual(rec["investment_action"], "HOLD_REVIEW")
        self.assertIn("BUY_CRITERIA_UNMET_DEGRADED_TO_HOLD", rec["reason_codes"])

    def test_growth_negative_degrades_buy(self):
        """Negative growth fails growth criteria, is flagged in cautionary factors, and degrades to HOLD_REVIEW."""
        data = _base_mock_result("NEG_GROWTH")
        data["fundamentals"]["sales_growth_3y_cagr"]["value"] = -2.5
        data["fundamentals"]["profit_growth_3y_cagr"]["value"] = -4.0
        rec = evaluate_investment_assessment(data)
        self.assertEqual(rec["investment_action"], "HOLD_REVIEW")
        self.assertIn("BUY_CRITERIA_UNMET_DEGRADED_TO_HOLD", rec["reason_codes"])
        self.assertTrue(any("Negative 3-year profit CAGR" in f for f in rec["cautionary_factors"]))

    def test_growth_unavailable_degrades_buy(self):
        """Unavailable growth metrics fail growth criteria, are recorded in limitations, and degrade to HOLD_REVIEW."""
        data = _base_mock_result("UNAVAIL_GROWTH")
        data["fundamentals"]["sales_growth_3y_cagr"]["status"] = "UNAVAILABLE"
        data["fundamentals"]["sales_growth_3y_cagr"]["value"] = None
        data["fundamentals"]["profit_growth_3y_cagr"]["status"] = "UNAVAILABLE"
        data["fundamentals"]["profit_growth_3y_cagr"]["value"] = None
        rec = evaluate_investment_assessment(data)
        self.assertEqual(rec["investment_action"], "HOLD_REVIEW")
        self.assertTrue(any("3y Sales CAGR is unavailable" in lim for lim in rec["limitations"]))

    def test_growth_stale_degrades_buy(self):
        """Stale growth metrics are not treated as verified and degrade BUY to HOLD_REVIEW."""
        data = _base_mock_result("STALE_GROWTH")
        data["fundamentals"]["sales_growth_3y_cagr"]["status"] = "STALE"
        data["fundamentals"]["profit_growth_3y_cagr"]["status"] = "STALE"
        rec = evaluate_investment_assessment(data)
        self.assertEqual(rec["investment_action"], "HOLD_REVIEW")
        self.assertTrue(any("STALE" in lim for lim in rec["limitations"]))

    def test_growth_conflicting_degrades_buy(self):
        """Conflicting growth metrics are not treated as verified and degrade BUY to HOLD_REVIEW."""
        data = _base_mock_result("CONFLICT_GROWTH")
        data["fundamentals"]["sales_growth_3y_cagr"]["status"] = "CONFLICTING"
        data["fundamentals"]["profit_growth_3y_cagr"]["status"] = "CONFLICTING"
        rec = evaluate_investment_assessment(data)
        self.assertEqual(rec["investment_action"], "HOLD_REVIEW")
        self.assertTrue(any("conflict" in lim.lower() for lim in rec["limitations"]))

    def test_technical_confidence_type_is_string(self):
        """Technical confidence is a string (HIGH, MEDIUM, LOW) conforming to technical engine output."""
        data = _base_mock_result("TCS")
        rec = evaluate_investment_assessment(data)
        self.assertIsInstance(rec["technical_confidence"], str)
        self.assertIn(rec["technical_confidence"], {"HIGH", "MEDIUM", "LOW"})
        # Investment confidence remains numeric (0.0 to 1.0)
        self.assertIsInstance(rec["investment_confidence"], float)
        self.assertGreaterEqual(rec["investment_confidence"], 0.0)
        self.assertLessEqual(rec["investment_confidence"], 1.0)


    # --------------------------------------------------------------------------
    # Key Metrics Table Tests
    # --------------------------------------------------------------------------

    def test_build_key_metrics_complete_data(self):
        """build_key_metrics produces 16 formatted metrics with accurate statuses and dates."""
        data = _base_mock_result("TCS")
        data["technicals"]["volume"] = {
            "value": 1000000.0,
            "unit": "SHARES",
            "status": "VERIFIED",
            "provenance": {"as_of_date": "2026-10-10"},
        }
        data["technicals"]["avg_volume_20"] = {
            "value": 500000.0,
            "unit": "SHARES",
            "status": "VERIFIED",
            "provenance": {"as_of_date": "2026-10-10"},
        }
        data["technicals"]["volume_vs_20d_pct"] = {
            "value": 100.0,
            "unit": "PERCENT",
            "status": "DERIVED",
            "provenance": {"as_of_date": "2026-10-10"},
        }
        data["technicals"]["obv_change_norm_14d"] = {
            "value": 0.15,
            "unit": "RATIO",
            "status": "DERIVED",
            "provenance": {"as_of_date": "2026-10-10"},
        }

        rec = evaluate_investment_assessment(data)
        self.assertIn("key_metrics", rec)
        km = rec["key_metrics"]
        self.assertEqual(len(km), 16)

        km_dict = {item["metric"]: item for item in km}
        self.assertEqual(km_dict["CMP"]["value"], "₹104.00")
        self.assertEqual(km_dict["CMP"]["status"], "VERIFIED")
        self.assertEqual(km_dict["P/E"]["value"], "28.00x")
        self.assertEqual(km_dict["ROCE"]["value"], "30.0%")
        self.assertEqual(km_dict["ROE"]["value"], "25.0%")
        self.assertEqual(km_dict["3Y Sales Growth"]["value"], "12.0%")
        self.assertEqual(km_dict["3Y Profit Growth"]["value"], "15.0%")
        self.assertEqual(km_dict["50 DMA"]["value"], "₹100.00")
        self.assertEqual(km_dict["200 DMA"]["value"], "₹90.00")
        self.assertEqual(km_dict["RSI (14)"]["value"], "58.0")
        self.assertEqual(km_dict["Debt-to-Equity"]["value"], "0.10")
        self.assertEqual(km_dict["PEG"]["value"], "1.87")
        self.assertEqual(km_dict["PEG"]["status"], "DERIVED")
        self.assertEqual(km_dict["Trading Volume (Latest)"]["value"], "1,000,000")
        self.assertEqual(km_dict["20-Day Avg Volume"]["value"], "500,000")
        self.assertEqual(km_dict["Relative Volume"]["value"], "2.00x (+100.0%)")
        self.assertEqual(km_dict["Relative Volume"]["status"], "DERIVED")
        self.assertEqual(km_dict["OBV Trend (14d)"]["value"], "Positive (+0.15)")
        self.assertEqual(km_dict["OBV Trend (14d)"]["status"], "DERIVED")

    def test_build_key_metrics_peg_unavailable_when_profit_growth_negative_or_missing(self):
        """PEG remains UNAVAILABLE when profit growth is negative or missing."""
        data = _base_mock_result("TEST")
        data["fundamentals"]["profit_growth_3y_cagr"]["value"] = -5.0
        rec = evaluate_investment_assessment(data)
        km_dict = {item["metric"]: item for item in rec["key_metrics"]}
        self.assertEqual(km_dict["PEG"]["value"], "UNAVAILABLE")
        self.assertEqual(km_dict["PEG"]["status"], "UNAVAILABLE")
        self.assertEqual(km_dict["PEG"]["as_of_date"], "—")

    def test_build_key_metrics_bank_nbfc_debt_to_equity_na(self):
        """Financial institutions display Debt-to-Equity as N/A with status N/A."""
        data = _base_mock_result("HDFCBANK")
        data["company_name"] = "HDFC Bank Ltd"
        data["fundamentals"]["sector"] = "Financial Services"
        data["fundamentals"]["industry"] = "Private Sector Bank"

        rec = evaluate_investment_assessment(data)
        km_dict = {item["metric"]: item for item in rec["key_metrics"]}
        self.assertEqual(km_dict["Debt-to-Equity"]["value"], "N/A")
        self.assertEqual(km_dict["Debt-to-Equity"]["status"], "N/A")
        self.assertEqual(km_dict["Debt-to-Equity"]["as_of_date"], "—")

    def test_build_key_metrics_missing_data_never_zero(self):
        """Missing metrics are explicitly UNAVAILABLE and never converted to zero."""
        data = _base_mock_result("MISSING_DATA")
        data["fundamentals"]["pe_ratio"] = {"value": None, "status": "UNAVAILABLE"}
        data["fundamentals"]["debt_to_equity"] = {"value": None, "status": "UNAVAILABLE"}
        data["technicals"]["rsi_14"] = {"value": None, "status": "UNAVAILABLE"}
        data["institutional"]["promoter_pledge_pct"] = {"value": None, "status": "UNAVAILABLE"}

        rec = evaluate_investment_assessment(data)
        km_dict = {item["metric"]: item for item in rec["key_metrics"]}
        self.assertEqual(km_dict["P/E"]["value"], "UNAVAILABLE")
        self.assertEqual(km_dict["P/E"]["status"], "UNAVAILABLE")
        self.assertNotEqual(km_dict["P/E"]["value"], "0.00x")
        self.assertEqual(km_dict["Debt-to-Equity"]["value"], "UNAVAILABLE")
        self.assertEqual(km_dict["RSI (14)"]["value"], "UNAVAILABLE")
        self.assertEqual(km_dict["Promoter Pledge"]["value"], "UNAVAILABLE")

    def test_build_key_metrics_zero_average_volume_guard(self):
        """Zero or missing average volume guards against division-by-zero in Relative Volume."""
        data = _base_mock_result("ZERO_VOL")
        data["technicals"]["volume"] = {"value": 100000.0, "status": "VERIFIED"}
        data["technicals"]["avg_volume_20"] = {"value": 0.0, "status": "VERIFIED"}

        rec = evaluate_investment_assessment(data)
        km_dict = {item["metric"]: item for item in rec["key_metrics"]}
        self.assertEqual(km_dict["Relative Volume"]["value"], "UNAVAILABLE")
        self.assertEqual(km_dict["Relative Volume"]["status"], "UNAVAILABLE")

    def test_build_key_metrics_stale_and_conflicting_preserved(self):
        """Stale and Conflicting statuses are faithfully preserved in key_metrics."""
        data = _base_mock_result("STALE_CONF")
        data["fundamentals"]["pe_ratio"] = {
            "value": 24.5,
            "status": "STALE",
            "provenance": {"as_of_date": "2024-03-31"},
        }
        data["fundamentals"]["roe"] = {
            "value": None,
            "status": "CONFLICTING",
            "provenance": {"as_of_date": "2026-03-31"},
        }

        rec = evaluate_investment_assessment(data)
        km_dict = {item["metric"]: item for item in rec["key_metrics"]}
        self.assertEqual(km_dict["P/E"]["value"], "24.50x")
        self.assertEqual(km_dict["P/E"]["status"], "STALE")
        self.assertEqual(km_dict["P/E"]["as_of_date"], "2024-03-31")
        self.assertEqual(km_dict["ROE"]["value"], "UNAVAILABLE")
        self.assertEqual(km_dict["ROE"]["status"], "CONFLICTING")

    def test_build_key_metrics_obv_trend_categories(self):
        """OBV trend categories: Positive, Neutral, Negative, and Missing."""
        data = _base_mock_result("OBV_TEST")

        # Positive
        data["technicals"]["obv_change_norm_14d"] = {"value": 0.22, "status": "DERIVED", "provenance": {"as_of_date": "2026-10-10"}}
        rec_pos = evaluate_investment_assessment(data)
        km_pos = {item["metric"]: item for item in rec_pos["key_metrics"]}
        self.assertEqual(km_pos["OBV Trend (14d)"]["value"], "Positive (+0.22)")

        # Neutral
        data["technicals"]["obv_change_norm_14d"]["value"] = -0.05
        rec_neu = evaluate_investment_assessment(data)
        km_neu = {item["metric"]: item for item in rec_neu["key_metrics"]}
        self.assertEqual(km_neu["OBV Trend (14d)"]["value"], "Neutral (-0.05)")

        # Negative
        data["technicals"]["obv_change_norm_14d"]["value"] = -0.28
        rec_neg = evaluate_investment_assessment(data)
        km_neg = {item["metric"]: item for item in rec_neg["key_metrics"]}
        self.assertEqual(km_neg["OBV Trend (14d)"]["value"], "Negative (-0.28)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
