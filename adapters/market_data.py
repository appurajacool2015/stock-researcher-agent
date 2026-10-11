#!/usr/bin/env python3

"""
Market Data Adapter
===================

Market-data adapter using Yahoo Finance via yfinance.

Responsibilities:
  - Resolve NSE stock symbols to Yahoo Finance symbols
  - Download historical daily market data with a target >= 400 trading sessions
  - Sanitize and flatten yfinance MultiIndex / unexpected column formats
  - Calculate robust moving-average dynamics (50 DMA, 200 DMA, distances, alignment, slope, crossover age)
  - Calculate volatility metrics (Wilder's ATR 14, ATR %, ATR 50-session compression baseline)
  - Calculate volume, moving averages (5, 20, 50), and relative volume
  - Calculate normalized 14-session OBV change and Close Location Value (CLV with zero-range guard)
  - Detect confirmed 20-session swing pivots with strict 3-session confirmation lag
  - Calculate 52-week High/Low and distances based on raw daily High/Low prices
  - Gracefully degrade for short history / IPOs (< 200 bars) with explicit UNAVAILABLE statuses
  - Return normalized market-data output with complete provenance
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf


class MarketDataAdapter:
    """
    Market-data adapter using Yahoo Finance via yfinance.
    """

    HISTORY_PERIOD = "2y"

    # Configurable provisional thresholds (not validated trading signals)
    DMA_FLAT_TOLERANCE_PCT = 0.50
    OBV_NORM_THRESHOLD = 0.20
    SWING_WINDOW = 20
    SWING_CONFIRMATION_LAG = 3
    SESSIONS_52W = 252

    def __init__(self):
        pass

    # =========================================================
    # SYMBOL
    # =========================================================

    @staticmethod
    def yahoo_symbol(symbol: str) -> str:
        symbol = symbol.upper().strip()

        if not symbol:
            raise ValueError("Stock symbol cannot be empty")

        if symbol.endswith(".NS"):
            return symbol

        return f"{symbol}.NS"

    # =========================================================
    # TIME
    # =========================================================

    @staticmethod
    def utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def normalize_date(value: Any) -> Optional[str]:
        """Convert a pandas Timestamp / datetime-like value into YYYY-MM-DD."""
        if value is None:
            return None

        try:
            if hasattr(value, "date"):
                return value.date().isoformat()

            text = str(value).strip()
            if not text:
                return None

            return text[:10]
        except Exception:
            return None

    @staticmethod
    def latest_trading_date(history: Any) -> Optional[str]:
        """Return the date represented by the latest row in history."""
        if history is None or history.empty:
            return None

        try:
            return MarketDataAdapter.normalize_date(history.index[-1])
        except Exception:
            return None

    # =========================================================
    # NUMERIC HELPERS
    # =========================================================

    @staticmethod
    def to_float(value: Any) -> Optional[float]:
        if value is None:
            return None

        try:
            if value != value:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def round_value(value: Optional[float], digits: int = 2) -> Optional[float]:
        if value is None:
            return None

        return round(float(value), digits)

    # =========================================================
    # COLUMN SANITIZATION
    # =========================================================

    @staticmethod
    def sanitize_history(history: pd.DataFrame) -> pd.DataFrame:
        """
        Safely flatten yfinance MultiIndex columns into standard single-level
        ['Open', 'High', 'Low', 'Close', 'Volume'] with numeric data types.
        """
        if history is None or history.empty:
            return pd.DataFrame()

        df = history.copy()

        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            # Take level 0 which contains OHLCV field names
            df.columns = df.columns.get_level_values(0)

        # Remove duplicate column names if any
        if df.columns.duplicated().any():
            df = df.loc[:, ~df.columns.duplicated()]

        # Case-insensitive normalization for expected columns
        expected = ["Open", "High", "Low", "Close", "Volume"]
        current_cols = {str(c).strip().lower(): c for c in df.columns}
        rename_map = {}
        for exp in expected:
            if exp not in df.columns and exp.lower() in current_cols:
                rename_map[current_cols[exp.lower()]] = exp

        if rename_map:
            df = df.rename(columns=rename_map)

        # Convert to numeric float
        for col in expected:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Drop rows where Close is missing
        if "Close" in df.columns:
            df = df.dropna(subset=["Close"])

        return df

    # =========================================================
    # HISTORY FETCH
    # =========================================================

    def fetch_history(self, symbol: str) -> pd.DataFrame:
        """
        Download historical daily market data.
        period='2y' targets >= 400 valid trading sessions for 200 DMA + lookbacks.
        """
        yahoo_symbol = self.yahoo_symbol(symbol)
        ticker = yf.Ticker(yahoo_symbol)

        raw_history = ticker.history(
            period=self.HISTORY_PERIOD,
            interval="1d",
            auto_adjust=False,
        )

        if raw_history is None or raw_history.empty:
            raise RuntimeError(f"No market data returned for {yahoo_symbol}")

        history = self.sanitize_history(raw_history)
        if history.empty:
            raise RuntimeError(f"No valid OHLCV price bars found for {yahoo_symbol}")

        return history

    # =========================================================
    # RSI
    # =========================================================

    @staticmethod
    def calculate_rsi(close: pd.Series, period: int = 14) -> Optional[float]:
        if close is None or len(close) < period + 1:
            return None

        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

        latest_gain = avg_gain.iloc[-1]
        latest_loss = avg_loss.iloc[-1]

        if latest_gain != latest_gain or latest_loss != latest_loss:
            return None

        if latest_loss == 0:
            return 100.0

        rs = latest_gain / latest_loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi)

    # =========================================================
    # ATR & VOLATILITY (WILDER'S SMOOTHING)
    # =========================================================

    @staticmethod
    def calculate_atr(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        cmp_value: Optional[float],
        period: int = 14,
        baseline_period: int = 50,
    ) -> Dict[str, Any]:
        """
        Calculate ATR(14) using Wilder's smoothing, ATR percentage,
        and ATR(50) baseline to assess range compression.
        """
        res: Dict[str, Any] = {
            "atr_14": None,
            "atr_pct": None,
            "atr_50_avg": None,
        }

        if len(close) < period + 1:
            return res

        prev_close = close.shift(1)
        tr0 = high - low
        tr1 = (high - prev_close).abs()
        tr2 = (low - prev_close).abs()
        tr = pd.concat([tr0, tr1, tr2], axis=1).max(axis=1)

        # Wilder's smoothing using alpha=1/period
        atr_series = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

        latest_atr = atr_series.iloc[-1]
        if latest_atr == latest_atr:
            res["atr_14"] = round(float(latest_atr), 2)
            if cmp_value and cmp_value > 0:
                res["atr_pct"] = round((float(latest_atr) / cmp_value) * 100, 2)

        # 50-session average of ATR(14) baseline
        valid_atrs = atr_series.dropna()
        if len(valid_atrs) >= baseline_period:
            baseline = valid_atrs.tail(baseline_period).mean()
            if baseline == baseline:
                res["atr_50_avg"] = round(float(baseline), 2)

        return res

    # =========================================================
    # CLV (CLOSE LOCATION VALUE) WITH ZERO-RANGE GUARD
    # =========================================================

    @staticmethod
    def calculate_clv(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14,
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Close Location Value: ((Close - Low) - (High - Close)) / (High - Low)
        Zero-Range Guard: If High == Low (e.g. circuit locks), CLV is explicitly 0.0.
        """
        if len(close) == 0:
            return None, None

        hl_spread = high - low
        clv_series = pd.Series(0.0, index=close.index, dtype=float)

        valid_spread = hl_spread > 0
        clv_series[valid_spread] = (
            (close[valid_spread] - low[valid_spread])
            - (high[valid_spread] - close[valid_spread])
        ) / hl_spread[valid_spread]

        clv_series = clv_series.clip(-1.0, 1.0)

        latest_clv = round(float(clv_series.iloc[-1]), 4)
        avg_clv_14 = (
            round(float(clv_series.tail(period).mean()), 4)
            if len(clv_series) >= period
            else None
        )

        return latest_clv, avg_clv_14

    # =========================================================
    # NORMALIZED 14-SESSION OBV CHANGE
    # =========================================================

    @staticmethod
    def calculate_normalized_obv_change(
        close: pd.Series,
        volume: pd.Series,
        avg_volume_20: Optional[float],
        period: int = 14,
    ) -> Optional[float]:
        """
        Normalized 14-session OBV change:
          (OBV[today] - OBV[14_sessions_ago]) / (avg_volume_20 * 14)
        """
        if (
            len(close) < period + 1
            or avg_volume_20 is None
            or avg_volume_20 <= 0
        ):
            return None

        delta = close.diff()
        direction = pd.Series(0.0, index=close.index, dtype=float)
        direction[delta > 0] = 1.0
        direction[delta < 0] = -1.0

        obv = (direction * volume).cumsum()

        obv_now = obv.iloc[-1]
        obv_past = obv.iloc[-(period + 1)]

        delta_obv = obv_now - obv_past
        denominator = avg_volume_20 * period

        if denominator == 0:
            return None

        norm_change = delta_obv / denominator
        return round(float(norm_change), 4)

    # =========================================================
    # DMA SLOPES
    # =========================================================

    @staticmethod
    def calculate_dma_slope(
        close: pd.Series,
        period: int,
        slope_lookback: int = 10,
        flat_tolerance_pct: float = 0.50,
    ) -> Tuple[str, Optional[float]]:
        """
        Calculate % change of DMA over past 10 sessions.
        Returns (classification, slope_pct).
        Classification: 'RISING', 'FALLING', 'FLAT', or 'UNAVAILABLE'.
        """
        min_bars_needed = period + slope_lookback
        if len(close) < min_bars_needed:
            return "UNAVAILABLE", None

        dma_series = close.rolling(window=period).mean()
        current_dma = dma_series.iloc[-1]
        past_dma = dma_series.iloc[-(slope_lookback + 1)]

        if current_dma is None or past_dma is None or past_dma == 0:
            return "UNAVAILABLE", None

        slope_pct = round(((current_dma - past_dma) / past_dma) * 100, 2)

        if slope_pct > flat_tolerance_pct:
            classification = "RISING"
        elif slope_pct < -flat_tolerance_pct:
            classification = "FALLING"
        else:
            classification = "FLAT"

        return classification, slope_pct

    # =========================================================
    # HISTORICAL DMA CROSSOVER DETECTION
    # =========================================================

    @staticmethod
    def detect_dma_crossover(
        close: pd.Series,
        short_period: int = 50,
        long_period: int = 200,
    ) -> Dict[str, Any]:
        """
        Detect Golden Cross / Death Cross strictly from historical transitions.
        Distinguishes 'NOT_FOUND_IN_LOOKBACK' from 'UNAVAILABLE'.
        """
        res: Dict[str, Any] = {
            "last_crossover_type": "UNAVAILABLE",
            "last_crossover_date": None,
            "days_since_dma_crossover": None,
            "notes": None,
        }

        if len(close) < long_period:
            res["notes"] = f"Insufficient history ({len(close)} bars < {long_period}) for 200 DMA crossover detection."
            return res

        sma50 = close.rolling(window=short_period).mean()
        sma200 = close.rolling(window=long_period).mean()

        diff = sma50 - sma200

        # Scan backwards from latest session to find the most recent crossover
        crossover_idx = None
        crossover_type = None

        # Comparison starts at long_period index
        for i in range(len(close) - 1, long_period - 1, -1):
            curr_diff = diff.iloc[i]
            prev_diff = diff.iloc[i - 1]

            if curr_diff > 0 and prev_diff <= 0:
                crossover_idx = i
                crossover_type = "GOLDEN_CROSS"
                break
            elif curr_diff < 0 and prev_diff >= 0:
                crossover_idx = i
                crossover_type = "DEATH_CROSS"
                break

        if crossover_idx is not None:
            crossover_date = MarketDataAdapter.normalize_date(close.index[crossover_idx])
            days_since = len(close) - 1 - crossover_idx
            res["last_crossover_type"] = crossover_type
            res["last_crossover_date"] = crossover_date
            res["days_since_dma_crossover"] = days_since
            res["notes"] = (
                f"{crossover_type} occurred on {crossover_date} "
                f"({days_since} trading sessions ago)."
            )
        else:
            res["last_crossover_type"] = "NOT_FOUND_IN_LOOKBACK"
            res["notes"] = f"No 50/200 DMA crossover occurred within the available {len(close)} sessions."

        return res

    # =========================================================
    # CONFIRMED 20-SESSION SWING PIVOTS (3-SESSION CONFIRMATION LAG)
    # =========================================================

    @staticmethod
    def detect_swing_pivots(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        cmp_value: Optional[float],
        window: int = 20,
        lag: int = 3,
    ) -> Dict[str, Any]:
        """
        Identify 20-session swing highs and swing lows with 3-session confirmation lag.
        Look-ahead bias is prevented: the 3 most recent sessions cannot be confirmed pivots.
        """
        res: Dict[str, Any] = {
            "swing_high_20": None,
            "swing_high_date": None,
            "swing_high_confirmation_date": None,
            "pct_from_swing_high": None,
            "swing_low_20": None,
            "swing_low_date": None,
            "swing_low_confirmation_date": None,
            "pct_from_swing_low": None,
        }

        n = len(close)
        if n < window + lag:
            return res

        # Scan backwards for confirmed swing high
        for i in range(n - 1 - lag, window - 1, -1):
            pivot_cand = high.iloc[i]
            # Must be maximum of the 20-session preceding window [i - window + 1 : i + 1]
            window_slice = high.iloc[i - window + 1 : i + 1]
            if pivot_cand >= window_slice.max():
                # Confirm 3 subsequent sessions have lower highs
                if (
                    high.iloc[i + 1] < pivot_cand
                    and high.iloc[i + 2] < pivot_cand
                    and high.iloc[i + 3] < pivot_cand
                ):
                    res["swing_high_20"] = round(float(pivot_cand), 2)
                    res["swing_high_date"] = MarketDataAdapter.normalize_date(high.index[i])
                    res["swing_high_confirmation_date"] = MarketDataAdapter.normalize_date(high.index[i + lag])
                    if cmp_value and res["swing_high_20"] > 0:
                        res["pct_from_swing_high"] = round(
                            ((cmp_value - res["swing_high_20"]) / res["swing_high_20"]) * 100, 2
                        )
                    break

        # Scan backwards for confirmed swing low
        for i in range(n - 1 - lag, window - 1, -1):
            pivot_cand = low.iloc[i]
            # Must be minimum of the 20-session preceding window [i - window + 1 : i + 1]
            window_slice = low.iloc[i - window + 1 : i + 1]
            if pivot_cand <= window_slice.min():
                # Confirm 3 subsequent sessions have higher lows
                if (
                    low.iloc[i + 1] > pivot_cand
                    and low.iloc[i + 2] > pivot_cand
                    and low.iloc[i + 3] > pivot_cand
                ):
                    res["swing_low_20"] = round(float(pivot_cand), 2)
                    res["swing_low_date"] = MarketDataAdapter.normalize_date(low.index[i])
                    res["swing_low_confirmation_date"] = MarketDataAdapter.normalize_date(low.index[i + lag])
                    if cmp_value and res["swing_low_20"] > 0:
                        res["pct_from_swing_low"] = round(
                            ((cmp_value - res["swing_low_20"]) / res["swing_low_20"]) * 100, 2
                        )
                    break

        return res

    # =========================================================
    # VOLUME METRICS
    # =========================================================

    @staticmethod
    def calculate_volume_metrics(volume: pd.Series) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "volume": None,
            "avg_volume_5": None,
            "avg_volume_20": None,
            "avg_volume_50": None,
            "avg_volume_1w": None,
            "avg_volume_1m": None,
            "volume_vs_20d_pct": None,
            "volume_vs_1w_pct": None,
            "volume_vs_1m_pct": None,
            "volume_above_1w": None,
            "volume_above_1m": None,
            "volume_traction": None,
        }

        if volume is None or len(volume) == 0:
            return result

        current_volume = MarketDataAdapter.to_float(volume.iloc[-1])
        result["volume"] = current_volume

        # Moving averages: 5 sessions (1w), 20 sessions, 50 sessions
        avg_5 = MarketDataAdapter.to_float(volume.tail(5).mean()) if len(volume) >= 5 else None
        avg_20 = MarketDataAdapter.to_float(volume.tail(20).mean()) if len(volume) >= 20 else None
        avg_50 = MarketDataAdapter.to_float(volume.tail(50).mean()) if len(volume) >= 50 else None

        # Preserved legacy 21-session 1m average
        avg_21 = MarketDataAdapter.to_float(volume.tail(21).mean()) if len(volume) >= 21 else avg_20

        result["avg_volume_5"] = avg_5
        result["avg_volume_20"] = avg_20
        result["avg_volume_50"] = avg_50
        result["avg_volume_1w"] = avg_5
        result["avg_volume_1m"] = avg_21

        if current_volume is not None and avg_20 is not None and avg_20 > 0:
            result["volume_vs_20d_pct"] = round(((current_volume / avg_20) - 1) * 100, 2)

        if current_volume is not None and avg_5 is not None and avg_5 > 0:
            result["volume_vs_1w_pct"] = round(((current_volume / avg_5) - 1) * 100, 2)
            result["volume_above_1w"] = current_volume > avg_5

        if current_volume is not None and avg_21 is not None and avg_21 > 0:
            result["volume_vs_1m_pct"] = round(((current_volume / avg_21) - 1) * 100, 2)
            result["volume_above_1m"] = current_volume > avg_21

        if current_volume is not None and avg_5 is not None and avg_21 is not None:
            result["volume_traction"] = current_volume > avg_5 and avg_5 > avg_21

        return result

    # =========================================================
    # BUILD INDICATORS
    # =========================================================

    def build_indicators(self, history: pd.DataFrame) -> Dict[str, Any]:
        """
        Build full suite of deterministic technical metrics from sanitized history.
        """
        df = self.sanitize_history(history)
        if df.empty:
            raise RuntimeError("Cannot build indicators from empty sanitized history")

        close = df["Close"]
        high = df["High"] if "High" in df.columns else close
        low = df["Low"] if "Low" in df.columns else close
        volume = df["Volume"] if "Volume" in df.columns else pd.Series(0.0, index=df.index)

        usable_bars = len(df)
        cmp_value = self.to_float(close.iloc[-1])

        # -----------------------------------------------------
        # Moving averages & distances
        # -----------------------------------------------------
        dma_50 = self.to_float(close.tail(50).mean()) if usable_bars >= 50 else None
        dma_200 = self.to_float(close.tail(200).mean()) if usable_bars >= 200 else None

        pct_from_50_dma = (
            round(((cmp_value - dma_50) / dma_50) * 100, 2)
            if cmp_value is not None and dma_50 is not None and dma_50 > 0
            else None
        )

        pct_from_200_dma = (
            round(((cmp_value - dma_200) / dma_200) * 100, 2)
            if cmp_value is not None and dma_200 is not None and dma_200 > 0
            else None
        )

        above_50_dma = (
            cmp_value > dma_50
            if cmp_value is not None and dma_50 is not None
            else None
        )

        above_200_dma = (
            cmp_value > dma_200
            if cmp_value is not None and dma_200 is not None
            else None
        )

        # DMA Alignment
        if dma_50 is not None and dma_200 is not None:
            if dma_50 > dma_200:
                dma_alignment = "50_DMA_ABOVE_200_DMA"
            elif dma_50 < dma_200:
                dma_alignment = "50_DMA_BELOW_200_DMA"
            else:
                dma_alignment = "EQUAL"
        else:
            dma_alignment = "UNAVAILABLE"

        # -----------------------------------------------------
        # DMA Slopes (50 and 200)
        # -----------------------------------------------------
        dma_slope_50, dma_slope_50_pct = self.calculate_dma_slope(
            close,
            period=50,
            slope_lookback=10,
            flat_tolerance_pct=self.DMA_FLAT_TOLERANCE_PCT,
        )

        dma_slope_200, dma_slope_200_pct = self.calculate_dma_slope(
            close,
            period=200,
            slope_lookback=10,
            flat_tolerance_pct=self.DMA_FLAT_TOLERANCE_PCT,
        )

        # -----------------------------------------------------
        # Historical DMA crossover
        # -----------------------------------------------------
        crossover_info = self.detect_dma_crossover(
            close,
            short_period=50,
            long_period=200,
        )

        # -----------------------------------------------------
        # Volatility (ATR 14, ATR %, ATR 50-session baseline)
        # -----------------------------------------------------
        atr_info = self.calculate_atr(
            high,
            low,
            close,
            cmp_value,
            period=14,
            baseline_period=50,
        )

        # -----------------------------------------------------
        # Momentum (RSI 14)
        # -----------------------------------------------------
        rsi_14 = self.calculate_rsi(close, period=14)

        # -----------------------------------------------------
        # Volume metrics
        # -----------------------------------------------------
        volume_metrics = self.calculate_volume_metrics(volume)

        # -----------------------------------------------------
        # Normalized OBV change (14d) & CLV
        # -----------------------------------------------------
        obv_change_norm_14d = self.calculate_normalized_obv_change(
            close,
            volume,
            avg_volume_20=volume_metrics.get("avg_volume_20"),
            period=14,
        )

        clv, clv_14_avg = self.calculate_clv(high, low, close, period=14)

        # -----------------------------------------------------
        # 52-week High / Low (raw daily High and Low)
        # -----------------------------------------------------
        window_52w = min(self.SESSIONS_52W, usable_bars)
        fifty_two_week_high = self.to_float(high.tail(window_52w).max())
        fifty_two_week_low = self.to_float(low.tail(window_52w).min())

        pct_from_52w_high = (
            round(((cmp_value - fifty_two_week_high) / fifty_two_week_high) * 100, 2)
            if cmp_value is not None and fifty_two_week_high is not None and fifty_two_week_high > 0
            else None
        )

        pct_from_52w_low = (
            round(((cmp_value - fifty_two_week_low) / fifty_two_week_low) * 100, 2)
            if cmp_value is not None and fifty_two_week_low is not None and fifty_two_week_low > 0
            else None
        )

        # -----------------------------------------------------
        # Confirmed 20-session swing pivots (3-session lag)
        # -----------------------------------------------------
        swing_info = self.detect_swing_pivots(
            high,
            low,
            close,
            cmp_value,
            window=self.SWING_WINDOW,
            lag=self.SWING_CONFIRMATION_LAG,
        )

        # -----------------------------------------------------
        # Assemble dictionary
        # -----------------------------------------------------
        return {
            "history_bars": usable_bars,
            "cmp": self.round_value(cmp_value),
            "dma_50": self.round_value(dma_50),
            "dma_200": self.round_value(dma_200),
            "pct_from_50_dma": pct_from_50_dma,
            "pct_from_200_dma": pct_from_200_dma,
            "above_50_dma": above_50_dma,
            "above_200_dma": above_200_dma,
            "dma_alignment": dma_alignment,
            "dma_slope_50": dma_slope_50,
            "dma_slope_50_pct": dma_slope_50_pct,
            "dma_slope_200": dma_slope_200,
            "dma_slope_200_pct": dma_slope_200_pct,
            "last_crossover_type": crossover_info["last_crossover_type"],
            "last_crossover_date": crossover_info["last_crossover_date"],
            "days_since_dma_crossover": crossover_info["days_since_dma_crossover"],
            "crossover_notes": crossover_info["notes"],
            "atr_14": atr_info["atr_14"],
            "atr_pct": atr_info["atr_pct"],
            "atr_50_avg": atr_info["atr_50_avg"],
            "rsi_14": self.round_value(rsi_14),
            **volume_metrics,
            "obv_change_norm_14d": obv_change_norm_14d,
            "clv": clv,
            "clv_14_avg": clv_14_avg,
            "fifty_two_week_high": self.round_value(fifty_two_week_high),
            "fifty_two_week_low": self.round_value(fifty_two_week_low),
            "pct_from_52w_high": pct_from_52w_high,
            "pct_from_52w_low": pct_from_52w_low,
            **swing_info,
        }

    # =========================================================
    # PUBLIC RESEARCH METHOD
    # =========================================================

    def research(self, symbol: str) -> Dict[str, Any]:
        symbol = symbol.upper().strip()

        if not symbol:
            raise ValueError("Stock symbol cannot be empty")

        yahoo_symbol = self.yahoo_symbol(symbol)
        retrieved_at = self.utc_now()
        history = self.fetch_history(symbol)
        as_of_date = self.latest_trading_date(history)
        indicators = self.build_indicators(history)

        return {
            "symbol": symbol,
            "yahoo_symbol": yahoo_symbol,
            "retrieved_at": retrieved_at,
            "as_of_date": as_of_date,
            "history_rows": len(history),
            "indicators": indicators,
        }

    # =========================================================
    # CLI
    # =========================================================

    def run_cli(self, symbol: str) -> None:
        result = self.research(symbol)
        print(json.dumps(result, indent=2, ensure_ascii=False))


def main():
    symbol = sys.argv[1].upper().strip() if len(sys.argv) > 1 else "TCS"
    adapter = MarketDataAdapter()
    adapter.run_cli(symbol)


if __name__ == "__main__":
    main()
