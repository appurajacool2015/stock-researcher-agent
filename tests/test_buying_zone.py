#!/usr/bin/env python3
"""
Unit tests for intelligence/buying_zone.py

Verifies:
1. BUYING_ZONE label upon multi-pillar confluence (trend, location, momentum, risk/reward).
2. WAIT_FOR_PULLBACK label when overextended (high RSI, far above 50 DMA, near swing resistance).
3. WAIT_FOR_CONFIRMATION label on aggressive downward momentum / falling knife.
4. NOT_IN_BUYING_ZONE label on structural downtrend (below 200 DMA) or fundamental red flags.
5. INSUFFICIENT_DATA label on missing critical metrics or insufficient history bars.
6. Zero-division and edge-case resilience (zero volume, zero risk).
7. Integration with explainer format_deterministic_template.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict

from intelligence.buying_zone import (
    BuyingZoneThresholds,
    DEFAULT_THRESHOLDS,
    evaluate_buying_zone,
)
from intelligence.explainer import format_deterministic_template


def _make_mock_research(
    cmp: float = 2450.0,
    dma_50: float = 2420.0,
    dma_200: float = 2300.0,
    rsi_14: float = 52.0,
    atr_14: float = 35.0,
    swing_high: float = 2580.0,
    swing_low: float = 2350.0,
    volume: float = 1_500_000.0,
    avg_volume_20: float = 1_200_000.0,
    volume_vs_20d_pct: float = 25.0,
    obv_val: float = 0.05,
    history_bars: int = 250,
    roe: float = 25.0,
    roce: float = 30.0,
    pe_ratio: float = 28.0,
    debt_to_equity: float = 0.05,
    promoter_pledge: float = 0.0,
) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "symbol": "TCS",
        "company_name": "Tata Consultancy Services Ltd",
        "technicals": {
            "provenance": {"as_of_date": "2026-10-16"},
            "cmp": {"value": cmp, "status": "VERIFIED", "unit": "INR"},
            "dma_50": {"value": dma_50, "status": "VERIFIED", "unit": "INR"},
            "dma_200": {"value": dma_200, "status": "VERIFIED", "unit": "INR"},
            "rsi_14": {"value": rsi_14, "status": "VERIFIED"},
            "atr_14": {"value": atr_14, "status": "VERIFIED"},
            "swing_high_20": {"value": swing_high, "status": "VERIFIED"},
            "swing_low_20": {"value": swing_low, "status": "VERIFIED"},
            "volume": {"value": volume, "status": "VERIFIED"},
            "avg_volume_20": {"value": avg_volume_20, "status": "VERIFIED"},
            "volume_vs_20d_pct": {"value": volume_vs_20d_pct, "status": "VERIFIED"},
            "obv_change_norm_14d": {"value": obv_val, "status": "VERIFIED"},
            "history_bars": {"value": history_bars, "status": "VERIFIED"},
        },
        "fundamentals": {
            "provenance": {"as_of_date": "2026-06-30"},
            "roe": {"value": roe, "status": "VERIFIED"},
            "roce": {"value": roce, "status": "VERIFIED"},
            "pe_ratio": {"value": pe_ratio, "status": "VERIFIED"},
            "debt_to_equity": {"value": debt_to_equity, "status": "VERIFIED"},
        },
        "institutional": {
            "provenance": {"as_of_date": "2026-06-30"},
            "promoter_pledge_pct": {"value": promoter_pledge, "status": "VERIFIED"},
        },
    }


class TestBuyingZoneAssessment(unittest.TestCase):

    def test_buying_zone_ideal_confluence(self):
        """Stock with constructive trend, near 50-DMA, balanced RSI, and R:R >= 1.5 triggers BUYING_ZONE."""
        # CMP 2450, 50 DMA 2420 (dist = 1.2% <= 3.5%), 200 DMA 2300, RSI 52, Swing High 2580 (upside 5.3%), ATR 35 (downside 2.65%) -> R:R ~ 2.0:1
        data = _make_mock_research(
            cmp=2450.0,
            dma_50=2420.0,
            dma_200=2300.0,
            rsi_14=52.0,
            atr_14=35.0,
            swing_high=2580.0,
        )
        res = evaluate_buying_zone(data)

        self.assertEqual(res["status"], "BUYING_ZONE")
        self.assertEqual(res["label"], "BUYING ZONE")
        self.assertGreaterEqual(res["reward_to_risk_ratio"], 1.50)
        self.assertEqual(res["support_type"], "50-Day Moving Average")
        self.assertGreater(len(res["supporting_signals"]), 0)
        self.assertEqual(len(res["conflicting_signals"]), 0)

    def test_wait_for_pullback_rsi_overbought(self):
        """Stock in strong uptrend but with RSI > 65 triggers WAIT_FOR_PULLBACK."""
        data = _make_mock_research(
            cmp=2550.0,
            dma_50=2400.0,
            rsi_14=72.0,  # Overbought
        )
        res = evaluate_buying_zone(data)

        self.assertEqual(res["status"], "WAIT_FOR_PULLBACK")
        self.assertEqual(res["label"], "WAIT FOR PULLBACK")
        self.assertTrue(any("overextended" in s.lower() for s in res["conflicting_signals"]))

    def test_wait_for_pullback_at_swing_resistance(self):
        """Stock trading within 1.5% of verified 20D swing high triggers WAIT_FOR_PULLBACK."""
        data = _make_mock_research(
            cmp=2575.0,
            swing_high=2580.0,  # within 0.2%
            rsi_14=58.0,
        )
        res = evaluate_buying_zone(data)

        self.assertEqual(res["status"], "WAIT_FOR_PULLBACK")
        self.assertTrue(any("resistance" in s.lower() for s in res["conflicting_signals"]))

    def test_wait_for_pullback_extended_above_50_dma(self):
        """Stock extended > 8% above its 50 DMA triggers WAIT_FOR_PULLBACK."""
        data = _make_mock_research(
            cmp=2650.0,
            dma_50=2400.0,  # +10.4% above 50 DMA
            rsi_14=60.0,
            swing_high=2750.0,
        )
        res = evaluate_buying_zone(data)

        self.assertEqual(res["status"], "WAIT_FOR_PULLBACK")
        self.assertTrue(any("extended" in s.lower() for s in res["conflicting_signals"]))

    def test_wait_for_confirmation_falling_knife_rsi(self):
        """Stock testing support but with RSI < 38 triggers WAIT_FOR_CONFIRMATION."""
        data = _make_mock_research(
            cmp=2420.0,
            dma_50=2420.0,
            rsi_14=32.0,  # Falling knife
        )
        res = evaluate_buying_zone(data)

        self.assertEqual(res["status"], "WAIT_FOR_CONFIRMATION")
        self.assertEqual(res["label"], "WAIT FOR CONFIRMATION")
        self.assertTrue(any("steep" in s.lower() for s in res["conflicting_signals"]))

    def test_wait_for_confirmation_heavy_obv_distribution(self):
        """Stock testing support but with normalized OBV change < -0.15 triggers WAIT_FOR_CONFIRMATION."""
        data = _make_mock_research(
            cmp=2420.0,
            dma_50=2420.0,
            rsi_14=45.0,
            obv_val=-0.22,  # Heavy distribution
        )
        res = evaluate_buying_zone(data)

        self.assertEqual(res["status"], "WAIT_FOR_CONFIRMATION")
        self.assertTrue(any("distribution" in s.lower() for s in res["conflicting_signals"]))

    def test_not_in_buying_zone_structural_downtrend(self):
        """Stock trading below 200 DMA triggers NOT_IN_BUYING_ZONE."""
        data = _make_mock_research(
            cmp=2150.0,
            dma_50=2200.0,
            dma_200=2300.0,  # CMP well below 200 DMA
        )
        res = evaluate_buying_zone(data)

        self.assertEqual(res["status"], "NOT_IN_BUYING_ZONE")
        self.assertEqual(res["label"], "NOT IN BUYING ZONE")
        self.assertTrue(any("downtrend" in s.lower() for s in res["conflicting_signals"]))

    def test_not_in_buying_zone_extreme_pe(self):
        """Stock with extreme P/E (> 65.0) triggers NOT_IN_BUYING_ZONE."""
        data = _make_mock_research(
            pe_ratio=75.0,  # Extreme valuation
        )
        res = evaluate_buying_zone(data)

        self.assertEqual(res["status"], "NOT_IN_BUYING_ZONE")
        self.assertTrue(any("valuation" in s.lower() for s in res["conflicting_signals"]))

    def test_not_in_buying_zone_severe_pledge(self):
        """Stock with promoter pledge > 25% triggers NOT_IN_BUYING_ZONE."""
        data = _make_mock_research(
            promoter_pledge=32.0,  # Severe encumbrance
        )
        res = evaluate_buying_zone(data)

        self.assertEqual(res["status"], "NOT_IN_BUYING_ZONE")
        self.assertTrue(any("pledge" in s.lower() for s in res["conflicting_signals"]))

    def test_insufficient_data_missing_cmp(self):
        """Missing CMP triggers INSUFFICIENT_DATA."""
        data = _make_mock_research()
        data["technicals"]["cmp"]["value"] = None
        data["technicals"]["cmp"]["status"] = "UNAVAILABLE"

        res = evaluate_buying_zone(data)
        self.assertEqual(res["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(res["reward_to_risk_ratio"])

    def test_insufficient_data_history_bars_too_low(self):
        """History bars < 50 triggers INSUFFICIENT_DATA."""
        data = _make_mock_research(history_bars=30)
        res = evaluate_buying_zone(data)

        self.assertEqual(res["status"], "INSUFFICIENT_DATA")
        self.assertTrue(any("History bars" in s for s in res["conflicting_signals"]))

    def test_zero_volume_resilience(self):
        """Zero volume or missing volume does not raise ZeroDivisionError."""
        data = _make_mock_research(avg_volume_20=0.0, volume=0.0)
        res = evaluate_buying_zone(data)
        # Should execute safely
        self.assertIn(res["status"], {"BUYING_ZONE", "WAIT_FOR_PULLBACK", "WAIT_FOR_CONFIRMATION", "NOT_IN_BUYING_ZONE", "INSUFFICIENT_DATA"})

    def test_explainer_integration_renders_buying_zone_block(self):
        """Explainer format_deterministic_template includes the Buying zone assessment block."""
        data = _make_mock_research(
            cmp=2450.0,
            dma_50=2420.0,
            dma_200=2300.0,
            rsi_14=52.0,
            atr_14=35.0,
            swing_high=2580.0,
        )
        bz_res = evaluate_buying_zone(data)
        rec = {
            "symbol": "TCS",
            "company_name": "Tata Consultancy Services Ltd",
            "cmp": 2450.0,
            "currency": "INR",
            "technical_classification": "BUY_CANDIDATE",
            "investment_action": "BUY_CANDIDATE",
            "positive_factors": ["High ROE of 25.0% reflects strong business quality."],
            "cautionary_factors": [],
            "risk_flags": [],
            "limitations": [],
            "key_levels": {
                "support_reference": {"price": 2420.0, "level_type": "50_DMA"},
                "resistance_reference": {"price": 2580.0, "level_type": "SWING_HIGH"},
            },
            "assessment_timestamp": "2026-10-17T01:00:00Z",
            "market_data_as_of": "2026-10-16",
            "is_cached": False,
            "buying_zone": bz_res,
        }

        output = format_deterministic_template(rec)

        self.assertIn("**Buying zone assessment:**", output)
        self.assertIn("**BUYING ZONE**", output)
        self.assertIn("Risk/Reward Structure:", output)
        self.assertIn("Reward-to-Risk Ratio:", output)
        self.assertIn("Supporting signals:", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
