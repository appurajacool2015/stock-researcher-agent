#!/usr/bin/env python3
"""
Unit tests for intelligence/explainer.py

Verifies:
1. Deterministic template outputs all 8 required Markdown sections.
2. Unavailable metrics and levels are formatted explicitly as UNAVAILABLE.
3. Key levels and timestamps are rendered correctly.
4. Capital-loss and non-guarantee disclaimer is included.
5. Missing Gemini API key falls back smoothly to deterministic template.
6. Gemini API failure or invariant corruption falls back smoothly to template.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from intelligence.explainer import (
    DISCLAIMER_TEXT,
    explain_assessment,
    format_deterministic_template,
    format_with_gemini,
)


def _sample_recommendation() -> dict:
    return {
        "id": "rec-1111-2222-3333",
        "symbol": "TCS",
        "company_name": "Tata Consultancy Services Ltd",
        "cmp": 3500.0,
        "currency": "INR",
        "technical_classification": "BUY_CANDIDATE",
        "investment_action": "BUY_CANDIDATE",
        "positive_factors": [
            "Robust ROE of 48.2% exceeds 15.0%.",
            "Reasonable valuation at P/E 28.5x.",
            "Price above rising 50-DMA.",
        ],
        "cautionary_factors": [
            "Quarterly revenue growth slowed.",
        ],
        "risk_flags": [],
        "limitations": [
            "3-year profit CAGR is unavailable.",
        ],
        "key_levels": {
            "support_reference": {"price": 3400.0, "level_type": "50-DMA"},
            "resistance_reference": {"price": 3650.0, "level_type": "52-Week High"},
        },
        "assessment_timestamp": "2026-10-11T12:00:00Z",
        "market_data_as_of": "2026-10-10",
        "is_cached": False,
    }


class TestExplainer(unittest.TestCase):

    def test_deterministic_template_eight_sections(self):
        """Deterministic template produces all 8 required sections."""
        rec = _sample_recommendation()
        output = format_deterministic_template(rec)

        self.assertIn("**Symbol and price:**", output)
        self.assertIn("**Technical classification:** BUY_CANDIDATE", output)
        self.assertIn("**Investment assessment:** BUY_CANDIDATE", output)
        self.assertIn("**Rationale:**", output)
        self.assertIn("1. *Business Quality:*", output)
        self.assertIn("2. *Valuation:*", output)
        self.assertIn("3. *Technical Trend & Volume:*", output)
        self.assertIn("**Risk and missing data:**", output)
        self.assertIn("**Key levels:**", output)
        self.assertIn("**Timestamps:**", output)
        self.assertIn("**History:**", output)
        self.assertIn("Recommendation ID: `rec-1111-2222-3333`", output)
        self.assertIn(DISCLAIMER_TEXT, output)

    def test_unavailable_values_explicitly_labeled(self):
        """Missing price and key levels are represented as UNAVAILABLE."""
        rec = _sample_recommendation()
        rec["cmp"] = None
        rec["key_levels"] = {
            "support_reference": None,
            "resistance_reference": None,
        }
        output = format_deterministic_template(rec)

        self.assertIn("CMP: UNAVAILABLE", output)
        self.assertIn("Support Reference: UNAVAILABLE", output)
        self.assertIn("Resistance Reference: UNAVAILABLE", output)

    def test_cached_result_labeled_in_timestamps(self):
        """Cached recommendations are explicitly labeled in timestamps section."""
        rec = _sample_recommendation()
        rec["is_cached"] = True
        output = format_deterministic_template(rec)

        self.assertIn("Cache Status: CACHED (< 6h Snapshot)", output)

    def test_gemini_fallback_when_key_missing(self):
        """When no Gemini key is provided, falls back smoothly to deterministic template."""
        rec = _sample_recommendation()
        with patch.dict("os.environ", {}, clear=True):
            output = explain_assessment(rec, use_gemini=True, gemini_key=None)
            self.assertIn("**Symbol and price:**", output)
            self.assertIn("BUY_CANDIDATE", output)

    @patch("intelligence.explainer.requests.post")
    def test_gemini_fallback_on_network_error(self, mock_post):
        """Network error during Gemini call falls back to deterministic template."""
        rec = _sample_recommendation()
        mock_post.side_effect = TimeoutError("Gemini timed out")

        output = explain_assessment(rec, use_gemini=True, gemini_key="mock-key")
        self.assertIn("**Symbol and price:**", output)
        self.assertIn("BUY_CANDIDATE", output)

    @patch("intelligence.explainer.requests.post")
    def test_gemini_fallback_on_invariant_tampering(self, mock_post):
        """If Gemini drops the exact classification, explainer rejects output and falls back."""
        rec = _sample_recommendation()
        # Mock Gemini response that hallucinated and altered classification to 'STRONG_BUY'
        hallucinated_resp = MagicMock(status_code=200)
        hallucinated_resp.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Altered text without required classification tokens"}]
                }
            }]
        }
        mock_post.return_value = hallucinated_resp

        output = explain_assessment(rec, use_gemini=True, gemini_key="mock-key")
        # Should reject hallucinated text and produce deterministic template
        self.assertIn("**Technical classification:** BUY_CANDIDATE", output)

    # --------------------------------------------------------------------------
    # Track Record Report Integration Tests (Phase 2C)
    # --------------------------------------------------------------------------

    def test_explainer_with_historical_track_record(self):
        """Renders complete track record with positive return, duration, and disclaimers."""
        rec = _sample_recommendation()
        track_record = {
            "symbol": "TCS",
            "status": "TRACK_RECORD_AVAILABLE",
            "has_prior_history": True,
            "first_researched_at": "2026-10-01T10:00:00Z",
            "first_researched_date_str": "01 Oct 2026",
            "first_researched_price": 3500.0,
            "latest_price": 3800.0,
            "price_change": 300.0,
            "price_return_pct": 8.57,
            "price_return_note": None,
            "duration_str": "14 days ago (01 Oct 2026)",
            "verdict_transition": "BUY_CANDIDATE (Unchanged)",
            "verdict_note": "Investment thesis remains consistent (BUY_CANDIDATE).",
        }

        output = format_deterministic_template(rec, track_record=track_record)

        self.assertIn("**History:**", output)
        self.assertIn("Research Baseline: First researched 14 days ago (01 Oct 2026) at ₹3,500.00 INR", output)
        self.assertIn("Price Return (Research Baseline): +₹300.00 (+8.57% 🟢)", output)
        self.assertIn("Verdict Tracking: BUY_CANDIDATE (Unchanged)", output)
        self.assertIn("Thesis Continuity: Investment thesis remains consistent", output)
        self.assertIn("Performance Basis: Price return on research baseline; excludes dividends", output)
        self.assertIn("Notice: Prior price movement does not guarantee future results", output)
        self.assertIn("Recommendation ID: `rec-1111-2222-3333`", output)

    def test_explainer_with_first_time_baseline_established(self):
        """Renders baseline established notice when stock is researched for the first time."""
        rec = _sample_recommendation()
        track_record = {
            "symbol": "TCS",
            "status": "BASELINE_ESTABLISHED",
            "has_prior_history": False,
            "duration_str": "today",
            "initial_verdict": "BUY_CANDIDATE",
        }

        output = format_deterministic_template(rec, track_record=track_record)

        self.assertIn("**History:**", output)
        self.assertIn("Research Baseline: Initial baseline established today at ₹3,500.00 INR", output)
        self.assertIn("Initial Verdict: BUY_CANDIDATE", output)
        self.assertIn("Historical price return will be computed on subsequent research checks", output)
        self.assertIn("Recommendation ID: `rec-1111-2222-3333`", output)

    def test_explainer_with_missing_baseline_price(self):
        """Displays informative note when historical price was missing/invalid."""
        rec = _sample_recommendation()
        track_record = {
            "symbol": "TCS",
            "status": "TRACK_RECORD_AVAILABLE",
            "has_prior_history": True,
            "first_researched_date_str": "01 Oct 2026",
            "first_researched_price": None,
            "price_change": None,
            "price_return_pct": None,
            "price_return_note": "Price return unavailable: baseline research price is missing or invalid.",
            "duration_str": "14 days ago (01 Oct 2026)",
            "verdict_transition": "BUY_CANDIDATE ➔ HOLD_REVIEW",
            "verdict_note": "Investment verdict changed from BUY_CANDIDATE to HOLD_REVIEW.",
        }

        output = format_deterministic_template(rec, track_record=track_record)

        self.assertIn("Research Baseline: First researched 14 days ago (01 Oct 2026) at UNAVAILABLE", output)
        self.assertIn("Price Return (Research Baseline): Price return unavailable: baseline research price is missing or invalid.", output)
        self.assertIn("Verdict Tracking: BUY_CANDIDATE ➔ HOLD_REVIEW", output)

    def test_explainer_with_unavailable_track_record(self):
        """Renders graceful notice when historical database lookup fails."""
        rec = _sample_recommendation()
        track_record = {
            "status": "UNAVAILABLE",
            "note": "Historical database lookup temporarily offline.",
        }

        output = format_deterministic_template(rec, track_record=track_record)

        self.assertIn("**History:**", output)
        self.assertIn("Historical Track Record: Historical database lookup temporarily offline.", output)
        self.assertIn("Recommendation ID: `rec-1111-2222-3333`", output)

    def test_explainer_passes_track_record_via_dict_property(self):
        """Verification that track_record attached as property inside rec dict is rendered correctly."""
        rec = _sample_recommendation()
        rec["track_record"] = {
            "status": "BASELINE_ESTABLISHED",
            "has_prior_history": False,
            "duration_str": "today",
            "initial_verdict": "BUY_CANDIDATE",
        }

        output = explain_assessment(rec, use_gemini=False)
        self.assertIn("Research Baseline: Initial baseline established today", output)

    # --------------------------------------------------------------------------
    # Key Metrics Presentation Table Tests
    # --------------------------------------------------------------------------

    def test_key_metrics_table_rendered_with_defaults(self):
        """When key_metrics is omitted, fallback table renders CMP and UNAVAILABLE defaults."""
        rec = _sample_recommendation()
        output = format_deterministic_template(rec)

        self.assertIn("**Key metrics:**", output)
        self.assertIn("| Metric | Value | Status | As-Of Date |", output)
        self.assertIn("| CMP | ₹3,500.00 | VERIFIED | 2026-10-10 |", output)
        self.assertIn("| PEG | UNAVAILABLE | UNAVAILABLE | — |", output)
        self.assertIn("| 50 DMA | UNAVAILABLE | UNAVAILABLE | — |", output)

    def test_key_metrics_table_with_complete_data(self):
        """Renders all 16 metrics faithfully with verified formats, statuses, and dates."""
        rec = _sample_recommendation()
        rec["key_metrics"] = [
            {"metric": "CMP", "value": "₹3,500.00", "status": "VERIFIED", "as_of_date": "2026-10-10"},
            {"metric": "P/E", "value": "28.50x", "status": "VERIFIED", "as_of_date": "2026-03-31"},
            {"metric": "ROCE", "value": "55.2%", "status": "VERIFIED", "as_of_date": "2026-03-31"},
            {"metric": "ROE", "value": "48.2%", "status": "VERIFIED", "as_of_date": "2026-03-31"},
            {"metric": "3Y Sales Growth", "value": "11.4%", "status": "VERIFIED", "as_of_date": "2026-03-31"},
            {"metric": "3Y Profit Growth", "value": "12.8%", "status": "VERIFIED", "as_of_date": "2026-03-31"},
            {"metric": "50 DMA", "value": "₹3,420.50", "status": "VERIFIED", "as_of_date": "2026-10-10"},
            {"metric": "200 DMA", "value": "₹3,210.00", "status": "VERIFIED", "as_of_date": "2026-10-10"},
            {"metric": "RSI (14)", "value": "58.4", "status": "VERIFIED", "as_of_date": "2026-10-10"},
            {"metric": "Debt-to-Equity", "value": "0.08", "status": "VERIFIED", "as_of_date": "2026-03-31"},
            {"metric": "Promoter Pledge", "value": "0.0%", "status": "VERIFIED", "as_of_date": "2026-06-30"},
            {"metric": "PEG", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
            {"metric": "Trading Volume (Latest)", "value": "2,450,100", "status": "VERIFIED", "as_of_date": "2026-10-10"},
            {"metric": "20-Day Avg Volume", "value": "1,850,000", "status": "VERIFIED", "as_of_date": "2026-10-10"},
            {"metric": "Relative Volume", "value": "1.32x (+32.4%)", "status": "DERIVED", "as_of_date": "2026-10-10"},
            {"metric": "OBV Trend (14d)", "value": "Positive (+0.25)", "status": "DERIVED", "as_of_date": "2026-10-10"},
        ]

        output = format_deterministic_template(rec)
        self.assertIn("| CMP | ₹3,500.00 | VERIFIED | 2026-10-10 |", output)
        self.assertIn("| P/E | 28.50x | VERIFIED | 2026-03-31 |", output)
        self.assertIn("| ROCE | 55.2% | VERIFIED | 2026-03-31 |", output)
        self.assertIn("| ROE | 48.2% | VERIFIED | 2026-03-31 |", output)
        self.assertIn("| 3Y Sales Growth | 11.4% | VERIFIED | 2026-03-31 |", output)
        self.assertIn("| 3Y Profit Growth | 12.8% | VERIFIED | 2026-03-31 |", output)
        self.assertIn("| 50 DMA | ₹3,420.50 | VERIFIED | 2026-10-10 |", output)
        self.assertIn("| 200 DMA | ₹3,210.00 | VERIFIED | 2026-10-10 |", output)
        self.assertIn("| RSI (14) | 58.4 | VERIFIED | 2026-10-10 |", output)
        self.assertIn("| Debt-to-Equity | 0.08 | VERIFIED | 2026-03-31 |", output)
        self.assertIn("| Promoter Pledge | 0.0% | VERIFIED | 2026-06-30 |", output)
        self.assertIn("| PEG | UNAVAILABLE | UNAVAILABLE | — |", output)
        self.assertIn("| Trading Volume (Latest) | 2,450,100 | VERIFIED | 2026-10-10 |", output)
        self.assertIn("| 20-Day Avg Volume | 1,850,000 | VERIFIED | 2026-10-10 |", output)
        self.assertIn("| Relative Volume | 1.32x (+32.4%) | DERIVED | 2026-10-10 |", output)
        self.assertIn("| OBV Trend (14d) | Positive (+0.25) | DERIVED | 2026-10-10 |", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
