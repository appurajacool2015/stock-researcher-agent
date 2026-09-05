#!/usr/bin/env python3

"""
Institutional Intelligence Module

Purpose
-------
Interpret institutional ownership facts from the canonical
ResearchResult v1.

Architecture principle
----------------------
Adapters collect facts.
Intelligence interprets facts.

Important interpretation rule
-----------------------------
A change in reported ownership percentage does NOT prove that an
institutional investor bought or sold shares in the market.

For example:

    FII holding change = -0.59 percentage points

means reported FII ownership decreased by 0.59 percentage points
between the available reporting periods.

It should NOT automatically be described as:

    "FIIs sold 0.59% of the shares."

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


MODULE_NAME = "institutional"
MODULE_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Ownership change is measured in percentage points.
#
# We deliberately use relatively small thresholds because institutional
# ownership changes are often meaningful even when they are less than 1 pp.

CHANGE_STRONG = 1.0
CHANGE_MODERATE = 0.25
CHANGE_STABLE = 0.10


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
    institutional: Dict[str, Any],
    key: str,
) -> Dict[str, Any]:
    """
    Read a canonical ResearchResult v1 institutional fact.
    """

    raw = institutional.get(key)

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
        "status": raw.get(
            "status",
            "UNAVAILABLE",
        ),
        "provenance": raw.get("provenance"),
        "notes": raw.get("notes"),
    }


def _change_signal(
    fact: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Interpret a quarter-on-quarter ownership change.

    Positive change:
        ownership increased

    Negative change:
        ownership decreased

    Near zero:
        ownership stable

    Important:
        This is a reported ownership change, not direct evidence
        of market buying/selling activity.
    """

    value = fact["value"]

    if value is None:
        return {
            "signal": "UNAVAILABLE",
            "score": None,
            "direction": "UNAVAILABLE",
            "change_pp": None,
            "unit": fact["unit"],
            "source_status": fact["status"],
            "provenance": fact["provenance"],
            "notes": fact["notes"],
        }

    if value >= CHANGE_STRONG:
        signal = "STRONG_INCREASE"
        direction = "INCREASED"
        score = 100

    elif value >= CHANGE_MODERATE:
        signal = "INCREASE"
        direction = "INCREASED"
        score = 80

    elif value > CHANGE_STABLE:
        signal = "SLIGHT_INCREASE"
        direction = "INCREASED"
        score = 70

    elif value >= -CHANGE_STABLE:
        signal = "STABLE"
        direction = "STABLE"
        score = 60

    elif value > -CHANGE_MODERATE:
        signal = "SLIGHT_DECREASE"
        direction = "DECREASED"
        score = 50

    elif value > -CHANGE_STRONG:
        signal = "DECREASE"
        direction = "DECREASED"
        score = 35

    else:
        signal = "STRONG_DECREASE"
        direction = "DECREASED"
        score = 20

    return {
        "signal": signal,
        "score": score,
        "direction": direction,
        "change_pp": value,
        "unit": fact["unit"],
        "source_status": fact["status"],
        "provenance": fact["provenance"],
        "notes": fact["notes"],
    }


def _holding_signal(
    fact: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Preserve the current ownership percentage.

    We intentionally do not classify a holding percentage itself as
    positive or negative because the appropriate level depends on the
    company, sector, shareholder structure and historical context.
    """

    return {
        "value": fact["value"],
        "unit": fact["unit"],
        "source_status": fact["status"],
        "provenance": fact["provenance"],
        "notes": fact["notes"],
    }


def _pledge_signal(
    fact: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Interpret promoter pledge percentage.

    Lower promoter pledge is generally preferable, but this module
    intentionally uses only simple deterministic bands.

        0%          → NO_PLEDGE_REPORTED
        <=10%       → LOW
        <=25%       → MODERATE
        <=50%       → HIGH
        >50%        → VERY_HIGH
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

    if value == 0:
        signal = "NO_PLEDGE_REPORTED"
        score = 100
    elif value <= 10:
        signal = "LOW"
        score = 85
    elif value <= 25:
        signal = "MODERATE"
        score = 65
    elif value <= 50:
        signal = "HIGH"
        score = 40
    else:
        signal = "VERY_HIGH"
        score = 20

    return {
        "signal": signal,
        "score": score,
        "value": value,
        "unit": fact["unit"],
        "source_status": fact["status"],
        "provenance": fact["provenance"],
        "notes": fact["notes"],
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


def _bias(
    score: Optional[float],
) -> str:
    """Translate score into an analytical bias."""

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

def analyze_institutional(
    research_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Analyze institutional ownership from canonical ResearchResult v1.
    """

    institutional = (
        research_result.get("institutional")
        or {}
    )

    # -----------------------------------------------------------------------
    # Read facts
    # -----------------------------------------------------------------------

    promoter_holding = _fact(
        institutional,
        "promoter_holding_pct",
    )

    promoter_change = _fact(
        institutional,
        "promoter_holding_change_qoq",
    )

    promoter_pledge = _fact(
        institutional,
        "promoter_pledge_pct",
    )

    fii_holding = _fact(
        institutional,
        "fii_holding_pct",
    )

    fii_change = _fact(
        institutional,
        "fii_holding_change_qoq",
    )

    dii_holding = _fact(
        institutional,
        "dii_holding_pct",
    )

    dii_change = _fact(
        institutional,
        "dii_holding_change_qoq",
    )

    # -----------------------------------------------------------------------
    # Interpret individual groups
    # -----------------------------------------------------------------------

    promoter_change_signal = _change_signal(
        promoter_change
    )

    fii_change_signal = _change_signal(
        fii_change
    )

    dii_change_signal = _change_signal(
        dii_change
    )

    promoter_pledge_signal = _pledge_signal(
        promoter_pledge
    )

    # -----------------------------------------------------------------------
    # Combined institutional change
    # -----------------------------------------------------------------------
    #
    # We combine FII and DII ownership changes only as a broad
    # "institutional ownership direction" indicator.
    #
    # This is NOT capital-flow data.
    # -----------------------------------------------------------------------

    fii_change_value = fii_change["value"]
    dii_change_value = dii_change["value"]

    if (
        fii_change_value is None
        and dii_change_value is None
    ):
        institutional_direction = "INSUFFICIENT_DATA"
        institutional_change_score = None

    elif (
        fii_change_value is not None
        and dii_change_value is not None
    ):
        combined_change = (
            fii_change_value
            + dii_change_value
        )

        if combined_change > CHANGE_STABLE:
            institutional_direction = "NET_INCREASE"
            institutional_change_score = 75

        elif combined_change < -CHANGE_STABLE:
            institutional_direction = "NET_DECREASE"
            institutional_change_score = 35

        else:
            institutional_direction = "BROADLY_STABLE"
            institutional_change_score = 60

    elif fii_change_value is not None:
        institutional_direction = (
            "FII_INCREASE"
            if fii_change_value > CHANGE_STABLE
            else "FII_DECREASE"
            if fii_change_value < -CHANGE_STABLE
            else "FII_STABLE"
        )

        institutional_change_score = fii_change_signal["score"]

    else:
        institutional_direction = (
            "DII_INCREASE"
            if dii_change_value > CHANGE_STABLE
            else "DII_DECREASE"
            if dii_change_value < -CHANGE_STABLE
            else "DII_STABLE"
        )

        institutional_change_score = dii_change_signal["score"]

    # -----------------------------------------------------------------------
    # Category scores
    # -----------------------------------------------------------------------

    ownership_change_score = _average([
        promoter_change_signal["score"],
        fii_change_signal["score"],
        dii_change_signal["score"],
    ])

    pledge_score = promoter_pledge_signal["score"]

    overall_score = _average([
        ownership_change_score,
        institutional_change_score,
        pledge_score,
    ])

    ownership_bias = _bias(
        ownership_change_score
    )

    institutional_bias = _bias(
        institutional_change_score
    )

    pledge_bias = _bias(
        pledge_score
    )

    available_categories = [
        score
        for score in [
            ownership_change_score,
            institutional_change_score,
            pledge_score,
        ]
        if score is not None
    ]

    if len(available_categories) < 2:
        overall_bias = "INSUFFICIENT_DATA"
    else:
        overall_bias = _bias(
            overall_score
        )

    # -----------------------------------------------------------------------
    # Reasons
    # -----------------------------------------------------------------------

    reasons: list[str] = []
    limitations: list[str] = []

    # Promoter
    if promoter_change_signal["signal"] == "STRONG_INCREASE":
        reasons.append(
            f"Promoter ownership increased by "
            f"{promoter_change['value']:.2f} percentage points QoQ."
        )
    elif promoter_change_signal["signal"] in {
        "INCREASE",
        "SLIGHT_INCREASE",
    }:
        reasons.append(
            f"Promoter ownership increased by "
            f"{promoter_change['value']:.2f} percentage points QoQ."
        )
    elif promoter_change_signal["signal"] == "STABLE":
        reasons.append(
            "Promoter ownership was broadly stable QoQ."
        )
    elif promoter_change_signal["signal"] in {
        "DECREASE",
        "SLIGHT_DECREASE",
        "STRONG_DECREASE",
    }:
        reasons.append(
            f"Promoter ownership decreased by "
            f"{abs(promoter_change['value']):.2f} percentage points QoQ."
        )
    else:
        limitations.append(
            "Promoter ownership change is unavailable."
        )

    # FII
    if fii_change_signal["signal"] == "STRONG_INCREASE":
        reasons.append(
            f"FII reported ownership increased by "
            f"{fii_change['value']:.2f} percentage points QoQ."
        )
    elif fii_change_signal["direction"] == "INCREASED":
        reasons.append(
            f"FII reported ownership increased by "
            f"{fii_change['value']:.2f} percentage points QoQ."
        )
    elif fii_change_signal["signal"] == "STABLE":
        reasons.append(
            "FII reported ownership was broadly stable QoQ."
        )
    elif fii_change_signal["direction"] == "DECREASED":
        reasons.append(
            f"FII reported ownership decreased by "
            f"{abs(fii_change['value']):.2f} percentage points QoQ."
        )
    else:
        limitations.append(
            "FII ownership change is unavailable."
        )

    # DII
    if dii_change_signal["direction"] == "INCREASED":
        reasons.append(
            f"DII reported ownership increased by "
            f"{dii_change['value']:.2f} percentage points QoQ."
        )
    elif dii_change_signal["signal"] == "STABLE":
        reasons.append(
            "DII reported ownership was broadly stable QoQ."
        )
    elif dii_change_signal["direction"] == "DECREASED":
        reasons.append(
            f"DII reported ownership decreased by "
            f"{abs(dii_change['value']):.2f} percentage points QoQ."
        )
    else:
        limitations.append(
            "DII ownership change is unavailable."
        )

    # Pledge
    if promoter_pledge_signal["signal"] == "NO_PLEDGE_REPORTED":
        reasons.append(
            "No promoter pledge was reported in the available data."
        )
    elif promoter_pledge_signal["signal"] == "LOW":
        reasons.append(
            f"Promoter pledge of "
            f"{promoter_pledge['value']:.2f}% is low."
        )
    elif promoter_pledge_signal["signal"] == "MODERATE":
        reasons.append(
            f"Promoter pledge of "
            f"{promoter_pledge['value']:.2f}% is moderate."
        )
    elif promoter_pledge_signal["signal"] in {
        "HIGH",
        "VERY_HIGH",
    }:
        reasons.append(
            f"Promoter pledge of "
            f"{promoter_pledge['value']:.2f}% is elevated."
        )
    else:
        limitations.append(
            "Promoter pledge percentage is unavailable."
        )

    # -----------------------------------------------------------------------
    # Important analytical caveat
    # -----------------------------------------------------------------------

    limitations.append(
        "Ownership percentage changes indicate changes in reported "
        "shareholding between reporting periods; they do not by "
        "themselves prove open-market buying or selling."
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
            institutional
            .get("provenance", {})
            .get("as_of_date")
        ),
        "signals": {
            "promoter": {
                "bias": ownership_bias,
                "score": promoter_change_signal["score"],
                "holding": _holding_signal(
                    promoter_holding
                ),
                "qoq_change": promoter_change_signal,
                "pledge": promoter_pledge_signal,
            },
            "fii": {
                "holding": _holding_signal(
                    fii_holding
                ),
                "qoq_change": fii_change_signal,
            },
            "dii": {
                "holding": _holding_signal(
                    dii_holding
                ),
                "qoq_change": dii_change_signal,
            },
            "institutional_direction": {
                "direction": institutional_direction,
                "score": institutional_change_score,
                "bias": institutional_bias,
            },
            "promoter_pledge": {
                "bias": pledge_bias,
                "score": pledge_score,
                "signal": promoter_pledge_signal,
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
            "Usage: python intelligence/institutional.py "
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

    result = analyze_institutional(
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
