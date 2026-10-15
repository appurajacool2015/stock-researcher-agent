#!/usr/bin/env python3
"""
Watchlist & Track Record Calculator Module

Purpose
-------
Calculates historical performance tracking between a stock's initial research
baseline and its current assessment without mutating underlying records.

Core Invariants:
1. Deterministic math: Pure calculations of price changes, percentage returns,
   and elapsed time based strictly on verifiable timestamps and prices.
2. Baseline immutability: The initial research date, price, and verdict are
   strictly preserved as the permanent comparison anchor.
3. Missing price safety: Zero, negative, or missing baseline/current prices
   gracefully degrade to unavailable rather than raising division errors or
   inventing returns.
4. Truth in reporting: Explicitly labels metrics as 'Price Return (Research Baseline)',
   distinguishing theoretical research performance from actual portfolio returns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


def _parse_timestamp(ts_val: Any) -> Optional[datetime]:
    """Safely parse ISO timestamp into a timezone-aware UTC datetime."""
    if not ts_val:
        return None
    if isinstance(ts_val, datetime):
        return ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
    if isinstance(ts_val, str):
        try:
            # Handle standard ISO formats and Z suffix
            clean_str = ts_val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None
    return None


def calculate_price_return(
    baseline_price: Optional[float],
    current_price: Optional[float],
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Calculate absolute price change and percentage price return.

    Returns:
        (price_change, return_pct, note)
    """
    if baseline_price is None or not isinstance(baseline_price, (int, float)) or baseline_price <= 0:
        return None, None, "Price return unavailable: baseline research price is missing or invalid."

    if current_price is None or not isinstance(current_price, (int, float)) or current_price <= 0:
        return None, None, "Price return unavailable: current market price is missing or invalid."

    change = round(float(current_price) - float(baseline_price), 2)
    return_pct = round((change / float(baseline_price)) * 100.0, 2)
    return change, return_pct, None


def calculate_elapsed_time(
    baseline_dt: Optional[datetime],
    current_dt: Optional[datetime],
) -> Tuple[int, str]:
    """
    Calculate calendar days elapsed and human-readable duration description.

    Returns:
        (days_elapsed, duration_str)
    """
    if not baseline_dt:
        return 0, "Unknown duration"

    now_dt = current_dt or datetime.now(timezone.utc)
    delta = now_dt - baseline_dt
    days = max(0, delta.days)

    if days == 0:
        hours = max(0, int(delta.total_seconds() // 3600))
        if hours <= 1:
            duration_str = "Earlier today"
        else:
            duration_str = f"Today ({hours}h ago)"
    elif days == 1:
        duration_str = "1 day ago"
    else:
        duration_str = f"{days} days ago"

    return days, duration_str


def calculate_track_record(
    current_assessment: Dict[str, Any],
    baseline_assessment: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Compute comprehensive track-record comparison against initial baseline.

    Parameters
    ----------
    current_assessment: The evaluated investment assessment for the current run.
    baseline_assessment: The earliest recorded assessment for this symbol from Supabase,
                         or None if this is the first research run.

    Returns
    -------
    Structured track record payload conforming to audit specifications.
    """
    symbol = str(current_assessment.get("symbol", "UNKNOWN")).upper()
    current_cmp = current_assessment.get("cmp")
    current_action = current_assessment.get("investment_action", "UNAVAILABLE")
    current_ts = (
        _parse_timestamp(current_assessment.get("assessment_timestamp"))
        or _parse_timestamp(current_assessment.get("created_at"))
        or datetime.now(timezone.utc)
    )

    # Check if a genuine prior baseline exists
    has_prior_baseline = False
    if baseline_assessment and isinstance(baseline_assessment, dict):
        base_id = baseline_assessment.get("id") or baseline_assessment.get("research_run_id")
        curr_id = current_assessment.get("id") or current_assessment.get("research_run_id")

        # Prior baseline exists if baseline has an ID and it doesn't match the current unsaved/cached run
        # OR if baseline has a strictly earlier timestamp than the current assessment
        base_ts = _parse_timestamp(baseline_assessment.get("assessment_timestamp")) or _parse_timestamp(baseline_assessment.get("created_at"))
        if base_ts and current_ts and base_ts < current_ts:
            has_prior_baseline = True
        elif base_id and curr_id and str(base_id) != str(curr_id):
            has_prior_baseline = True
        elif base_id and not curr_id:
            # Baseline is a saved record from DB while current is a fresh in-memory assessment
            has_prior_baseline = True

    # Case 1: First research run (establishing baseline)
    if not has_prior_baseline or baseline_assessment is None:
        return {
            "symbol": symbol,
            "status": "BASELINE_ESTABLISHED",
            "has_prior_history": False,
            "first_researched_at": current_ts.isoformat(),
            "first_researched_price": current_cmp,
            "initial_verdict": current_action,
            "latest_price": current_cmp,
            "latest_verdict": current_action,
            "price_change": None,
            "price_return_pct": None,
            "days_elapsed": 0,
            "duration_str": "Baseline established today",
            "verdict_changed": False,
            "verdict_transition": f"{current_action} (Initial)",
            "note": "Initial research baseline established. Historical price tracking will activate on future checks.",
            "disclaimer": (
                "Price return reflects market price change since the initial research timestamp. "
                "It does not represent realized portfolio return or personal purchase price, and excludes "
                "dividends, transaction fees, and taxes."
            ),
        }

    # Case 2: Subsequent research run with prior history
    baseline_ts = (
        _parse_timestamp(baseline_assessment.get("assessment_timestamp"))
        or _parse_timestamp(baseline_assessment.get("created_at"))
        or current_ts
    )
    baseline_cmp = baseline_assessment.get("cmp")
    baseline_action = baseline_assessment.get("investment_action", "UNAVAILABLE")

    price_change, price_return_pct, price_note = calculate_price_return(baseline_cmp, current_cmp)
    days_elapsed, duration_str = calculate_elapsed_time(baseline_ts, current_ts)

    verdict_changed = baseline_action != current_action
    if verdict_changed:
        verdict_transition = f"{baseline_action} ➔ {current_action}"
        verdict_note = f"Investment verdict changed from {baseline_action} to {current_action}."
    else:
        verdict_transition = f"{current_action} (Unchanged)"
        verdict_note = f"Investment thesis remains consistent ({current_action})."

    # Evaluation quality notes
    baseline_date_str = baseline_ts.strftime("%d %b %Y")
    latest_date_str = current_ts.strftime("%d %b %Y")

    return {
        "symbol": symbol,
        "status": "TRACK_RECORD_AVAILABLE",
        "has_prior_history": True,
        "first_researched_at": baseline_ts.isoformat(),
        "first_researched_date_str": baseline_date_str,
        "first_researched_price": baseline_cmp,
        "initial_verdict": baseline_action,
        "latest_price": current_cmp,
        "latest_date_str": latest_date_str,
        "latest_verdict": current_action,
        "price_change": price_change,
        "price_return_pct": price_return_pct,
        "price_return_note": price_note,
        "days_elapsed": days_elapsed,
        "duration_str": f"{duration_str} ({baseline_date_str})",
        "verdict_changed": verdict_changed,
        "verdict_transition": verdict_transition,
        "verdict_note": verdict_note,
        "note": f"Compared against research baseline established on {baseline_date_str}.",
        "disclaimer": (
            "Price return reflects market price change since the initial research timestamp. "
            "It does not represent realized portfolio return or personal purchase price, and excludes "
            "dividends, transaction fees, and taxes."
        ),
        "causality_disclaimer": (
            "Price movement since research baseline does not guarantee future results or validate "
            "the infallibility of prior automated assessments."
        ),
    }
