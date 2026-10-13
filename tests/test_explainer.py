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


if __name__ == "__main__":
    unittest.main(verbosity=2)
