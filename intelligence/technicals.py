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

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple


MODULE_NAME = "technicals"
MODULE_VERSION = "2.0"


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
    unit = raw.get("unit")

    if unit == "BOOLEAN":
        normalized_value = _boolean(value)
    elif unit in {"TEXT", "DATE"}:
        normalized_value = str(value) if value is not None else None
    else:
        normalized_value = _number(value)

    return {
        "value": normalized_value,
        "unit": unit,
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
    # Stage 2 Decision Engine & Classification
    # -----------------------------------------------------------------------

    classification, reason_codes, positive_factors, cautionary_factors, risk_flags = (
        _evaluate_classification(technicals)
    )

    key_levels = _derive_key_levels(cmp["value"], technicals)

    stage1_facts_count = sum(
        1
        for k in [
            "dma_slope_50",
            "obv_change_norm_14d",
            "clv_14_avg",
            "atr_14",
            "swing_high_20",
        ]
        if _fact(technicals, k)["value"] is not None
        and _fact(technicals, k)["status"] != "UNAVAILABLE"
    )

    history_bars_fact = _fact(technicals, "history_bars")
    history_bars_val = (
        int(history_bars_fact["value"])
        if history_bars_fact["value"] is not None
        else None
    )
    if history_bars_val is None and dma_200["value"] is not None and dma_200["status"] == "VERIFIED":
        history_bars_val = 200

    confidence = _calculate_confidence(
        classification=classification,
        history_bars=history_bars_val,
        cmp_fact=cmp,
        dma_50_fact=dma_50,
        dma_200_fact=dma_200,
        rsi_fact=rsi_14,
        volume_fact=volume,
        stage1_facts_available=stage1_facts_count,
    )

    swing_high_fact = _fact(technicals, "swing_high_20")
    pct_from_swing_high_fact = _fact(technicals, "pct_from_swing_high")
    pct_swing_high = pct_from_swing_high_fact["value"]
    if pct_swing_high is None and cmp["value"] is not None and swing_high_fact["value"] is not None and swing_high_fact["value"] > 0:
        pct_swing_high = round(((cmp["value"] - swing_high_fact["value"]) / swing_high_fact["value"]) * 100, 2)

    score = _calculate_score(
        classification=classification,
        cmp_val=cmp["value"],
        dma_50_val=dma_50["value"],
        dma_200_val=dma_200["value"],
        dma_align_val=_fact(technicals, "dma_alignment")["value"],
        dma_slope_50_val=_fact(technicals, "dma_slope_50")["value"],
        rsi_val=rsi_14["value"],
        obv_val=_fact(technicals, "obv_change_norm_14d")["value"],
        clv_avg_val=_fact(technicals, "clv_14_avg")["value"],
        high_52w_val=fifty_two_week_high["value"],
        low_52w_val=fifty_two_week_low["value"],
        pct_from_swing_high=pct_swing_high,
    )

    assessment_timestamp = datetime.now(timezone.utc).isoformat()

    # Preserve overall_bias compatibility
    if classification == "INSUFFICIENT_DATA":
        overall_bias = "INSUFFICIENT_DATA"
    elif overall_score is not None:
        overall_bias = _bias(overall_score)
    else:
        if score is not None:
            if score >= 30.0:
                overall_bias = "POSITIVE"
            elif score <= -30.0:
                overall_bias = "NEGATIVE"
            else:
                overall_bias = "MIXED"
        else:
            overall_bias = "INSUFFICIENT_DATA"

    # -----------------------------------------------------------------------
    # Return structured intelligence
    # -----------------------------------------------------------------------

    return {
        "module": MODULE_NAME,
        "version": MODULE_VERSION,
        "symbol": research_result.get("symbol"),
        "company_name": research_result.get("company_name"),
        "classification": classification,
        "score": score,
        "confidence": confidence,
        "reason_codes": reason_codes,
        "positive_factors": positive_factors,
        "cautionary_factors": cautionary_factors,
        "risk_flags": risk_flags,
        "key_levels": key_levels,
        "assessment_timestamp": assessment_timestamp,
        "overall_bias": overall_bias,
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
# Stage 2 Helper Functions
# ---------------------------------------------------------------------------

def _derive_key_levels(
    cmp_val: Optional[float],
    technicals: Dict[str, Any],
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Derive immediate deterministic support and resistance reference levels.
    Levels must come directly from data without fabricating prices.
    """
    if cmp_val is None:
        return {
            "support_reference": None,
            "resistance_reference": None,
        }

    swing_low = _fact(technicals, "swing_low_20")
    swing_high = _fact(technicals, "swing_high_20")
    dma_50 = _fact(technicals, "dma_50")
    dma_200 = _fact(technicals, "dma_200")
    high_52w = _fact(technicals, "fifty_two_week_high")
    low_52w = _fact(technicals, "fifty_two_week_low")

    # Potential supports (must be <= cmp_val)
    support_candidates: List[Dict[str, Any]] = []
    if (
        swing_low["value"] is not None
        and swing_low["status"] != "UNAVAILABLE"
        and swing_low["value"] <= cmp_val
    ):
        support_candidates.append(
            {"level": float(swing_low["value"]), "type": "SWING_LOW_20D"}
        )
    if (
        dma_50["value"] is not None
        and dma_50["status"] != "UNAVAILABLE"
        and dma_50["value"] <= cmp_val
    ):
        support_candidates.append(
            {"level": float(dma_50["value"]), "type": "DMA_50"}
        )
    if (
        dma_200["value"] is not None
        and dma_200["status"] != "UNAVAILABLE"
        and dma_200["value"] <= cmp_val
    ):
        support_candidates.append(
            {"level": float(dma_200["value"]), "type": "DMA_200"}
        )
    if (
        low_52w["value"] is not None
        and low_52w["status"] != "UNAVAILABLE"
        and low_52w["value"] <= cmp_val
    ):
        support_candidates.append(
            {"level": float(low_52w["value"]), "type": "52_WEEK_LOW"}
        )

    support_reference = (
        max(support_candidates, key=lambda x: x["level"])
        if support_candidates
        else None
    )

    # Potential resistances (must be >= cmp_val)
    resistance_candidates: List[Dict[str, Any]] = []
    if (
        swing_high["value"] is not None
        and swing_high["status"] != "UNAVAILABLE"
        and swing_high["value"] >= cmp_val
    ):
        resistance_candidates.append(
            {"level": float(swing_high["value"]), "type": "SWING_HIGH_20D"}
        )
    if (
        dma_50["value"] is not None
        and dma_50["status"] != "UNAVAILABLE"
        and dma_50["value"] >= cmp_val
    ):
        resistance_candidates.append(
            {"level": float(dma_50["value"]), "type": "DMA_50"}
        )
    if (
        dma_200["value"] is not None
        and dma_200["status"] != "UNAVAILABLE"
        and dma_200["value"] >= cmp_val
    ):
        resistance_candidates.append(
            {"level": float(dma_200["value"]), "type": "DMA_200"}
        )
    if (
        high_52w["value"] is not None
        and high_52w["status"] != "UNAVAILABLE"
        and high_52w["value"] >= cmp_val
    ):
        resistance_candidates.append(
            {"level": float(high_52w["value"]), "type": "52_WEEK_HIGH"}
        )

    resistance_reference = (
        min(resistance_candidates, key=lambda x: x["level"])
        if resistance_candidates
        else None
    )

    return {
        "support_reference": support_reference,
        "resistance_reference": resistance_reference,
    }


def _calculate_score(
    classification: str,
    cmp_val: Optional[float],
    dma_50_val: Optional[float],
    dma_200_val: Optional[float],
    dma_align_val: Optional[str],
    dma_slope_50_val: Optional[str],
    rsi_val: Optional[float],
    obv_val: Optional[float],
    clv_avg_val: Optional[float],
    high_52w_val: Optional[float],
    low_52w_val: Optional[float],
    pct_from_swing_high: Optional[float],
) -> Optional[float]:
    """
    Calculate deterministic technical score strictly bounded between -100.0 and +100.0.
    Returns None for INSUFFICIENT_DATA.
    """
    if classification == "INSUFFICIENT_DATA" or cmp_val is None:
        return None

    score = 0.0

    # 1. Trend & Structure Component (±40 points max)
    if dma_200_val is not None:
        score += 15.0 if cmp_val > dma_200_val else -15.0

    if dma_align_val == "50_DMA_ABOVE_200_DMA" or (
        dma_50_val is not None and dma_200_val is not None and dma_50_val > dma_200_val
    ):
        score += 15.0
    elif dma_align_val == "50_DMA_BELOW_200_DMA" or (
        dma_50_val is not None and dma_200_val is not None and dma_50_val < dma_200_val
    ):
        score -= 15.0

    if dma_slope_50_val == "RISING":
        score += 10.0
    elif dma_slope_50_val == "FALLING":
        score -= 10.0

    # 2. Momentum Component (±25 points max)
    if rsi_val is not None:
        if 55.0 <= rsi_val <= 68.0:
            score += 25.0
        elif 45.0 <= rsi_val < 55.0:
            score += 15.0
        elif 68.0 < rsi_val <= 72.0:
            score += 5.0
        elif rsi_val > 72.0:
            score -= 15.0
        elif 30.0 <= rsi_val < 45.0:
            score -= 15.0
        elif rsi_val < 30.0:
            score -= 20.0

    # 3. Volume Flow Component (±20 points max)
    if obv_val is not None:
        if obv_val > 0.10:
            score += 10.0
        elif obv_val < -0.10:
            score -= 10.0

    if clv_avg_val is not None:
        if clv_avg_val > 0.10:
            score += 10.0
        elif clv_avg_val < -0.10:
            score -= 10.0

    # 4. Range & Resistance Runway Component (±15 points max)
    if high_52w_val is not None and low_52w_val is not None and high_52w_val > low_52w_val:
        pos_pct = ((cmp_val - low_52w_val) / (high_52w_val - low_52w_val)) * 100.0
        if pos_pct > 75.0:
            score += 10.0
        elif pos_pct < 25.0:
            score -= 10.0

    if pct_from_swing_high is not None:
        if -1.5 <= pct_from_swing_high <= 0.0:
            score -= 5.0
        else:
            score += 5.0

    clamped = max(-100.0, min(100.0, score))
    return round(clamped, 2)


def _calculate_confidence(
    classification: str,
    history_bars: Optional[int],
    cmp_fact: Dict[str, Any],
    dma_50_fact: Dict[str, Any],
    dma_200_fact: Dict[str, Any],
    rsi_fact: Dict[str, Any],
    volume_fact: Dict[str, Any],
    stage1_facts_available: int,
) -> str:
    """
    Derive deterministic confidence based on evidence completeness.
    """
    if classification == "INSUFFICIENT_DATA":
        return "LOW"

    if (
        history_bars is not None
        and history_bars >= 200
        and cmp_fact["value"] is not None
        and dma_50_fact["value"] is not None
        and dma_200_fact["value"] is not None
        and rsi_fact["value"] is not None
        and volume_fact["value"] is not None
        and stage1_facts_available >= 4
    ):
        return "HIGH"

    return "MEDIUM"


def _evaluate_classification(
    technicals: Dict[str, Any],
) -> Tuple[str, List[str], List[str], List[str], List[str]]:
    """
    Evaluate deterministic classification according to strict precedence:
    1. INSUFFICIENT_DATA
    2. REDUCE_SELL_CANDIDATE
    3. AVOID_NEW_ENTRY
    4. BUY_CANDIDATE
    5. WAIT_AND_WATCH

    Returns: (classification, reason_codes, positive_factors, cautionary_factors, risk_flags)
    """
    cmp_fact = _fact(technicals, "cmp")
    dma_50_fact = _fact(technicals, "dma_50")
    dma_200_fact = _fact(technicals, "dma_200")
    history_bars_fact = _fact(technicals, "history_bars")

    history_bars = (
        int(history_bars_fact["value"])
        if history_bars_fact["value"] is not None
        else None
    )
    if history_bars is None and dma_200_fact["value"] is not None and dma_200_fact["status"] == "VERIFIED":
        history_bars = 200

    cmp_val = cmp_fact["value"]
    dma_50_val = dma_50_fact["value"]
    dma_200_val = dma_200_fact["value"]

    # -----------------------------------------------------------------------
    # Rule 1 — INSUFFICIENT_DATA
    # -----------------------------------------------------------------------
    rule1_reasons = []
    if history_bars is None or history_bars < 200:
        rule1_reasons.append("INSUFFICIENT_HISTORY_BARS")
    if cmp_val is None or cmp_fact["status"] == "UNAVAILABLE":
        rule1_reasons.append("CRITICAL_METRIC_UNAVAILABLE_CMP")
    if dma_50_val is None or dma_50_fact["status"] == "UNAVAILABLE":
        rule1_reasons.append("CRITICAL_METRIC_UNAVAILABLE_DMA_50")

    if rule1_reasons:
        return (
            "INSUFFICIENT_DATA",
            rule1_reasons,
            [],
            [
                f"Trading history or critical metrics are insufficient (bars: {history_bars}, CMP: {cmp_val}, 50-DMA: {dma_50_val}) to form a reliable technical assessment."
            ],
            ["INSUFFICIENT_DATA", "INSUFFICIENT_HISTORY"],
        )

    # Extract Stage 1 facts
    obv_fact = _fact(technicals, "obv_change_norm_14d")
    crossover_type_fact = _fact(technicals, "last_crossover_type")
    crossover_days_fact = _fact(technicals, "days_since_dma_crossover")
    dma_slope_50_fact = _fact(technicals, "dma_slope_50")
    volume_vs_20d_fact = _fact(technicals, "volume_vs_20d_pct")
    clv_fact = _fact(technicals, "clv")
    clv_14_avg_fact = _fact(technicals, "clv_14_avg")
    rsi_fact = _fact(technicals, "rsi_14")
    pct_from_50_dma_fact = _fact(technicals, "pct_from_50_dma")
    swing_high_fact = _fact(technicals, "swing_high_20")
    pct_from_swing_high_fact = _fact(technicals, "pct_from_swing_high")
    swing_high_conf_fact = _fact(technicals, "swing_high_confirmation_date")
    high_52w_fact = _fact(technicals, "fifty_two_week_high")
    pct_from_52w_high_fact = _fact(technicals, "pct_from_52w_high")
    close_below_prev_fact = _fact(technicals, "close_below_prev_close")

    obv_val = obv_fact["value"]
    crossover_type = crossover_type_fact["value"]
    crossover_days = (
        int(crossover_days_fact["value"])
        if crossover_days_fact["value"] is not None
        else None
    )
    dma_slope_50 = dma_slope_50_fact["value"]
    vol_vs_20d = volume_vs_20d_fact["value"]
    clv_val = clv_fact["value"]
    clv_14_avg = clv_14_avg_fact["value"]
    rsi_val = rsi_fact["value"]

    pct_from_50 = pct_from_50_dma_fact["value"]
    if pct_from_50 is None and cmp_val is not None and dma_50_val is not None and dma_50_val > 0:
        pct_from_50 = round(((cmp_val - dma_50_val) / dma_50_val) * 100, 2)

    swing_high_val = swing_high_fact["value"]
    pct_from_swing_high = pct_from_swing_high_fact["value"]
    if pct_from_swing_high is None and cmp_val is not None and swing_high_val is not None and swing_high_val > 0:
        pct_from_swing_high = round(((cmp_val - swing_high_val) / swing_high_val) * 100, 2)

    high_52w_val = high_52w_fact["value"]
    pct_from_52w_high = pct_from_52w_high_fact["value"]
    if pct_from_52w_high is None and cmp_val is not None and high_52w_val is not None and high_52w_val > 0:
        pct_from_52w_high = round(((cmp_val - high_52w_val) / high_52w_val) * 100, 2)

    close_below_prev = close_below_prev_fact["value"]

    # -----------------------------------------------------------------------
    # Rule 2 — REDUCE_SELL_CANDIDATE
    # -----------------------------------------------------------------------
    cond_2a = (
        dma_200_val is not None
        and cmp_val < dma_200_val
        and obv_val is not None
        and obv_val < -0.20
    )

    cond_2b = (
        crossover_type == "DEATH_CROSS"
        and crossover_days is not None
        and crossover_days <= 40
        and dma_slope_50 == "FALLING"
    )

    cond_2c = (
        vol_vs_20d is not None
        and vol_vs_20d > 20.0
        and close_below_prev is True
        and clv_val is not None
        and clv_val < -0.50
        and cmp_val < dma_50_val
    )

    if cond_2a or cond_2b or cond_2c:
        r2_reasons: List[str] = []
        r2_cautionary: List[str] = []
        r2_flags: List[str] = []

        if cond_2a:
            r2_reasons.append("REDUCE_BREAKDOWN_BELOW_200_DMA_AND_OBV_DISTRIBUTION")
            r2_cautionary.append(
                f"Price breakdown: CMP ({cmp_val:.2f}) is below the 200-DMA ({dma_200_val:.2f}) with negative price/volume-flow momentum (normalized 14-session OBV change of {obv_val:.2f} < -0.20)."
            )
            r2_flags.append("BREAKDOWN_BELOW_200_DMA")
            r2_flags.append("VOLUME_FLOW_DISTRIBUTION")

        if cond_2b:
            r2_reasons.append("REDUCE_RECENT_DEATH_CROSS_FALLING_50_DMA")
            r2_cautionary.append(
                f"Severely deteriorating trend: Active Death Cross occurred {crossover_days} sessions ago with a falling 50-DMA trendline."
            )
            r2_flags.append("DEATH_CROSS_ACTIVE")
            r2_flags.append("FALLING_50_DMA")

        if cond_2c:
            r2_reasons.append("REDUCE_SEVERE_DISTRIBUTION_HIGH_VOLUME_BELOW_50_DMA")
            r2_cautionary.append(
                f"Severe distribution signal: Elevated volume ({vol_vs_20d:.1f}% above 20d average) on a down session with weak close location (CLV {clv_val:.2f} < -0.50) while trading below 50-DMA."
            )
            r2_flags.append("SEVERE_DISTRIBUTION_VOLUME")
            r2_flags.append("BELOW_50_DMA")

        r2_cautionary.append(
            "Evidence reflects observed price/volume-flow signals. This assessment indicates elevated structural downside risk; it is not an investment guarantee."
        )

        return ("REDUCE_SELL_CANDIDATE", r2_reasons, [], r2_cautionary, r2_flags)

    # -----------------------------------------------------------------------
    # Rule 3 — AVOID_NEW_ENTRY
    # -----------------------------------------------------------------------
    cond_3a = (
        dma_200_val is not None
        and cmp_val < dma_50_val
        and cmp_val < dma_200_val
    )

    cond_3b_extended = pct_from_50 is not None and pct_from_50 > 15.0
    cond_3b_rsi = rsi_val is not None and rsi_val > 72.0
    cond_3b = cond_3b_extended or cond_3b_rsi

    swing_high_confirmed = (
        swing_high_val is not None
        and swing_high_fact["status"] != "UNAVAILABLE"
        and swing_high_conf_fact["value"] is not None
        and swing_high_conf_fact["status"] != "UNAVAILABLE"
    )

    near_swing_high = (
        swing_high_confirmed
        and pct_from_swing_high is not None
        and -3.0 <= pct_from_swing_high <= 0.0
    )

    near_52w_high = (
        high_52w_val is not None
        and high_52w_fact["status"] != "UNAVAILABLE"
        and pct_from_52w_high is not None
        and -3.0 <= pct_from_52w_high <= 0.0
    )

    cond_3c_volume_outflow = (
        obv_val is not None
        and obv_val < -0.10
        and clv_14_avg is not None
        and clv_14_avg < 0.0
    )

    cond_3c = (near_swing_high or near_52w_high) and cond_3c_volume_outflow

    if cond_3a or cond_3b or cond_3c:
        r3_reasons: List[str] = []
        r3_cautionary: List[str] = []
        r3_flags: List[str] = []

        if cond_3a:
            r3_reasons.append("AVOID_CMP_BELOW_50_AND_200_DMA")
            r3_cautionary.append(
                f"Negative trend alignment: CMP ({cmp_val:.2f}) is below both the 50-DMA ({dma_50_val:.2f}) and 200-DMA ({dma_200_val:.2f})."
            )
            r3_flags.append("BELOW_50_DMA")
            r3_flags.append("BELOW_200_DMA")

        if cond_3b_extended:
            r3_reasons.append("AVOID_EXTENDED_ABOVE_50_DMA")
            r3_cautionary.append(
                f"Extended price structure: CMP is {pct_from_50:.2f}% above the 50-DMA (> 15% threshold), creating elevated mean-reversion risk."
            )
            r3_flags.append("EXTENDED_ABOVE_50_DMA")

        if cond_3b_rsi:
            r3_reasons.append("AVOID_OVERBOUGHT_RSI")
            r3_cautionary.append(
                f"Overbought momentum: RSI(14) of {rsi_val:.2f} is above 72.0, indicating stretched short-term conditions."
            )
            r3_flags.append("OVERBOUGHT_RSI")

        if cond_3c:
            r3_reasons.append("AVOID_RESISTANCE_PROXIMITY_WITH_VOLUME_OUTFLOW")
            res_desc = (
                f"confirmed swing high ({swing_high_val:.2f})"
                if near_swing_high
                else f"52-week high ({high_52w_val:.2f})"
            )
            r3_cautionary.append(
                f"Resistance proximity with price/volume-flow outflows: CMP is within 3% of {res_desc} while normalized OBV change ({obv_val:.2f}) is < -0.10 and 14d CLV average ({clv_14_avg:.2f}) is negative."
            )
            r3_flags.append("OVERHEAD_RESISTANCE_NEAR")
            r3_flags.append("VOLUME_OUTFLOW_DETECTED")

        r3_cautionary.append(
            "AVOID_NEW_ENTRY indicates unfavorable risk-reward for initiating new long positions; it is not an instruction to sell existing long-term positions."
        )

        return ("AVOID_NEW_ENTRY", r3_reasons, [], r3_cautionary, r3_flags)

    # -----------------------------------------------------------------------
    # Rule 4 — BUY_CANDIDATE
    # -----------------------------------------------------------------------
    # Condition 1: CMP > 200-DMA and 50-DMA > 200-DMA
    cond_4_1 = (
        dma_200_val is not None
        and cmp_val > dma_200_val
        and dma_50_val > dma_200_val
    )

    # Condition 2: CMP >= 50-DMA or no more than 2% below it with RISING 50-DMA slope
    cond_4_2 = False
    if pct_from_50 is not None:
        if pct_from_50 >= 0.0:
            cond_4_2 = True
        elif -2.0 <= pct_from_50 < 0.0 and dma_slope_50 == "RISING":
            cond_4_2 = True

    # Condition 3: CMP <= 10% above 50-DMA
    cond_4_3 = pct_from_50 is not None and pct_from_50 <= 10.0

    # Condition 4: RSI(14) between 45 and 68 inclusive
    cond_4_4 = rsi_val is not None and 45.0 <= rsi_val <= 68.0

    # Condition 5: Normalized OBV change > 0.10 or 14d CLV average > 0.10
    cond_4_5 = (
        (obv_val is not None and obv_val > 0.10)
        or (clv_14_avg is not None and clv_14_avg > 0.10)
    )

    # Condition 6: Not within 1.5% below confirmed swing high
    # If required resistance metric is unavailable, do not assume clearance
    cond_4_6 = False
    if swing_high_confirmed and pct_from_swing_high is not None:
        if not (-1.5 <= pct_from_swing_high <= 0.0):
            cond_4_6 = True

    if cond_4_1 and cond_4_2 and cond_4_3 and cond_4_4 and cond_4_5 and cond_4_6:
        r4_reasons = [
            "BUY_TREND_ALIGNMENT_CONFIRMED",
            "BUY_HEALTHY_MOMENTUM_RSI",
            "BUY_VOLUME_FLOW_SUPPORT",
            "BUY_CLEAR_RESISTANCE_RUNWAY",
        ]
        if pct_from_50 is not None and pct_from_50 < 0.0:
            r4_reasons.append("BUY_PULLBACK_SUPPORT_50_DMA")

        r4_positive = [
            f"Bullish trend structure: CMP ({cmp_val:.2f}) is above 200-DMA ({dma_200_val:.2f}) and 50-DMA ({dma_50_val:.2f}) is aligned above 200-DMA.",
            f"Controlled entry zone: CMP is {pct_from_50:+.2f}% from the 50-DMA (within optimal band).",
            f"Healthy momentum: RSI(14) is {rsi_val:.2f} (within constructive 45–68 band).",
            f"Supportive price/volume-flow: normalized OBV change ({obv_val}) / CLV 14d average ({clv_14_avg}) indicates net accumulation.",
            f"Resistance clearance: CMP ({cmp_val:.2f}) maintains runway below confirmed swing high ({swing_high_val:.2f}).",
        ]

        r4_cautionary = [
            "BUY_CANDIDATE identifies a favorable technical pattern based on historical metrics; it does not guarantee profitable returns or eliminate risk of capital loss.",
        ]

        return ("BUY_CANDIDATE", r4_reasons, r4_positive, r4_cautionary, [])

    # -----------------------------------------------------------------------
    # Rule 5 — WAIT_AND_WATCH (Fallback)
    # -----------------------------------------------------------------------
    r5_reasons = []
    r5_positive = []
    r5_cautionary = []
    r5_flags = []

    if dma_200_val is not None and cmp_val > dma_200_val:
        r5_positive.append(f"CMP ({cmp_val:.2f}) is above the 200-DMA ({dma_200_val:.2f}), preserving macro trend support.")
    if dma_50_val is not None and cmp_val > dma_50_val:
        r5_positive.append(f"CMP is above the 50-DMA ({dma_50_val:.2f}).")
    if rsi_val is not None and 45.0 <= rsi_val <= 68.0:
        r5_positive.append(f"RSI(14) of {rsi_val:.2f} is in constructive neutral range.")

    if cond_4_1:
        r5_reasons.append("WAIT_INCOMPLETE_BUY_CRITERIA")
        if not cond_4_2:
            r5_cautionary.append(f"Price is more than 2% below the 50-DMA or 50-DMA slope ({dma_slope_50}) is not rising.")
        if not cond_4_3:
            r5_cautionary.append(f"Price is {pct_from_50:.2f}% above the 50-DMA (exceeds 10% threshold).")
        if not cond_4_4:
            r5_cautionary.append(f"RSI(14) of {rsi_val} is outside the required 45–68 band.")
        if not cond_4_5:
            r5_cautionary.append("Price/volume-flow does not show positive accumulation (both OBV change and 14d CLV avg <= 0.10).")
        if not cond_4_6:
            if not swing_high_confirmed:
                r5_cautionary.append("Confirmed resistance metric is unavailable; resistance clearance cannot be verified.")
            else:
                r5_cautionary.append(f"CMP is within 1.5% below confirmed swing high ({swing_high_val:.2f}), facing immediate resistance headwind.")
    else:
        r5_reasons.append("WAIT_CONSOLIDATION_OR_MIXED_SIGNALS")
        r5_cautionary.append("Trend signals are mixed or consolidating; neither clear breakdown nor complete buy setup is present.")

    return ("WAIT_AND_WATCH", r5_reasons, r5_positive, r5_cautionary, r5_flags)


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
