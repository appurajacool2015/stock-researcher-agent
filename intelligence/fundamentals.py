#!/usr/bin/env python3

"""
Fundamentals Intelligence Module

Purpose
-------
Interpret fundamental facts from the canonical ResearchResult v1.

Architecture principle
----------------------
Adapters collect facts.
Intelligence interprets facts.

This module:
- does not scrape websites
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


MODULE_NAME = "fundamentals"
MODULE_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Growth
GROWTH_STRONG = 15.0
GROWTH_GOOD = 10.0
GROWTH_MODERATE = 5.0

# Profitability
ROE_STRONG = 20.0
ROE_GOOD = 15.0
ROE_MODERATE = 10.0

ROCE_STRONG = 20.0
ROCE_GOOD = 15.0
ROCE_MODERATE = 10.0

# Valuation
#
# These are broad heuristic bands only.
# They must eventually be interpreted using:
# - sector
# - peers
# - historical valuation
# - growth
PE_LOW = 15.0
PE_MODERATE = 25.0
PE_HIGH = 40.0

PB_LOW = 3.0
PB_MODERATE = 6.0
PB_HIGH = 10.0

# Leverage
DEBT_TO_EQUITY_LOW = 0.5
DEBT_TO_EQUITY_MODERATE = 1.0
DEBT_TO_EQUITY_HIGH = 2.0


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


def _fact(
    fundamentals: Dict[str, Any],
    key: str,
) -> Dict[str, Any]:
    """
    Read a canonical ResearchResult v1 fact.

    Expected structure:

        "roe": {
            "value": 51.8,
            "unit": "PERCENT",
            "status": "VERIFIED",
            "provenance": {...}
        }

    Returns a normalized internal representation while retaining
    source metadata.
    """

    raw = fundamentals.get(key)

    if not isinstance(raw, dict):
        return {
            "value": None,
            "unit": None,
            "status": "UNAVAILABLE",
            "provenance": None,
            "notes": None,
        }

    return {
        "value": _number(raw.get("value")),
        "unit": raw.get("unit"),
        "status": raw.get("status", "UNAVAILABLE"),
        "provenance": raw.get("provenance"),
        "notes": raw.get("notes"),
    }


def _higher_is_better(
    fact: Dict[str, Any],
    strong: float,
    good: float,
    moderate: float,
) -> Dict[str, Any]:
    """Classify a metric where higher values are generally better."""

    value = fact["value"]

    if value is None:
        signal = "UNAVAILABLE"
        score = None
    elif value >= strong:
        signal = "STRONG"
        score = 100
    elif value >= good:
        signal = "GOOD"
        score = 80
    elif value >= moderate:
        signal = "MODERATE"
        score = 60
    else:
        signal = "WEAK"
        score = 30

    return {
        "value": value,
        "unit": fact["unit"],
        "source_status": fact["status"],
        "signal": signal,
        "score": score,
        "provenance": fact["provenance"],
        "notes": fact["notes"],
    }


def _valuation(
    fact: Dict[str, Any],
    low: float,
    moderate: float,
    high: float,
) -> Dict[str, Any]:
    """
    Classify valuation multiple.

    Lower is treated as more favourable only within this heuristic.

    This is NOT an absolute cheap/expensive judgement.
    """

    value = fact["value"]

    if value is None:
        signal = "UNAVAILABLE"
        score = None
    elif value <= low:
        signal = "LOW"
        score = 85
    elif value <= moderate:
        signal = "MODERATE"
        score = 65
    elif value <= high:
        signal = "HIGH"
        score = 40
    else:
        signal = "VERY_HIGH"
        score = 20

    return {
        "value": value,
        "unit": fact["unit"],
        "source_status": fact["status"],
        "signal": signal,
        "score": score,
        "provenance": fact["provenance"],
        "notes": fact["notes"],
        "interpretation": (
            "Heuristic valuation band only. Requires sector, peer, "
            "historical and growth comparison."
        ),
    }


def _leverage(fact: Dict[str, Any]) -> Dict[str, Any]:
    """Classify debt-to-equity."""

    value = fact["value"]

    if value is None:
        signal = "UNAVAILABLE"
        score = None
    elif value <= DEBT_TO_EQUITY_LOW:
        signal = "LOW"
        score = 90
    elif value <= DEBT_TO_EQUITY_MODERATE:
        signal = "MODERATE"
        score = 65
    elif value <= DEBT_TO_EQUITY_HIGH:
        signal = "HIGH"
        score = 40
    else:
        signal = "VERY_HIGH"
        score = 20

    return {
        "value": value,
        "unit": fact["unit"],
        "source_status": fact["status"],
        "signal": signal,
        "score": score,
        "provenance": fact["provenance"],
        "notes": fact["notes"],
    }


def _average(values: list[Optional[int]]) -> Optional[float]:
    """Average available scores."""

    available = [
        value for value in values
        if value is not None
    ]

    if not available:
        return None

    return round(sum(available) / len(available), 2)


def _bias(score: Optional[float]) -> str:
    """Translate a category score into an analytical bias."""

    if score is None:
        return "INSUFFICIENT_DATA"

    if score >= 75:
        return "POSITIVE"

    if score >= 50:
        return "MIXED"

    return "NEGATIVE"


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def analyze_fundamentals(
    research_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Analyze fundamentals from canonical ResearchResult v1.
    """

    fundamentals = research_result.get("fundamentals") or {}

    # -----------------------------------------------------------------------
    # Read canonical facts
    # -----------------------------------------------------------------------

    pe = _fact(fundamentals, "pe_ratio")
    pb = _fact(fundamentals, "pb_ratio")
    roe = _fact(fundamentals, "roe")
    roce = _fact(fundamentals, "roce")
    debt_to_equity = _fact(
        fundamentals,
        "debt_to_equity",
    )
    sales_growth = _fact(
        fundamentals,
        "sales_growth_3y_cagr",
    )
    profit_growth = _fact(
        fundamentals,
        "profit_growth_3y_cagr",
    )
    market_cap = _fact(
        fundamentals,
        "market_cap",
    )

    # -----------------------------------------------------------------------
    # Analyze categories
    # -----------------------------------------------------------------------

    roe_signal = _higher_is_better(
        roe,
        ROE_STRONG,
        ROE_GOOD,
        ROE_MODERATE,
    )

    roce_signal = _higher_is_better(
        roce,
        ROCE_STRONG,
        ROCE_GOOD,
        ROCE_MODERATE,
    )

    sales_growth_signal = _higher_is_better(
        sales_growth,
        GROWTH_STRONG,
        GROWTH_GOOD,
        GROWTH_MODERATE,
    )

    profit_growth_signal = _higher_is_better(
        profit_growth,
        GROWTH_STRONG,
        GROWTH_GOOD,
        GROWTH_MODERATE,
    )

    pe_signal = _valuation(
        pe,
        PE_LOW,
        PE_MODERATE,
        PE_HIGH,
    )

    pb_signal = _valuation(
        pb,
        PB_LOW,
        PB_MODERATE,
        PB_HIGH,
    )

    leverage_signal = _leverage(debt_to_equity)

    # -----------------------------------------------------------------------
    # Category scores
    # -----------------------------------------------------------------------

    profitability_score = _average([
        roe_signal["score"],
        roce_signal["score"],
    ])

    growth_score = _average([
        sales_growth_signal["score"],
        profit_growth_signal["score"],
    ])

    valuation_score = _average([
        pe_signal["score"],
        pb_signal["score"],
    ])

    leverage_score = leverage_signal["score"]

    overall_score = _average([
        profitability_score,
        growth_score,
        valuation_score,
        leverage_score,
    ])

    # -----------------------------------------------------------------------
    # Category biases
    # -----------------------------------------------------------------------

    profitability_bias = _bias(profitability_score)
    growth_bias = _bias(growth_score)
    valuation_bias = _bias(valuation_score)
    leverage_bias = _bias(leverage_score)

    available_categories = [
        score
        for score in [
            profitability_score,
            growth_score,
            valuation_score,
            leverage_score,
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

    if roe_signal["signal"] == "STRONG":
        reasons.append(
            f"ROE of {roe['value']:.2f}% is strong under the "
            "fundamental heuristic."
        )
    elif roe_signal["signal"] == "GOOD":
        reasons.append(
            f"ROE of {roe['value']:.2f}% is good."
        )
    elif roe_signal["signal"] == "MODERATE":
        reasons.append(
            f"ROE of {roe['value']:.2f}% is moderate."
        )
    elif roe_signal["signal"] == "WEAK":
        reasons.append(
            f"ROE of {roe['value']:.2f}% is weak."
        )
    else:
        limitations.append("ROE is unavailable.")

    if roce_signal["signal"] == "STRONG":
        reasons.append(
            f"ROCE of {roce['value']:.2f}% is strong under the "
            "fundamental heuristic."
        )
    elif roce_signal["signal"] == "GOOD":
        reasons.append(
            f"ROCE of {roce['value']:.2f}% is good."
        )
    elif roce_signal["signal"] == "MODERATE":
        reasons.append(
            f"ROCE of {roce['value']:.2f}% is moderate."
        )
    elif roce_signal["signal"] == "WEAK":
        reasons.append(
            f"ROCE of {roce['value']:.2f}% is weak."
        )
    else:
        limitations.append("ROCE is unavailable.")

    if sales_growth_signal["signal"] == "STRONG":
        reasons.append(
            f"3-year sales CAGR of {sales_growth['value']:.2f}% "
            "is strong."
        )
    elif sales_growth_signal["signal"] == "GOOD":
        reasons.append(
            f"3-year sales CAGR of {sales_growth['value']:.2f}% "
            "is good."
        )
    elif sales_growth_signal["signal"] == "MODERATE":
        reasons.append(
            f"3-year sales CAGR of {sales_growth['value']:.2f}% "
            "is moderate."
        )
    elif sales_growth_signal["signal"] == "WEAK":
        reasons.append(
            f"3-year sales CAGR of {sales_growth['value']:.2f}% "
            "is weak."
        )
    else:
        limitations.append(
            "3-year sales CAGR is unavailable."
        )

    if profit_growth_signal["signal"] == "STRONG":
        reasons.append(
            f"3-year profit CAGR of {profit_growth['value']:.2f}% "
            "is strong."
        )
    elif profit_growth_signal["signal"] == "GOOD":
        reasons.append(
            f"3-year profit CAGR of {profit_growth['value']:.2f}% "
            "is good."
        )
    elif profit_growth_signal["signal"] == "MODERATE":
        reasons.append(
            f"3-year profit CAGR of {profit_growth['value']:.2f}% "
            "is moderate."
        )
    elif profit_growth_signal["signal"] == "WEAK":
        reasons.append(
            f"3-year profit CAGR of {profit_growth['value']:.2f}% "
            "is weak."
        )
    else:
        limitations.append(
            "3-year profit CAGR is unavailable."
        )

    if pe_signal["signal"] == "LOW":
        reasons.append(
            f"P/E of {pe['value']:.2f} is in the low heuristic band."
        )
    elif pe_signal["signal"] == "MODERATE":
        reasons.append(
            f"P/E of {pe['value']:.2f} is in the moderate heuristic band."
        )
    elif pe_signal["signal"] in {"HIGH", "VERY_HIGH"}:
        reasons.append(
            f"P/E of {pe['value']:.2f} is elevated under the "
            "heuristic valuation bands."
        )
    else:
        limitations.append("P/E is unavailable.")

    if pb_signal["signal"] == "LOW":
        reasons.append(
            f"P/B of {pb['value']:.2f} is in the low heuristic band."
        )
    elif pb_signal["signal"] == "MODERATE":
        reasons.append(
            f"P/B of {pb['value']:.2f} is in the moderate heuristic band."
        )
    elif pb_signal["signal"] in {"HIGH", "VERY_HIGH"}:
        reasons.append(
            f"P/B of {pb['value']:.2f} is elevated under the "
            "heuristic valuation bands."
        )
    else:
        limitations.append("P/B is unavailable.")

    if leverage_signal["signal"] == "LOW":
        reasons.append(
            f"Debt-to-equity of {debt_to_equity['value']:.2f} "
            "indicates low leverage."
        )
    elif leverage_signal["signal"] == "MODERATE":
        reasons.append(
            f"Debt-to-equity of {debt_to_equity['value']:.2f} "
            "indicates moderate leverage."
        )
    elif leverage_signal["signal"] in {"HIGH", "VERY_HIGH"}:
        reasons.append(
            f"Debt-to-equity of {debt_to_equity['value']:.2f} "
            "indicates elevated leverage."
        )
    else:
        limitations.append(
            "Debt-to-equity is unavailable."
        )

    # -----------------------------------------------------------------------
    # Return intelligence object
    # -----------------------------------------------------------------------

    return {
        "module": MODULE_NAME,
        "version": MODULE_VERSION,
        "symbol": research_result.get("symbol"),
        "company_name": research_result.get("company_name"),
        "overall_bias": overall_bias,
        "score": overall_score,
        "as_of_date": (
            fundamentals
            .get("provenance", {})
            .get("as_of_date")
        ),
        "signals": {
            "profitability": {
                "bias": profitability_bias,
                "score": profitability_score,
                "roe": roe_signal,
                "roce": roce_signal,
            },
            "growth": {
                "bias": growth_bias,
                "score": growth_score,
                "sales_growth_3y_cagr": sales_growth_signal,
                "profit_growth_3y_cagr": profit_growth_signal,
            },
            "valuation": {
                "bias": valuation_bias,
                "score": valuation_score,
                "pe_ratio": pe_signal,
                "pb_ratio": pb_signal,
            },
            "leverage": {
                "bias": leverage_bias,
                "score": leverage_score,
                "debt_to_equity": leverage_signal,
            },
        },
        "market_cap": {
            "value": market_cap["value"],
            "unit": market_cap["unit"],
            "source_status": market_cap["status"],
            "provenance": market_cap["provenance"],
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
            "Usage: python intelligence/fundamentals.py "
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
        with input_path.open("r", encoding="utf-8") as handle:
            research_result = json.load(handle)
    except json.JSONDecodeError as exc:
        print(
            f"ERROR: Invalid JSON: {exc}",
            file=sys.stderr,
        )
        return 1

    result = analyze_fundamentals(research_result)

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
