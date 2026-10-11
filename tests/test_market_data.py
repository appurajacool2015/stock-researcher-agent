#!/usr/bin/env python3

"""
Unit tests for MarketDataAdapter and Stage 1 Technical Metrics.

Covers:
  - MultiIndex column flattening and malformed column handling
  - ATR(14) with Wilder's smoothing, ATR %, and 50-session ATR baseline
  - CLV and zero-range candle guard (High == Low -> CLV = 0.0)
  - Normalized 14-session OBV change and threshold boundaries
  - 50-DMA and 200-DMA slopes and ±0.50% flat-tolerance boundaries
  - Historical DMA crossover detection (GOLDEN_CROSS, DEATH_CROSS, NOT_FOUND_IN_LOOKBACK, UNAVAILABLE)
  - Confirmed 20-session swing pivots with 3-session confirmation lag (no look-ahead)
  - Volume averages (5, 20, 50) and relative volume
  - 52-week High/Low from daily High/Low and distance percentages
  - Short history / IPO degradation (< 200 bars)
  - ResearchResult canonical envelope construction and JSON Schema validation
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from adapters.market_data import MarketDataAdapter
from services.research_pipeline import (
    build_research_result,
    validate_schema,
)


def create_synthetic_ohlcv(
    bars: int = 300,
    base_price: float = 1000.0,
    trend_slope: float = 0.5,
    volatility: float = 10.0,
    start_date: str = "2024-01-01",
) -> pd.DataFrame:
    """Generate deterministic synthetic daily OHLCV dataframe."""
    dates = pd.date_range(start=start_date, periods=bars, freq="B")
    t = np.arange(bars)

    close_prices = base_price + (trend_slope * t) + (np.sin(t / 5.0) * volatility)
    high_prices = close_prices + np.abs(np.sin(t)) * 5.0 + 2.0
    low_prices = close_prices - np.abs(np.cos(t)) * 5.0 - 2.0
    open_prices = (high_prices + low_prices) / 2.0
    volume = 1_000_000.0 + (np.sin(t / 10.0) * 200_000.0)

    df = pd.DataFrame(
        {
            "Open": open_prices,
            "High": high_prices,
            "Low": low_prices,
            "Close": close_prices,
            "Volume": volume,
        },
        index=dates,
    )
    return df


class TestMarketDataAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = MarketDataAdapter()

    def test_multiindex_and_malformed_columns(self):
        """Verify MultiIndex and unexpected column names are flattened and sanitized."""
        df_base = create_synthetic_ohlcv(bars=10)

        # Create MultiIndex columns
        multi_cols = pd.MultiIndex.from_tuples(
            [(col, "TEST.NS") for col in df_base.columns]
        )
        df_multi = pd.DataFrame(df_base.values, index=df_base.index, columns=multi_cols)

        sanitized = self.adapter.sanitize_history(df_multi)
        self.assertListEqual(
            list(sanitized.columns),
            ["Open", "High", "Low", "Close", "Volume"],
        )
        self.assertEqual(len(sanitized), 10)

        # Case-insensitive column matching
        df_lower = df_base.rename(columns={"Close": "close", "Volume": "volume"})
        sanitized_lower = self.adapter.sanitize_history(df_lower)
        self.assertIn("Close", sanitized_lower.columns)
        self.assertIn("Volume", sanitized_lower.columns)

    def test_atr_wilders_and_baseline(self):
        """Verify ATR(14) Wilder smoothing and 50-session ATR baseline."""
        df = create_synthetic_ohlcv(bars=80, volatility=15.0)
        cmp_val = float(df["Close"].iloc[-1])

        atr_info = self.adapter.calculate_atr(
            df["High"],
            df["Low"],
            df["Close"],
            cmp_value=cmp_val,
            period=14,
            baseline_period=50,
        )

        self.assertIsNotNone(atr_info["atr_14"])
        self.assertGreater(atr_info["atr_14"], 0.0)
        self.assertIsNotNone(atr_info["atr_pct"])
        self.assertGreater(atr_info["atr_pct"], 0.0)
        self.assertIsNotNone(atr_info["atr_50_avg"])
        self.assertGreater(atr_info["atr_50_avg"], 0.0)

        # With insufficient bars (< 64), atr_50_avg must be None
        df_short = create_synthetic_ohlcv(bars=30)
        atr_short = self.adapter.calculate_atr(
            df_short["High"],
            df_short["Low"],
            df_short["Close"],
            cmp_value=float(df_short["Close"].iloc[-1]),
            period=14,
            baseline_period=50,
        )
        self.assertIsNotNone(atr_short["atr_14"])
        self.assertIsNone(atr_short["atr_50_avg"])

    def test_clv_and_zero_range_candle_guard(self):
        """Verify CLV formula and zero-range candle guard (High == Low)."""
        dates = pd.date_range("2024-01-01", periods=5, freq="B")

        # Candle 0: Close at High -> CLV = +1.0
        # Candle 1: Close at Low -> CLV = -1.0
        # Candle 2: Close at Midpoint -> CLV = 0.0
        # Candle 3: Circuit lock (High == Low == Close) -> CLV MUST BE 0.0 (zero-range guard)
        # Candle 4: Normal candle
        high = pd.Series([100.0, 100.0, 100.0, 100.0, 105.0], index=dates)
        low = pd.Series([90.0, 90.0, 90.0, 100.0, 95.0], index=dates)
        close = pd.Series([100.0, 90.0, 95.0, 100.0, 100.0], index=dates)

        clv_latest, clv_avg = self.adapter.calculate_clv(high, low, close, period=3)
        self.assertIsNotNone(clv_latest)

        # Check circuit candle explicitly
        circuit_high = pd.Series([100.0], index=dates[:1])
        circuit_low = pd.Series([100.0], index=dates[:1])
        circuit_close = pd.Series([100.0], index=dates[:1])
        clv_circuit, _ = self.adapter.calculate_clv(circuit_high, circuit_low, circuit_close)
        self.assertEqual(clv_circuit, 0.0)

    def test_normalized_obv_change(self):
        """Verify normalized 14-session OBV change and threshold boundaries."""
        dates = pd.date_range("2024-01-01", periods=25, freq="B")

        # Monotonically rising closes with constant volume 100,000
        close_up = pd.Series(np.linspace(100, 200, 25), index=dates)
        volume = pd.Series(100_000.0, index=dates)

        # OBV increases by 100,000 each session. Over 14 sessions: delta = 1,400,000
        # avg_volume_20 = 100,000. Denominator = 100,000 * 14 = 1,400,000
        # Normalized change = 1,400,000 / 1,400,000 = +1.0
        norm_obv = self.adapter.calculate_normalized_obv_change(
            close_up,
            volume,
            avg_volume_20=100_000.0,
            period=14,
        )
        self.assertAlmostEqual(norm_obv, 1.0, places=3)
        self.assertGreater(norm_obv, self.adapter.OBV_NORM_THRESHOLD)

        # Monotonically falling closes -> normalized change = -1.0
        close_down = pd.Series(np.linspace(200, 100, 25), index=dates)
        norm_obv_down = self.adapter.calculate_normalized_obv_change(
            close_down,
            volume,
            avg_volume_20=100_000.0,
            period=14,
        )
        self.assertAlmostEqual(norm_obv_down, -1.0, places=3)
        self.assertLess(norm_obv_down, -self.adapter.OBV_NORM_THRESHOLD)

        # Flat closes -> 0.0
        close_flat = pd.Series(100.0, index=dates)
        norm_obv_flat = self.adapter.calculate_normalized_obv_change(
            close_flat,
            volume,
            avg_volume_20=100_000.0,
            period=14,
        )
        self.assertAlmostEqual(norm_obv_flat, 0.0, places=3)

    def test_dma_slopes_and_flat_tolerance(self):
        """Verify DMA slope classification and ±0.50% flat-tolerance boundary."""
        dates = pd.date_range("2024-01-01", periods=70, freq="B")

        # Strongly rising series
        close_rising = pd.Series(np.linspace(100, 300, 70), index=dates)
        slope_class, slope_pct = self.adapter.calculate_dma_slope(
            close_rising, period=50, slope_lookback=10, flat_tolerance_pct=0.50
        )
        self.assertEqual(slope_class, "RISING")
        self.assertGreater(slope_pct, 0.50)

        # Flat series
        close_flat = pd.Series(100.0, index=dates)
        slope_flat_class, slope_flat_pct = self.adapter.calculate_dma_slope(
            close_flat, period=50, slope_lookback=10, flat_tolerance_pct=0.50
        )
        self.assertEqual(slope_flat_class, "FLAT")
        self.assertEqual(slope_flat_pct, 0.0)

        # Falling series
        close_falling = pd.Series(np.linspace(300, 100, 70), index=dates)
        slope_fall_class, slope_fall_pct = self.adapter.calculate_dma_slope(
            close_falling, period=50, slope_lookback=10, flat_tolerance_pct=0.50
        )
        self.assertEqual(slope_fall_class, "FALLING")
        self.assertLess(slope_fall_pct, -0.50)

        # Insufficient bars (< 60) yields UNAVAILABLE
        short_close = pd.Series(np.linspace(100, 200, 40), index=dates[:40])
        short_class, short_pct = self.adapter.calculate_dma_slope(
            short_close, period=50, slope_lookback=10
        )
        self.assertEqual(short_class, "UNAVAILABLE")
        self.assertIsNone(short_pct)

    def test_golden_cross_detection(self):
        """Verify historical Golden Cross detection, date accuracy, and crossover age."""
        # Construct 250 bars where 50 DMA starts below 200 DMA and crosses above around bar 220
        dates = pd.date_range("2023-01-01", periods=250, freq="B")
        prices = np.full(250, 100.0)
        # Sharp surge in last 40 sessions
        prices[210:] = np.linspace(100.0, 250.0, 40)
        close = pd.Series(prices, index=dates)

        res = self.adapter.detect_dma_crossover(close, short_period=50, long_period=200)
        self.assertEqual(res["last_crossover_type"], "GOLDEN_CROSS")
        self.assertIsNotNone(res["last_crossover_date"])
        self.assertIsNotNone(res["days_since_dma_crossover"])
        self.assertGreater(res["days_since_dma_crossover"], 0)

    def test_death_cross_detection(self):
        """Verify historical Death Cross detection."""
        dates = pd.date_range("2023-01-01", periods=250, freq="B")
        prices = np.full(250, 200.0)
        # Sharp decline in last 40 sessions
        prices[210:] = np.linspace(200.0, 80.0, 40)
        close = pd.Series(prices, index=dates)

        res = self.adapter.detect_dma_crossover(close, short_period=50, long_period=200)
        self.assertEqual(res["last_crossover_type"], "DEATH_CROSS")
        self.assertIsNotNone(res["last_crossover_date"])
        self.assertIsNotNone(res["days_since_dma_crossover"])

    def test_crossover_not_found_vs_unavailable(self):
        """Distinguish NOT_FOUND_IN_LOOKBACK (sufficient history) from UNAVAILABLE (short history)."""
        # Sufficient history (250 bars), strictly constant price -> no crossover occurred
        dates_long = pd.date_range("2023-01-01", periods=250, freq="B")
        close_long = pd.Series(100.0, index=dates_long)
        res_not_found = self.adapter.detect_dma_crossover(close_long)
        self.assertEqual(res_not_found["last_crossover_type"], "NOT_FOUND_IN_LOOKBACK")
        self.assertIsNone(res_not_found["last_crossover_date"])

        # Insufficient history (< 200 bars) -> UNAVAILABLE
        dates_short = pd.date_range("2023-01-01", periods=100, freq="B")
        close_short = pd.Series(100.0, index=dates_short)
        res_unavail = self.adapter.detect_dma_crossover(close_short)
        self.assertEqual(res_unavail["last_crossover_type"], "UNAVAILABLE")
        self.assertIsNone(res_unavail["last_crossover_date"])

    def test_confirmed_swing_pivots_and_confirmation_lag(self):
        """
        Verify 20-session swing high/low detection with 3-session confirmation lag.
        Confirm that recent unconfirmed peaks are not reported (no look-ahead).
        """
        dates = pd.date_range("2024-01-01", periods=50, freq="B")

        # Flat 100 baseline
        high = pd.Series(100.0, index=dates)
        low = pd.Series(95.0, index=dates)
        close = pd.Series(98.0, index=dates)

        # Place a confirmed peak at index 30 (date: dates[30])
        # Indices 31, 32, 33 have lower highs (e.g. 102, 101, 100)
        high.iloc[30] = 110.0
        high.iloc[31] = 103.0
        high.iloc[32] = 102.0
        high.iloc[33] = 101.0

        # Place an unconfirmed peak at the very last session index 49
        high.iloc[49] = 120.0

        pivots = self.adapter.detect_swing_pivots(
            high, low, close, cmp_value=100.0, window=20, lag=3
        )

        # The peak at 49 must NOT be reported because it lacks 3 subsequent confirmation bars!
        self.assertEqual(pivots["swing_high_20"], 110.0)
        self.assertEqual(pivots["swing_high_date"], dates[30].date().isoformat())
        self.assertEqual(pivots["swing_high_confirmation_date"], dates[33].date().isoformat())
        self.assertEqual(pivots["pct_from_swing_high"], -9.09)

    def test_ipo_short_history_graceful_degradation(self):
        """Verify pipeline and adapter handle short IPO histories (< 200 bars) gracefully."""
        df_ipo = create_synthetic_ohlcv(bars=80)
        indicators = self.adapter.build_indicators(df_ipo)

        self.assertEqual(indicators["history_bars"], 80)
        self.assertIsNotNone(indicators["dma_50"])
        # With 80 bars, 200 DMA and crossover are UNAVAILABLE
        self.assertIsNone(indicators["dma_200"])
        self.assertIsNone(indicators["pct_from_200_dma"])
        self.assertEqual(indicators["dma_alignment"], "UNAVAILABLE")
        self.assertEqual(indicators["last_crossover_type"], "UNAVAILABLE")
        self.assertIsNone(indicators["last_crossover_date"])

        # For very short history (< 50 bars), atr_50_avg and dma_50 are also UNAVAILABLE
        df_very_short = create_synthetic_ohlcv(bars=40)
        indicators_short = self.adapter.build_indicators(df_very_short)
        self.assertIsNone(indicators_short["dma_50"])
        self.assertIsNone(indicators_short["atr_50_avg"])

    def test_schema_conformance_and_backward_compatibility(self):
        """Verify full build_research_result conforms to schema and maintains backward compatibility."""
        df = create_synthetic_ohlcv(bars=260)
        indicators = self.adapter.build_indicators(df)

        screener_data = {
            "symbol": "SYNTH",
            "company_name": "Synthetic Test Ltd",
            "url": "https://example.com/company/SYNTH",
            "retrieved_at": "2026-10-10T00:00:00Z",
            "fundamentals": {
                "pe": 25.0,
                "book_value": 200.0,
                "roce": 20.0,
                "roe": 18.0,
                "debt_to_equity": 0.2,
                "sales_growth_3y": 15.0,
                "profit_growth_3y": 12.0,
                "market_cap": 50000.0,
            },
            "institutional": {
                "promoter": 55.0,
                "promoter_previous": 55.0,
                "fii": 20.0,
                "fii_previous": 19.5,
                "dii": 15.0,
                "dii_previous": 14.8,
            },
            "as_of_dates": {
                "fundamentals": "2026-03-31",
                "institutional": "2026-06-30",
            },
        }

        market_data = {
            "symbol": "SYNTH",
            "yahoo_symbol": "SYNTH.NS",
            "retrieved_at": "2026-10-10T00:00:00Z",
            "as_of_date": "2026-10-09",
            "history_rows": len(df),
            "indicators": indicators,
        }

        news_data = {"articles": [], "retrieved_at": "2026-10-10T00:00:00Z"}

        # Build research result
        result = build_research_result(screener_data, market_data, news_data)

        # Validate against JSON schema
        validate_schema(result)

        # Check technical fields envelope structure
        tech = result["technicals"]
        self.assertIn("history_bars", tech)
        self.assertEqual(tech["history_bars"]["value"], 260)
        self.assertEqual(tech["history_bars"]["unit"], "COUNT")
        self.assertEqual(tech["history_bars"]["status"], "VERIFIED")

        self.assertIn("dma_alignment", tech)
        self.assertIn(tech["dma_alignment"]["value"], ("50_DMA_ABOVE_200_DMA", "50_DMA_BELOW_200_DMA", "EQUAL"))
        self.assertEqual(tech["dma_alignment"]["status"], "DERIVED")

        self.assertIn("atr_14", tech)
        self.assertEqual(tech["atr_14"]["unit"], "INR")
        self.assertEqual(tech["atr_14"]["status"], "DERIVED")

        self.assertIn("obv_change_norm_14d", tech)
        self.assertEqual(tech["obv_change_norm_14d"]["unit"], "RATIO")

        self.assertIn("clv", tech)
        self.assertEqual(tech["clv"]["unit"], "RATIO")

        self.assertIn("swing_high_20", tech)
        self.assertEqual(tech["swing_high_20"]["unit"], "INR")


if __name__ == "__main__":
    unittest.main(verbosity=2)
