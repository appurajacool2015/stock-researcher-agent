#!/usr/bin/env python3

import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import yfinance as yf


class MarketDataAdapter:
    """
    Market-data adapter using Yahoo Finance via yfinance.

    Responsibilities:
      - Resolve NSE stock symbols to Yahoo Finance symbols
      - Download historical market data
      - Calculate technical indicators
      - Calculate recent volume averages
      - Calculate volume traction signals
      - Identify the latest trading date
      - Return normalized market-data output

    It does NOT:
      - perform investment analysis
      - assign stock ratings
      - make investment decisions
      - modify ResearchResult schema
    """

    HISTORY_PERIOD = "500d"

    def __init__(self):
        pass

    # =========================================================
    # SYMBOL
    # =========================================================

    @staticmethod
    def yahoo_symbol(symbol: str) -> str:
        symbol = symbol.upper().strip()

        if not symbol:
            raise ValueError(
                "Stock symbol cannot be empty"
            )

        if symbol.endswith(".NS"):
            return symbol

        return f"{symbol}.NS"

    # =========================================================
    # TIME
    # =========================================================

    @staticmethod
    def utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def normalize_date(value: Any) -> Optional[str]:
        """
        Convert a pandas Timestamp / datetime-like value
        into YYYY-MM-DD.

        Returns None when the date cannot be determined.
        """

        if value is None:
            return None

        try:
            # pandas Timestamp / datetime-like objects
            if hasattr(value, "date"):
                return value.date().isoformat()

            # ISO-like strings
            text = str(value).strip()

            if not text:
                return None

            # Handle strings such as:
            # 2026-09-01
            # 2026-09-01 00:00:00
            # 2026-09-01T00:00:00+05:30
            return text[:10]

        except Exception:
            return None

    @staticmethod
    def latest_trading_date(history) -> Optional[str]:
        """
        Return the date represented by the latest row
        in the downloaded historical dataset.
        """

        if history is None or history.empty:
            return None

        try:
            return MarketDataAdapter.normalize_date(
                history.index[-1]
            )
        except Exception:
            return None

    # =========================================================
    # HISTORY
    # =========================================================

    def fetch_history(self, symbol: str):
        """
        Download historical daily market data.

        500 trading days gives enough history for:
          - 50 DMA
          - 200 DMA
          - RSI
          - 52-week high/low
          - volume averages
        """

        yahoo_symbol = self.yahoo_symbol(symbol)

        ticker = yf.Ticker(yahoo_symbol)

        history = ticker.history(
            period=self.HISTORY_PERIOD,
            interval="1d",
            auto_adjust=False,
        )

        if history is None or history.empty:
            raise RuntimeError(
                f"No market data returned for {yahoo_symbol}"
            )

        return history

    # =========================================================
    # NUMERIC HELPERS
    # =========================================================

    @staticmethod
    def to_float(
        value: Any,
    ) -> Optional[float]:

        if value is None:
            return None

        try:
            # Handle pandas/numpy NaN without
            # importing numpy directly.
            if value != value:
                return None

            return float(value)

        except (
            TypeError,
            ValueError,
        ):

            return None

    @staticmethod
    def round_value(
        value: Optional[float],
        digits: int = 2,
    ) -> Optional[float]:

        if value is None:
            return None

        return round(
            float(value),
            digits,
        )

    # =========================================================
    # RSI
    # =========================================================

    @staticmethod
    def calculate_rsi(
        close,
        period: int = 14,
    ) -> Optional[float]:

        if close is None:
            return None

        if len(close) < period + 1:
            return None

        delta = close.diff()

        gain = delta.clip(
            lower=0
        )

        loss = -delta.clip(
            upper=0
        )

        avg_gain = gain.ewm(
            alpha=1 / period,
            min_periods=period,
            adjust=False,
        ).mean()

        avg_loss = loss.ewm(
            alpha=1 / period,
            min_periods=period,
            adjust=False,
        ).mean()

        latest_gain = avg_gain.iloc[-1]
        latest_loss = avg_loss.iloc[-1]

        if latest_gain != latest_gain:
            return None

        if latest_loss != latest_loss:
            return None

        if latest_loss == 0:
            return 100.0

        rs = latest_gain / latest_loss

        rsi = 100 - (
            100 / (1 + rs)
        )

        return float(rsi)

    # =========================================================
    # VOLUME
    # =========================================================

    @staticmethod
    def calculate_volume_metrics(
        volume,
    ) -> Dict[str, Any]:

        result = {
            "volume": None,
            "avg_volume_1w": None,
            "avg_volume_1m": None,
            "volume_vs_1w_pct": None,
            "volume_vs_1m_pct": None,
            "volume_above_1w": None,
            "volume_above_1m": None,
            "volume_traction": None,
        }

        if volume is None:
            return result

        if len(volume) == 0:
            return result

        current_volume = (
            MarketDataAdapter.to_float(
                volume.iloc[-1]
            )
        )

        result["volume"] = current_volume

        # Latest 5 trading sessions
        if len(volume) >= 5:
            avg_1w = MarketDataAdapter.to_float(
                volume.tail(5).mean()
            )
        else:
            avg_1w = None

        # Latest 21 trading sessions
        if len(volume) >= 21:
            avg_1m = MarketDataAdapter.to_float(
                volume.tail(21).mean()
            )
        else:
            avg_1m = None

        result["avg_volume_1w"] = avg_1w
        result["avg_volume_1m"] = avg_1m

        if (
            current_volume is not None
            and avg_1w is not None
            and avg_1w != 0
        ):
            result["volume_vs_1w_pct"] = round(
                (
                    (current_volume / avg_1w) - 1
                ) * 100,
                2,
            )

            result["volume_above_1w"] = (
                current_volume > avg_1w
            )

        if (
            current_volume is not None
            and avg_1m is not None
            and avg_1m != 0
        ):
            result["volume_vs_1m_pct"] = round(
                (
                    (current_volume / avg_1m) - 1
                ) * 100,
                2,
            )

            result["volume_above_1m"] = (
                current_volume > avg_1m
            )

        if (
            current_volume is not None
            and avg_1w is not None
            and avg_1m is not None
        ):
            result["volume_traction"] = (
                current_volume > avg_1w
                and avg_1w > avg_1m
            )

        return result

    # =========================================================
    # BUILD INDICATORS
    # =========================================================

    def build_indicators(
        self,
        history,
    ) -> Dict[str, Any]:

        if history is None or history.empty:
            raise RuntimeError(
                "Cannot build indicators from empty history"
            )

        close = history["Close"]
        volume = history["Volume"]

        cmp_value = self.to_float(
            close.iloc[-1]
        )

        dma_50 = None

        if len(close) >= 50:
            dma_50 = self.to_float(
                close.tail(50).mean()
            )

        dma_200 = None

        if len(close) >= 200:
            dma_200 = self.to_float(
                close.tail(200).mean()
            )

        rsi_14 = self.calculate_rsi(
            close,
            period=14,
        )

        volume_metrics = (
            self.calculate_volume_metrics(
                volume
            )
        )

        # -----------------------------------------------------
        # 52-WEEK RANGE
        # -----------------------------------------------------

        fifty_two_week_high = None
        fifty_two_week_low = None

        # Approximately 252 trading sessions.
        if len(close) >= 1:

            window = close.tail(
                min(252, len(close))
            )

            fifty_two_week_high = self.to_float(
                window.max()
            )

            fifty_two_week_low = self.to_float(
                window.min()
            )

        return {
            "cmp": self.round_value(
                cmp_value
            ),

            "dma_50": self.round_value(
                dma_50
            ),

            "dma_200": self.round_value(
                dma_200
            ),

            "above_50_dma": (
                None
                if cmp_value is None
                or dma_50 is None
                else cmp_value > dma_50
            ),

            "above_200_dma": (
                None
                if cmp_value is None
                or dma_200 is None
                else cmp_value > dma_200
            ),

            "rsi_14": self.round_value(
                rsi_14
            ),

            **volume_metrics,

            "fifty_two_week_high": self.round_value(
                fifty_two_week_high
            ),

            "fifty_two_week_low": self.round_value(
                fifty_two_week_low
            ),
        }

    # =========================================================
    # PUBLIC RESEARCH METHOD
    # =========================================================

    def research(
        self,
        symbol: str,
    ) -> Dict[str, Any]:

        symbol = symbol.upper().strip()

        if not symbol:
            raise ValueError(
                "Stock symbol cannot be empty"
            )

        yahoo_symbol = self.yahoo_symbol(
            symbol
        )

        retrieved_at = self.utc_now()

        history = self.fetch_history(
            symbol
        )

        as_of_date = (
            self.latest_trading_date(
                history
            )
        )

        indicators = self.build_indicators(
            history
        )

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

    def run_cli(
        self,
        symbol: str,
    ) -> None:

        result = self.research(
            symbol
        )

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
        )


def main():

    symbol = (
        sys.argv[1].upper().strip()
        if len(sys.argv) > 1
        else "TCS"
    )

    adapter = MarketDataAdapter()

    adapter.run_cli(symbol)


if __name__ == "__main__":
    main()
