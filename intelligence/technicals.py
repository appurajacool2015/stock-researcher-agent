#!/usr/bin/env python3

"""
Technicals Intelligence Module

Purpose
-------
Interpret technical facts from the canonical ResearchResult v1.

Architecture principle
----------------------
Adapters collect facts.
Intelligence interprets facts.

This module:
- does not collect market data
- does not call external APIs
- does not modify ResearchResult v1
- does not make BUY/SELL decisions
- does not invent unavailable values
- preserves source status and provenance
- uses deterministic rules
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional


MODULE_NAME = "technicals"
MODULE_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# RSI
RSI_OVERSOLD = 30.0
RSI_WEAK = 45.0
RSI_NEUTRAL_HIGH = 55.0
RSI_STRONG = 70.0

# Distance from moving averages
DMA_NEAR_PCT = 3.0

# 52-week position
WEEK52_LOW_ZONE = 25.0
WEEK52_HIGH_ZONE = 75.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _number(value: Any) -> Optional[float]:
    """Convert a value to float, returning None when unavailable."""

    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _boolean(value: Any) -> Optional[bool]:
    """Convert a value to boolean, preserving unavailable as None."""

    if value is None:
        return None

    if isinstance(value, bool):
        return value

    return None


def _fact(
    technicals: Dict[str, Any],
    key: str,
) -> Dict[str, Any]:
    """
    Read a canonical ResearchResult v1 technical fact.
    """

    raw = technicals.get(key)

    if not isinstance(raw, dict):
        return {
            "value": None,
            "unit": None,
            "status": "UNAVAILABLE",
            "provenance": None,
            "notes": None,
        }

    value = raw.get("value")

    if raw.get("unit") == "BOOLEAN":
        normalized_value = _boolean(value)
    else:
        normalized_value = _number(value)

    return {
        "value": normalized_value,
        "unit": raw.get("unit"),
        "status": raw.get("status", "UNAVAILABLE"),
        "provenance": raw.get("provenance"),
        "notes": raw.get("notes"),
    }


def _average(
    values: list[Optional[int]],
) -> Optional[float]:
    """Average available scores."""

    available = [
        value
        for value in values
        if value is not None
    ]

    if not available:
        return None

    return round(
        sum(available) / len(available),
        2,
    )


def _bias(score: Optional[float]) -> str:
    """Translate score into an analytical bias."""

    if score is None:
        return "INSUFFICIENT_DATA"

    if score >= 75:
        return "POSITIVE"

    if score >= 50:
        return "MIXED"

    return "NEGATIVE"


# ---------------------------------------------------------------------------
# Moving average analysis
# ---------------------------------------------------------------------------

def _moving_average_signal(
    cmp: Dict[str, Any],
    dma: Dict[str, Any],
    above_dma: Dict[str, Any],
    period: int,
) -> Dict[str, Any]:
    """
    Analyze CMP relative to a moving average.

    Signals:
        ABOVE
        BELOW
        NEAR_ABOVE
        NEAR_BELOW
        UNAVAILABLE
    """

    cmp_value = cmp["value"]
    dma_value = dma["value"]
    above_value = above_dma["value"]

    if cmp_value is None or dma_value is None:
        return {
            "period": period,
            "signal": "UNAVAILABLE",
            "score": None,
            "cmp": cmp_value,
            "dma": dma_value,
            "distance_pct": None,
            "source_status": {
                "cmp": cmp["status"],
                "dma": dma["status"],
                "above_dma": above_dma["status"],
            },
            "provenance": dma["provenance"],
        }

    distance_pct = round(
        ((cmp_value - dma_value) / dma_value) * 100,
        2,
    )

    if above_value is True:
        if distance_pct <= DMA_NEAR_PCT:
            signal = "NEAR_ABOVE"
            score = 65
        else:
            signal = "ABOVE"
            score = 85
    elif above_value is False:
        if abs(distance_pct) <= DMA_NEAR_PCT:
            signal = "NEAR_BELOW"
            score = 40
        else:
            signal = "BELOW"
            score = 25
    else:
        signal = (
            "ABOVE"
            if distance_pct > 0
            else "BELOW"
        )

        score = (
            85
            if distance_pct > 0
            else 25
        )

    return {
        "period": period,
        "signal": signal,
        "score": score,
        "cmp": cmp_value,
        "dma": dma_value,
        "distance_pct": distance_pct,
        "source_status": {
            "cmp": cmp["status"],
            "dma": dma["status"],
            "above_dma": above_dma["status"],
        },
        "provenance": dma["provenance"],
    }


# ---------------------------------------------------------------------------
# RSI analysis
# ---------------------------------------------------------------------------

def _rsi_signal(
    fact: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Interpret RSI(14).

    Bands:

        <30       OVERSOLD
        30-45     WEAK
        45-55     NEUTRAL
        55-70     STRONG
        >70       OVERBOUGHT
    """

    value = fact["value"]

    if value is None:
        return {
            "signal": "UNAVAILABLE",
            "score": None,
            "value": None,
            "unit": fact["unit"],
            "source_status": fact["status"],
            "provenance": fact["provenance"],
            "notes": fact["notes"],
        }

    if value < RSI_OVERSOLD:
        signal = "OVERSOLD"
        score = 60
    elif value < RSI_WEAK:
        signal = "WEAK"
        score = 35
    elif value < RSI_NEUTRAL_HIGH:
        signal = "NEUTRAL"
        score = 60
    elif value <= RSI_STRONG:
        signal = "STRONG"
        score = 85
    else:
        signal = "OVERBOUGHT"
        score = 45

    return {
        "signal": signal,
        "score": score,
        "value": value,
        "unit": fact["unit"],
        "source_status": fact["status"],
        "provenance": fact["provenance"],
        "notes": fact["notes"],
    }


# ---------------------------------------------------------------------------
# Volume analysis
# ---------------------------------------------------------------------------

def _volume_signal(
    volume: Dict[str, Any],
    avg_1w: Dict[str, Any],
    avg_1m: Dict[str, Any],
    volume_vs_1w: Dict[str, Any],
    volume_vs_1m: Dict[str, Any],
    above_1w: Dict[str, Any],
    above_1m: Dict[str, Any],
    traction: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Interpret volume participation.

    Strong traction requires:
        current volume > 1-week average
        AND
        1-week average > 1-month average

    This uses the adapter's explicit volume_traction fact.
    """

    traction_value = traction["value"]

    if traction_value is None:
        signal = "UNAVAILABLE"
        score = None
    elif traction_value is True:
        signal = "STRONG_TRACTION"
        score = 90
    elif above_1w["value"] is True and above_1m["value"] is False:
        signal = "MIXED"
        score = 60
    elif above_1w["value"] is False and above_1m["value"] is False:
        signal = "WEAK"
        score = 35
    elif above_1w["value"] is True:
        signal = "POSITIVE"
        score = 75
    else:
        signal = "MIXED"
        score = 55

    return {
        "signal": signal,
        "score": score,
        "volume": volume["value"],
        "avg_volume_1w": avg_1w["value"],
        "avg_volume_1m": avg_1m["value"],
        "volume_vs_1w_pct": volume_vs_1w["value"],
        "volume_vs_1m_pct": volume_vs_1m["value"],
        "above_1w": above_1w["value"],
        "above_1m": above_1m["value"],
        "traction": traction_value,
        "source_status": {
            "volume": volume["status"],
            "avg_volume_1w": avg_1w["status"],
            "avg_volume_1m": avg_1m["status"],
            "volume_vs_1w_pct": volume_vs_1w["status"],
            "volume_vs_1m_pct": volume_vs_1m["status"],
            "volume_above_1w": above_1w["status"],
            "volume_above_1m": above_1m["status"],
            "volume_traction": traction["status"],
        },
        "provenance": traction["provenance"],
        "notes": traction["notes"],
    }


# ---------------------------------------------------------------------------
# 52-week range analysis
# ---------------------------------------------------------------------------

def _week52_signal(
    cmp: Dict[str, Any],
    high: Dict[str, Any],
    low: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Determine CMP position within the 52-week range.

    Formula:

        position = (CMP - low) / (high - low) * 100

    Signals:

        <25%       NEAR_52W_LOW
        25-75%     MID_RANGE
        >75%       NEAR_52W_HIGH
    """

    cmp_value = cmp["value"]
    high_value = high["value"]
    low_value = low["value"]

    if (
        cmp_value is None
        or high_value is None
        or low_value is None
        or high_value <= low_value
    ):
        return {
            "signal": "UNAVAILABLE",
            "score": None,
            "cmp": cmp_value,
            "high": high_value,
            "low": low_value,
            "position_pct": None,
            "provenance": high["provenance"],
        }

    position_pct = round(
        ((cmp_value - low_value) /
         (high_value - low_value)) * 100,
        2,
    )

    if position_pct < WEEK52_LOW_ZONE:
        signal = "NEAR_52W_LOW"
        score = 40
    elif position_pct > WEEK52_HIGH_ZONE:
        signal = "NEAR_52W_HIGH"
        score = 70
    else:
        signal = "MID_RANGE"
        score = 60

    return {
        "signal": signal,
        "score": score,
        "cmp": cmp_value,
        "high": high_value,
        "low": low_value,
        "position_pct": position_pct,
        "provenance": high["provenance"],
    }


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def analyze_technicals(
    research_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Analyze technical indicators from canonical ResearchResult v1.
    """

    technicals = research_result.get("technicals") or {}

    # -----------------------------------------------------------------------
    # Read facts
    # -----------------------------------------------------------------------

    cmp = _fact(technicals, "cmp")

    dma_50 = _fact(
        technicals,
        "dma_50",
    )

    dma_200 = _fact(
        technicals,
        "dma_200",
    )

    above_50_dma = _fact(
        technicals,
        "above_50_dma",
    )

    above_200_dma = _fact(
        technicals,
        "above_200_dma",
    )

    rsi_14 = _fact(
        technicals,
        "rsi_14",
    )

    volume = _fact(
        technicals,
        "volume",
    )

    avg_volume_1w = _fact(
        technicals,
        "avg_volume_1w",
    )

    avg_volume_1m = _fact(
        technicals,
        "avg_volume_1m",
    )

    volume_vs_1w_pct = _fact(
        technicals,
        "volume_vs_1w_pct",
    )

    volume_vs_1m_pct = _fact(
        technicals,
        "volume_vs_1m_pct",
    )

    volume_above_1w = _fact(
        technicals,
        "volume_above_1w",
    )

    volume_above_1m = _fact(
        technicals,
        "volume_above_1m",
    )

    volume_traction = _fact(
        technicals,
        "volume_traction",
    )

    fifty_two_week_high = _fact(
        technicals,
        "fifty_two_week_high",
    )

    fifty_two_week_low = _fact(
        technicals,
        "fifty_two_week_low",
    )

    # -----------------------------------------------------------------------
    # Analyze trend
    # -----------------------------------------------------------------------

    dma50_signal = _moving_average_signal(
        cmp,
        dma_50,
        above_50_dma,
        50,
    )

    dma200_signal = _moving_average_signal(
        cmp,
        dma_200,
        above_200_dma,
        200,
    )

    trend_score = _average([
        dma50_signal["score"],
        dma200_signal["score"],
    ])

    trend_bias = _bias(trend_score)

    # -----------------------------------------------------------------------
    # Momentum
    # -----------------------------------------------------------------------

    rsi_signal = _rsi_signal(rsi_14)

    momentum_score = rsi_signal["score"]

    momentum_bias = _bias(momentum_score)

    # -----------------------------------------------------------------------
    # Volume
    # -----------------------------------------------------------------------

    volume_signal = _volume_signal(
        volume,
        avg_volume_1w,
        avg_volume_1m,
        volume_vs_1w_pct,
        volume_vs_1m_pct,
        volume_above_1w,
        volume_above_1m,
        volume_traction,
    )

    volume_score = volume_signal["score"]

    volume_bias = _bias(volume_score)

    # -----------------------------------------------------------------------
    # 52-week range
    # -----------------------------------------------------------------------

    week52_signal = _week52_signal(
        cmp,
        fifty_two_week_high,
        fifty_two_week_low,
    )

    week52_score = week52_signal["score"]

    week52_bias = _bias(week52_score)

    # -----------------------------------------------------------------------
    # Overall technical score
    # -----------------------------------------------------------------------

    overall_score = _average([
        trend_score,
        momentum_score,
        volume_score,
        week52_score,
    ])

    available_categories = [
        score
        for score in [
            trend_score,
            momentum_score,
            volume_score,
            week52_score,
        ]
        if score is not None
    ]

    if len(available_categories) < 2:
        overall_bias = "INSUFFICIENT_DATA"
    else:
        overall_bias = _bias(overall_score)

    # -----------------------------------------------------------------------
    # Reasons
    # -----------------------------------------------------------------------

    reasons: list[str] = []
    limitations: list[str] = []

    if dma50_signal["signal"] in {
        "ABOVE",
        "NEAR_ABOVE",
    }:
        reasons.append(
            f"CMP is {dma50_signal['distance_pct']:.2f}% above "
            "the 50-DMA, supporting the shorter-term trend."
        )
    elif dma50_signal["signal"] in {
        "BELOW",
        "NEAR_BELOW",
    }:
        reasons.append(
            f"CMP is {abs(dma50_signal['distance_pct']):.2f}% below "
            "the 50-DMA, weakening the shorter-term trend."
        )
    else:
        limitations.append(
            "50-DMA relationship is unavailable."
        )

    if dma200_signal["signal"] in {
        "ABOVE",
        "NEAR_ABOVE",
    }:
        reasons.append(
            f"CMP is {dma200_signal['distance_pct']:.2f}% above "
            "the 200-DMA, supporting the longer-term trend."
        )
    elif dma200_signal["signal"] in {
        "BELOW",
        "NEAR_BELOW",
    }:
        reasons.append(
            f"CMP is {abs(dma200_signal['distance_pct']):.2f}% below "
            "the 200-DMA, weakening the longer-term trend."
        )
    else:
        limitations.append(
            "200-DMA relationship is unavailable."
        )

    if rsi_signal["signal"] == "OVERBOUGHT":
        reasons.append(
            f"RSI(14) of {rsi_14['value']:.2f} indicates "
            "overbought momentum."
        )
    elif rsi_signal["signal"] == "OVERSOLD":
        reasons.append(
            f"RSI(14) of {rsi_14['value']:.2f} indicates "
            "oversold conditions."
        )
    elif rsi_signal["signal"] == "STRONG":
        reasons.append(
            f"RSI(14) of {rsi_14['value']:.2f} indicates "
            "healthy positive momentum."
        )
    elif rsi_signal["signal"] == "NEUTRAL":
        reasons.append(
            f"RSI(14) of {rsi_14['value']:.2f} is in the neutral range."
        )
    elif rsi_signal["signal"] == "WEAK":
        reasons.append(
            f"RSI(14) of {rsi_14['value']:.2f} indicates weak momentum."
        )
    else:
        limitations.append(
            "RSI(14) is unavailable."
        )

    if volume_signal["signal"] == "STRONG_TRACTION":
        reasons.append(
            "Volume shows strong upward traction relative to "
            "the recent averages."
        )
    elif volume_signal["signal"] == "POSITIVE":
        reasons.append(
            "Current volume is above the 1-week average."
        )
    elif volume_signal["signal"] == "MIXED":
        reasons.append(
            "Volume confirmation is mixed across the 1-week and "
            "1-month averages."
        )
    elif volume_signal["signal"] == "WEAK":
        reasons.append(
            "Current volume is below the recent averages."
        )
    else:
        limitations.append(
            "Volume participation data is unavailable."
        )

    if week52_signal["signal"] == "NEAR_52W_LOW":
        reasons.append(
            f"CMP is at {week52_signal['position_pct']:.2f}% "
            "of the 52-week range, near the lower end."
        )
    elif week52_signal["signal"] == "MID_RANGE":
        reasons.append(
            f"CMP is at {week52_signal['position_pct']:.2f}% "
            "of the 52-week range, in the middle zone."
        )
    elif week52_signal["signal"] == "NEAR_52W_HIGH":
        reasons.append(
            f"CMP is at {week52_signal['position_pct']:.2f}% "
            "of the 52-week range, near the upper end."
        )
    else:
        limitations.append(
            "52-week range position is unavailable."
        )

    # -----------------------------------------------------------------------
    # Return structured intelligence
    # -----------------------------------------------------------------------

    return {
        "module": MODULE_NAME,
        "version": MODULE_VERSION,
        "symbol": research_result.get("symbol"),
        "company_name": research_result.get("company_name"),
        "overall_bias": overall_bias,
        "score": overall_score,
        "as_of_date": (
            technicals
            .get("provenance", {})
            .get("as_of_date")
        ),
        "signals": {
            "trend": {
                "bias": trend_bias,
                "score": trend_score,
                "dma_50": dma50_signal,
                "dma_200": dma200_signal,
            },
            "momentum": {
                "bias": momentum_bias,
                "score": momentum_score,
                "rsi_14": rsi_signal,
            },
            "volume": {
                "bias": volume_bias,
                "score": volume_score,
                "participation": volume_signal,
            },
            "range_position": {
                "bias": week52_bias,
                "score": week52_score,
                "fifty_two_week": week52_signal,
            },
        },
        "reasons": reasons,
        "limitations": limitations,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    """CLI entry point."""

    if len(sys.argv) != 2:
        print(
            "Usage: python intelligence/technicals.py "
            "<research-result.json>",
            file=sys.stderr,
        )
        return 1

    input_path = Path(sys.argv[1])

    if not input_path.exists():
        print(
            f"ERROR: File not found: {input_path}",
            file=sys.stderr,
        )
        return 1

    try:
        with input_path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            research_result = json.load(handle)
    except json.JSONDecodeError as exc:
        print(
            f"ERROR: Invalid JSON: {exc}",
            file=sys.stderr,
        )
        return 1

    result = analyze_technicals(
        research_result
    )

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
