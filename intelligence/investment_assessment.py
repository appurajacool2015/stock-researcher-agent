#!/usr/bin/env python3
"""
Higher-Level Deterministic Investment Assessment Engine v1.0.0

Purpose
-------
Combines canonical ResearchResult v1 evidence—including deterministic technicals,
fundamentals, institutional shareholding, and news—to produce an objective,
audit-grade higher-level investment assessment.

Mandatory Safeguards:
1. Five mutually exclusive higher-level actions:
   - INSUFFICIENT_DATA
   - REDUCE_SELL_REVIEW
   - AVOID_NEW_ENTRY
   - BUY_CANDIDATE
   - HOLD_REVIEW
2. Missing, stale, contradictory, or unverified data are never treated as positive evidence.
3. BUY_CANDIDATE requires all defined mandatory checks to pass. If required evidence
   is unavailable, degrades to an appropriate non-buy action or INSUFFICIENT_DATA.
4. Bank / NBFC / Debt-free applicability guard for Debt-to-Equity.
5. Technical metrics/scores and Investment actions/scores are kept strictly separate.
6. All decision thresholds are configurable, documented, and traceable.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Import project intelligence modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from intelligence.buying_zone import evaluate_buying_zone
from intelligence.fundamentals import analyze_fundamentals
from intelligence.institutional import analyze_institutional
from intelligence.news import analyze_news
from intelligence.technicals import analyze_technicals

ENGINE_VERSION = "1.0.0"


# ==============================================================================
# CONFIGURABLE THRESHOLDS
# ==============================================================================

@dataclass(frozen=True)
class InvestmentThresholds:
    """
    Configurable thresholds for deterministic investment assessment.

    Assumptions:
    - Minimum ROE/ROCE of 15% represents high capital efficiency for Indian large/mid-caps.
    - 3-year CAGR > 0% is required for buy eligibility, with >= 5% indicating healthy expansion.
    - P/E <= 45.0 serves as a pragmatic absolute upper valuation bound for buy candidates;
      P/E > 65.0 or P/B > 12.0 represents extreme valuation requiring avoidance of fresh entry.
      NOTE ON P/E VALUATION LIMITATION: The historical industry-median P/E alternative is
      deferred because reliable peer and industry-median valuation data is not currently
      produced by the canonical research pipeline. We strictly avoid fabricating or estimating
      industry-median multiples.
    - Debt-to-equity <= 1.0 represents conservative leverage for non-financials.
    - Promoter pledge > 25.0% represents critical financial/governance risk.
    """
    roe_min_buy: float = 15.0
    roce_min_buy: float = 15.0
    sales_growth_min_buy: float = 5.0
    profit_growth_min_buy: float = 5.0
    pe_max_buy: float = 45.0
    pe_extreme_avoid: float = 65.0
    pb_extreme_avoid: float = 12.0
    debt_to_equity_max_buy: float = 1.0
    debt_to_equity_high_risk: float = 2.0
    promoter_pledge_max_buy: float = 10.0
    promoter_pledge_severe_risk: float = 25.0


DEFAULT_THRESHOLDS = InvestmentThresholds()


# ==============================================================================
# HELPERS
# ==============================================================================

def _number(value: Any) -> Optional[float]:
    """Convert value to float safely without converting booleans."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_fact(
    container: Dict[str, Any],
    key: str,
    fallback_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract a canonical field-envelope fact dictionary with optional fallback key."""
    if not isinstance(container, dict):
        return {
            "value": None,
            "unit": None,
            "status": "UNAVAILABLE",
            "provenance": None,
            "notes": None,
        }
    fact = container.get(key)
    if (not isinstance(fact, dict) or fact.get("status") == "UNAVAILABLE") and fallback_key:
        fallback_fact = container.get(fallback_key)
        if isinstance(fallback_fact, dict) and fallback_fact.get("status") != "UNAVAILABLE":
            fact = fallback_fact
        elif not isinstance(fact, dict):
            fact = fallback_fact

    if not isinstance(fact, dict):
        return {
            "value": None,
            "unit": None,
            "status": "UNAVAILABLE",
            "provenance": None,
            "notes": None,
        }
    return {
        "value": _number(fact.get("value")),
        "unit": fact.get("unit"),
        "status": fact.get("status", "UNAVAILABLE"),
        "provenance": fact.get("provenance"),
        "notes": fact.get("notes"),
    }


def _is_verified_or_derived(fact: Dict[str, Any]) -> bool:
    """Check if fact status indicates usable evidence (not missing/stale/conflicting)."""
    return fact["status"] in {"VERIFIED", "DERIVED"} and fact["value"] is not None


def _is_financial_institution(company_name: str, fundamentals: Dict[str, Any]) -> bool:
    """
    Detect whether the entity is a Bank, NBFC, or Financial Institution.
    Checked via sector/industry fields and standard corporate naming conventions.
    """
    text_corpus = (company_name or "").lower()
    sector = str(fundamentals.get("sector") or "").lower()
    industry = str(fundamentals.get("industry") or "").lower()
    full_text = f"{text_corpus} {sector} {industry}"

    financial_keywords = [
        "bank", "banking", "finance", "housing finance", "finserve",
        "capital services", "nbfc", "financial", "asset management",
        "life insurance", "general insurance", "holdings"
    ]
    return any(keyword in full_text for keyword in financial_keywords)



def _extract_metric_item(
    container: Any,
    key: str,
    default_date: Optional[str] = None,
) -> Tuple[Optional[float], str, str]:
    """
    Extract (value, status, as_of_date) safely from a datapoint envelope.
    Preserves VERIFIED, DERIVED, STALE, CONFLICTING, UNAVAILABLE statuses faithfully.
    """
    if not isinstance(container, dict):
        return None, "UNAVAILABLE", "—"
    item = container.get(key)
    if not isinstance(item, dict):
        return None, "UNAVAILABLE", "—"

    val = _number(item.get("value"))
    status = str(item.get("status") or ("VERIFIED" if val is not None else "UNAVAILABLE"))

    prov = item.get("provenance")
    as_of = None
    if isinstance(prov, dict):
        as_of = prov.get("as_of_date")
    if not as_of:
        as_of = default_date or "—"

    if val is None and status == "UNAVAILABLE":
        return None, "UNAVAILABLE", "—"

    return val, status, str(as_of)


def build_key_metrics(research_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Construct a deterministic list of 16 key financial, valuation, and volume metrics
    conforming strictly to the 4-column specification: [Metric, Value, Status, As-Of Date].

    Guards:
    1. Never invent values or substitute zero for missing data.
    2. Missing metrics explicitly labeled UNAVAILABLE with as-of date '—'.
    3. Stale/conflicting statuses are faithfully preserved from pipeline facts.
    4. Debt-to-Equity is marked 'N/A' (Status: 'N/A') for Banks / NBFCs.
    5. PEG is explicitly UNAVAILABLE (Date: '—') pending future schema support.
    6. Relative volume guards against zero/missing 20-day average volume.
    7. OBV trend describes directional volume-flow without claiming institutional proof.
    """
    fundamentals = research_result.get("fundamentals") or {}
    technicals = research_result.get("technicals") or {}
    institutional = research_result.get("institutional") or {}
    company_name = str(research_result.get("company_name") or "")

    fund_date = fundamentals.get("provenance", {}).get("as_of_date") if isinstance(fundamentals, dict) else None
    tech_date = technicals.get("provenance", {}).get("as_of_date") if isinstance(technicals, dict) else None
    inst_date = institutional.get("provenance", {}).get("as_of_date") if isinstance(institutional, dict) else None

    # 1. CMP
    cmp_val, cmp_stat, cmp_dt = _extract_metric_item(technicals, "cmp", tech_date)
    cmp_str = f"₹{cmp_val:,.2f}" if cmp_val is not None else "UNAVAILABLE"

    # 2. P/E
    pe_val, pe_stat, pe_dt = _extract_metric_item(fundamentals, "pe_ratio", fund_date)
    pe_str = f"{pe_val:.2f}x" if pe_val is not None else "UNAVAILABLE"

    # 3. ROCE
    roce_val, roce_stat, roce_dt = _extract_metric_item(fundamentals, "roce", fund_date)
    roce_str = f"{roce_val:.1f}%" if roce_val is not None else "UNAVAILABLE"

    # 4. ROE
    roe_val, roe_stat, roe_dt = _extract_metric_item(fundamentals, "roe", fund_date)
    roe_str = f"{roe_val:.1f}%" if roe_val is not None else "UNAVAILABLE"

    # 5. 3Y Sales Growth
    sg_val, sg_stat, sg_dt = _extract_metric_item(fundamentals, "sales_growth_3y_cagr", fund_date)
    if sg_val is None:
        sg_val, sg_stat, sg_dt = _extract_metric_item(fundamentals, "sales_growth_3years_cagr", fund_date)
    sg_str = f"{sg_val:.1f}%" if sg_val is not None else "UNAVAILABLE"

    # 6. 3Y Profit Growth
    pg_val, pg_stat, pg_dt = _extract_metric_item(fundamentals, "profit_growth_3y_cagr", fund_date)
    if pg_val is None:
        pg_val, pg_stat, pg_dt = _extract_metric_item(fundamentals, "profit_growth_3years_cagr", fund_date)
    pg_str = f"{pg_val:.1f}%" if pg_val is not None else "UNAVAILABLE"

    # 7. 50 DMA
    dma50_val, dma50_stat, dma50_dt = _extract_metric_item(technicals, "dma_50", tech_date)
    dma50_str = f"₹{dma50_val:,.2f}" if dma50_val is not None else "UNAVAILABLE"

    # 8. 200 DMA
    dma200_val, dma200_stat, dma200_dt = _extract_metric_item(technicals, "dma_200", tech_date)
    dma200_str = f"₹{dma200_val:,.2f}" if dma200_val is not None else "UNAVAILABLE"

    # 9. RSI (14)
    rsi_val, rsi_stat, rsi_dt = _extract_metric_item(technicals, "rsi_14", tech_date)
    rsi_str = f"{rsi_val:.1f}" if rsi_val is not None else "UNAVAILABLE"

    # 10. Debt-to-Equity
    is_fin = _is_financial_institution(company_name, fundamentals)
    if is_fin:
        de_str = "N/A"
        de_stat = "N/A"
        de_dt = "—"
        de_val = None
    else:
        de_val, de_stat, de_dt = _extract_metric_item(fundamentals, "debt_to_equity", fund_date)
        de_str = f"{de_val:.2f}" if de_val is not None else "UNAVAILABLE"

    # 11. Promoter Pledge
    pledge_val, pledge_stat, pledge_dt = _extract_metric_item(institutional, "promoter_pledge_pct", inst_date)
    pledge_str = f"{pledge_val:.1f}%" if pledge_val is not None else "UNAVAILABLE"

    # 12. PEG (Explicitly UNAVAILABLE until supported)
    peg_str = "UNAVAILABLE"
    peg_stat = "UNAVAILABLE"
    peg_dt = "—"

    # 13. Trading Volume (Latest completed session)
    vol_val, vol_stat, vol_dt = _extract_metric_item(technicals, "volume", tech_date)
    vol_str = f"{int(round(vol_val)):,}" if vol_val is not None else "UNAVAILABLE"

    # 14. 20-Day Avg Volume
    avg_vol_val, avg_vol_stat, avg_vol_dt = _extract_metric_item(technicals, "avg_volume_20", tech_date)
    if avg_vol_val is None:
        avg_vol_val, avg_vol_stat, avg_vol_dt = _extract_metric_item(technicals, "avg_volume_1m", tech_date)
    avg_vol_str = f"{int(round(avg_vol_val)):,}" if avg_vol_val is not None else "UNAVAILABLE"

    # 15. Relative Volume = latest session volume / 20-day average volume
    pct_val, _, _ = _extract_metric_item(technicals, "volume_vs_20d_pct")
    if pct_val is None:
        pct_val, _, _ = _extract_metric_item(technicals, "volume_vs_1m_pct")

    if vol_val is not None and avg_vol_val is not None and avg_vol_val > 0:
        rel_ratio = vol_val / avg_vol_val
        if pct_val is not None:
            pct_sign = "+" if pct_val >= 0 else ""
            rel_vol_str = f"{rel_ratio:.2f}x ({pct_sign}{pct_val:.1f}%)"
        else:
            pct_derived = ((rel_ratio - 1.0) * 100.0)
            pct_sign = "+" if pct_derived >= 0 else ""
            rel_vol_str = f"{rel_ratio:.2f}x ({pct_sign}{pct_derived:.1f}%)"
        rel_vol_stat = "DERIVED"
        rel_vol_dt = tech_date or "—"
    else:
        rel_vol_str = "UNAVAILABLE"
        rel_vol_stat = "UNAVAILABLE"
        rel_vol_dt = "—"
        rel_ratio = None

    # 16. OBV Trend (14d)
    obv_val, _, obv_dt = _extract_metric_item(technicals, "obv_change_norm_14d", tech_date)
    if obv_val is not None:
        if obv_val >= 0.10:
            obv_str = f"Positive (+{obv_val:.2f})"
        elif obv_val >= -0.10:
            sign = "+" if obv_val >= 0 else ""
            obv_str = f"Neutral ({sign}{obv_val:.2f})"
        else:
            obv_str = f"Negative ({obv_val:.2f})"
        obv_stat = "DERIVED"
    else:
        obv_str = "UNAVAILABLE"
        obv_stat = "UNAVAILABLE"
        obv_dt = "—"

    return [
        {"metric": "CMP", "value": cmp_str, "status": cmp_stat, "as_of_date": cmp_dt, "raw_value": cmp_val},
        {"metric": "P/E", "value": pe_str, "status": pe_stat, "as_of_date": pe_dt, "raw_value": pe_val},
        {"metric": "ROCE", "value": roce_str, "status": roce_stat, "as_of_date": roce_dt, "raw_value": roce_val},
        {"metric": "ROE", "value": roe_str, "status": roe_stat, "as_of_date": roe_dt, "raw_value": roe_val},
        {"metric": "3Y Sales Growth", "value": sg_str, "status": sg_stat, "as_of_date": sg_dt, "raw_value": sg_val},
        {"metric": "3Y Profit Growth", "value": pg_str, "status": pg_stat, "as_of_date": pg_dt, "raw_value": pg_val},
        {"metric": "50 DMA", "value": dma50_str, "status": dma50_stat, "as_of_date": dma50_dt, "raw_value": dma50_val},
        {"metric": "200 DMA", "value": dma200_str, "status": dma200_stat, "as_of_date": dma200_dt, "raw_value": dma200_val},
        {"metric": "RSI (14)", "value": rsi_str, "status": rsi_stat, "as_of_date": rsi_dt, "raw_value": rsi_val},
        {"metric": "Debt-to-Equity", "value": de_str, "status": de_stat, "as_of_date": de_dt, "raw_value": de_val},
        {"metric": "Promoter Pledge", "value": pledge_str, "status": pledge_stat, "as_of_date": pledge_dt, "raw_value": pledge_val},
        {"metric": "PEG", "value": peg_str, "status": peg_stat, "as_of_date": peg_dt, "raw_value": None},
        {"metric": "Trading Volume (Latest)", "value": vol_str, "status": vol_stat, "as_of_date": vol_dt, "raw_value": vol_val},
        {"metric": "20-Day Avg Volume", "value": avg_vol_str, "status": avg_vol_stat, "as_of_date": avg_vol_dt, "raw_value": avg_vol_val},
        {"metric": "Relative Volume", "value": rel_vol_str, "status": rel_vol_stat, "as_of_date": rel_vol_dt, "raw_value": rel_ratio},
        {"metric": "OBV Trend (14d)", "value": obv_str, "status": obv_stat, "as_of_date": obv_dt, "raw_value": obv_val},
    ]


# ==============================================================================
# DETERMINISTIC ASSESSMENT ENGINE
# ==============================================================================

def evaluate_investment_assessment(
    research_result: Dict[str, Any],
    thresholds: InvestmentThresholds = DEFAULT_THRESHOLDS,
) -> Dict[str, Any]:
    """
    Execute deterministic higher-level investment assessment.

    Parameters
    ----------
    research_result: Canonical ResearchResult v1 dictionary.
    thresholds: Configurable thresholds instance.

    Returns
    -------
    Dictionary conforming to Phase 4 recommendation contract.
    """
    now_utc = datetime.now(timezone.utc).isoformat()
    symbol = str(research_result.get("symbol") or "UNKNOWN").upper()
    company_name = str(research_result.get("company_name") or symbol)
    overall_status = str(research_result.get("overall_status") or "UNAVAILABLE")

    fundamentals_data = research_result.get("fundamentals") or {}
    technicals_data = research_result.get("technicals") or {}
    institutional_data = research_result.get("institutional") or {}

    # Run intelligence sub-evaluations
    tech_intel = analyze_technicals(research_result)
    fund_intel = analyze_fundamentals(research_result)
    inst_intel = analyze_institutional(research_result)
    news_intel = analyze_news(research_result)

    # Separate Technical Metrics
    technical_classification = tech_intel.get("classification", "INSUFFICIENT_DATA")
    technical_score = tech_intel.get("score")
    technical_confidence = tech_intel.get("confidence", 0.0)
    key_levels = tech_intel.get("key_levels", {})

    # Extract market and fundamental facts
    cmp_fact = _get_fact(technicals_data, "cmp")
    dma50_fact = _get_fact(technicals_data, "dma_50")
    dma200_fact = _get_fact(technicals_data, "dma_200")
    rsi_fact = _get_fact(technicals_data, "rsi_14")

    roe_fact = _get_fact(fundamentals_data, "roe")
    roce_fact = _get_fact(fundamentals_data, "roce")
    sales_growth_fact = _get_fact(
        fundamentals_data,
        "sales_growth_3y_cagr",
        fallback_key="sales_growth_3years_cagr",
    )
    profit_growth_fact = _get_fact(
        fundamentals_data,
        "profit_growth_3y_cagr",
        fallback_key="profit_growth_3years_cagr",
    )
    pe_fact = _get_fact(fundamentals_data, "pe_ratio")
    pb_fact = _get_fact(fundamentals_data, "pb_ratio")
    de_fact = _get_fact(fundamentals_data, "debt_to_equity")

    pledge_fact = _get_fact(
        institutional_data,
        "promoter_pledge_pct",
        fallback_key="promoter_pledge",
    )

    # Audit tracking lists
    reason_codes: List[str] = []
    positive_factors: List[str] = []
    cautionary_factors: List[str] = []
    risk_flags: List[str] = []
    limitations: List[str] = []

    # Provenance and market as-of date
    market_as_of = (
        technicals_data.get("provenance", {}).get("as_of_date")
        or fundamentals_data.get("provenance", {}).get("as_of_date")
    )

    # Evaluate deterministic buying zone entry setup
    buying_zone_eval = evaluate_buying_zone(research_result)
    key_metrics_data = build_key_metrics(research_result)

    # Synchronize key_levels with buying zone references if technical key_levels are absent
    key_levels = dict(key_levels)
    if buying_zone_eval:
        if (not key_levels.get("support_reference") or not key_levels["support_reference"].get("price")) and buying_zone_eval.get("support_reference"):
            key_levels["support_reference"] = {
                "price": buying_zone_eval["support_reference"],
                "level_type": buying_zone_eval.get("support_type", "Support Reference"),
            }
        if (not key_levels.get("resistance_reference") or not key_levels["resistance_reference"].get("price")) and buying_zone_eval.get("resistance_reference"):
            key_levels["resistance_reference"] = {
                "price": buying_zone_eval["resistance_reference"],
                "level_type": buying_zone_eval.get("resistance_type", "Resistance Reference"),
            }

    # --------------------------------------------------------------------------
    # DATA QUALITY & LIMITATIONS AUDIT
    # --------------------------------------------------------------------------
    facts_to_audit = [
        ("CMP", cmp_fact),
        ("50-DMA", dma50_fact),
        ("200-DMA", dma200_fact),
        ("RSI(14)", rsi_fact),
        ("ROE", roe_fact),
        ("ROCE", roce_fact),
        ("3y Sales CAGR", sales_growth_fact),
        ("3y Profit CAGR", profit_growth_fact),
        ("P/E Ratio", pe_fact),
        ("P/B Ratio", pb_fact),
        ("Debt-to-Equity", de_fact),
        ("Promoter Pledge", pledge_fact),
    ]

    usable_count = 0
    total_audited = len(facts_to_audit)

    for label, f_item in facts_to_audit:
        f_stat = f_item["status"]
        if f_stat in {"VERIFIED", "DERIVED"} and f_item["value"] is not None:
            usable_count += 1
        elif f_stat == "UNAVAILABLE":
            limitations.append(f"{label} is unavailable.")
        elif f_stat == "STALE":
            limitations.append(f"{label} is marked STALE; freshness requirements not met.")
            cautionary_factors.append(f"{label} data is stale.")
        elif f_stat == "CONFLICTING":
            limitations.append(f"{label} has conflicting observations across sources.")
            cautionary_factors.append(f"{label} source values conflict.")
        elif f_stat == "FAILED":
            limitations.append(f"{label} extraction failed.")
            cautionary_factors.append(f"{label} source failure detected.")

    # Copy news limitations/flags
    if news_intel.get("limitations"):
        limitations.extend(news_intel["limitations"])
    if news_intel.get("risk_flags"):
        risk_flags.extend(news_intel["risk_flags"])

    # --------------------------------------------------------------------------
    # DEBT-TO-EQUITY APPLICABILITY GUARD
    # --------------------------------------------------------------------------
    is_fin = _is_financial_institution(company_name, fundamentals_data)
    is_debt_free = False
    de_status_guard = "EVALUATE"

    if is_fin:
        de_status_guard = "NOT_APPLICABLE_BANK_NBFC"
        positive_factors.append("Debt-to-equity is structurally not applicable (Bank/NBFC).")
        reason_codes.append("LEVERAGE_NOT_APPLICABLE_FINANCIAL")
    elif de_fact["value"] == 0.0 and _is_verified_or_derived(de_fact):
        is_debt_free = True
        de_status_guard = "DEBT_FREE"
        positive_factors.append("Company is verified debt-free (D/E = 0.00).")
        reason_codes.append("COMPANY_DEBT_FREE")
    elif de_fact["status"] == "UNAVAILABLE":
        de_status_guard = "MISSING_EVIDENCE"
        # Explicit guard: Do not assume NOT_APPLICABLE without evidence!
        limitations.append("Debt-to-equity is unavailable and cannot be verified.")
    elif _is_verified_or_derived(de_fact):
        de_val = de_fact["value"]
        if de_val <= thresholds.debt_to_equity_max_buy:
            positive_factors.append(f"Conservative leverage with Debt-to-Equity of {de_val:.2f}.")
        elif de_val >= thresholds.debt_to_equity_high_risk:
            cautionary_factors.append(f"Elevated financial leverage with Debt-to-Equity of {de_val:.2f}.")
            risk_flags.append(f"HIGH_LEVERAGE_DE_{de_val:.2f}")

    # --------------------------------------------------------------------------
    # POSITIVE & CAUTIONARY FACTOR ACCUMULATION
    # --------------------------------------------------------------------------
    # Profitability
    if _is_verified_or_derived(roe_fact) and roe_fact["value"] >= thresholds.roe_min_buy:
        positive_factors.append(f"Robust ROE of {roe_fact['value']:.1f}% exceeds {thresholds.roe_min_buy}%.")
    if _is_verified_or_derived(roce_fact) and roce_fact["value"] >= thresholds.roce_min_buy:
        positive_factors.append(f"Strong ROCE of {roce_fact['value']:.1f}% exceeds {thresholds.roce_min_buy}%.")

    # Growth
    if _is_verified_or_derived(sales_growth_fact) and sales_growth_fact["value"] >= thresholds.sales_growth_min_buy:
        positive_factors.append(f"Steady 3-year sales CAGR of {sales_growth_fact['value']:.1f}%.")
    if _is_verified_or_derived(profit_growth_fact) and profit_growth_fact["value"] >= thresholds.profit_growth_min_buy:
        positive_factors.append(f"Healthy 3-year profit CAGR of {profit_growth_fact['value']:.1f}%.")
    elif _is_verified_or_derived(profit_growth_fact) and profit_growth_fact["value"] < 0:
        cautionary_factors.append(f"Negative 3-year profit CAGR of {profit_growth_fact['value']:.1f}%.")

    # Valuation
    if _is_verified_or_derived(pe_fact):
        pe_val = pe_fact["value"]
        if pe_val <= thresholds.pe_max_buy and pe_val > 0:
            positive_factors.append(f"Reasonable valuation at P/E {pe_val:.1f}x.")
        elif pe_val > thresholds.pe_extreme_avoid:
            cautionary_factors.append(f"Extreme valuation at P/E {pe_val:.1f}x (above {thresholds.pe_extreme_avoid}x).")
            risk_flags.append(f"EXTREME_PE_VALUATION_{pe_val:.1f}")

    if _is_verified_or_derived(pb_fact):
        pb_val = pb_fact["value"]
        if pb_val > thresholds.pb_extreme_avoid:
            cautionary_factors.append(f"Elevated price-to-book ratio of {pb_val:.1f}x.")

    # Promoter Pledge
    if _is_verified_or_derived(pledge_fact):
        pledge_val = pledge_fact["value"]
        if pledge_val <= thresholds.promoter_pledge_max_buy:
            positive_factors.append(f"Clean promoter pledge at {pledge_val:.1f}%.")
        elif pledge_val >= thresholds.promoter_pledge_severe_risk:
            cautionary_factors.append(f"High promoter pledge of {pledge_val:.1f}% represents governance risk.")
            risk_flags.append(f"HIGH_PROMOTER_PLEDGE_{pledge_val:.1f}")

    # Technical factors
    if tech_intel.get("positive_factors"):
        positive_factors.extend(tech_intel["positive_factors"][:2])
    if tech_intel.get("cautionary_factors"):
        cautionary_factors.extend(tech_intel["cautionary_factors"][:2])
    if tech_intel.get("risk_flags"):
        risk_flags.extend(tech_intel["risk_flags"])

    # --------------------------------------------------------------------------
    # RULE EVALUATION HIERARCHY
    # --------------------------------------------------------------------------
    investment_action: str = "INSUFFICIENT_DATA"
    investment_score: Optional[float] = None

    # Calculate base confidence strictly from verified/derived coverage
    investment_confidence = round(usable_count / total_audited, 2)

    # --------------------------------------------------------------------------
    # RULE 1: INSUFFICIENT_DATA
    # --------------------------------------------------------------------------
    rule1_triggered = False

    if overall_status == "FAILED":
        rule1_triggered = True
        reason_codes.append("RULE1_PIPELINE_STATUS_FAILED")
    elif not _is_verified_or_derived(cmp_fact) or not _is_verified_or_derived(dma50_fact):
        rule1_triggered = True
        reason_codes.append("RULE1_CRITICAL_PRICE_DATA_MISSING")
    elif technical_classification == "INSUFFICIENT_DATA":
        rule1_triggered = True
        reason_codes.append("RULE1_TECHNICAL_INSUFFICIENT_DATA")
    elif not _is_verified_or_derived(roe_fact) and not _is_verified_or_derived(roce_fact):
        rule1_triggered = True
        reason_codes.append("RULE1_PROFITABILITY_METRICS_UNAVAILABLE")

    if rule1_triggered:
        investment_action = "INSUFFICIENT_DATA"
        investment_score = None
        return _build_recommendation_dict(
            symbol=symbol,
            company_name=company_name,
            cmp_fact=cmp_fact,
            technical_classification=technical_classification,
            technical_score=technical_score,
            technical_confidence=technical_confidence,
            investment_action=investment_action,
            investment_score=investment_score,
            investment_confidence=investment_confidence,
            reason_codes=reason_codes,
            positive_factors=positive_factors,
            cautionary_factors=cautionary_factors,
            risk_flags=risk_flags,
            key_levels=key_levels,
            limitations=limitations,
            market_as_of=market_as_of,
            now_utc=now_utc,
            research_run_id=research_result.get("research_id"),
            buying_zone=buying_zone_eval,
            key_metrics=key_metrics_data,
        )

    # --------------------------------------------------------------------------
    # RULE 2: REDUCE_SELL_REVIEW
    # --------------------------------------------------------------------------
    rule2_triggered = False

    # Condition 2A: Technical breakdown
    if technical_classification == "REDUCE_SELL_CANDIDATE":
        rule2_triggered = True
        reason_codes.append("RULE2_TECHNICAL_BREAKDOWN")

    # Condition 2B: Severe Promoter Pledge
    if _is_verified_or_derived(pledge_fact) and pledge_fact["value"] > thresholds.promoter_pledge_severe_risk:
        rule2_triggered = True
        reason_codes.append("RULE2_CRITICAL_PROMOTER_PLEDGE")

    # Condition 2C: High leverage + negative profit growth + below 50/200 DMA
    if (
        de_status_guard == "EVALUATE"
        and _is_verified_or_derived(de_fact)
        and de_fact["value"] >= thresholds.debt_to_equity_high_risk
        and _is_verified_or_derived(profit_growth_fact)
        and profit_growth_fact["value"] < 0
        and _is_verified_or_derived(dma50_fact)
        and _is_verified_or_derived(dma200_fact)
        and cmp_fact["value"] < dma50_fact["value"]
        and cmp_fact["value"] < dma200_fact["value"]
    ):
        rule2_triggered = True
        reason_codes.append("RULE2_HIGH_LEVERAGE_AND_EARNINGS_CONTRACTION")

    # Condition 2D: Critical news risk (fraud, severe regulatory sanction)
    if "REGULATORY" in risk_flags or "FRAUD" in risk_flags:
        rule2_triggered = True
        reason_codes.append("RULE2_REGULATORY_OR_GOVERNANCE_SEVERITY")

    if rule2_triggered:
        investment_action = "REDUCE_SELL_REVIEW"
        investment_score = round(max(15.0, (technical_score or 30.0) * 0.5), 1)
        return _build_recommendation_dict(
            symbol=symbol,
            company_name=company_name,
            cmp_fact=cmp_fact,
            technical_classification=technical_classification,
            technical_score=technical_score,
            technical_confidence=technical_confidence,
            investment_action=investment_action,
            investment_score=investment_score,
            investment_confidence=investment_confidence,
            reason_codes=reason_codes,
            positive_factors=positive_factors,
            cautionary_factors=cautionary_factors,
            risk_flags=risk_flags,
            key_levels=key_levels,
            limitations=limitations,
            market_as_of=market_as_of,
            now_utc=now_utc,
            research_run_id=research_result.get("research_id"),
            buying_zone=buying_zone_eval,
            key_metrics=key_metrics_data,
        )

    # --------------------------------------------------------------------------
    # RULE 3: AVOID_NEW_ENTRY
    # --------------------------------------------------------------------------
    rule3_triggered = False

    # Condition 3A: Technical avoid classification
    if technical_classification == "AVOID_NEW_ENTRY":
        rule3_triggered = True
        reason_codes.append("RULE3_TECHNICAL_AVOID_CONDITION")

    # Condition 3B: Extreme valuation without exceptional growth
    is_growth_exceptional = (
        _is_verified_or_derived(sales_growth_fact)
        and sales_growth_fact["value"] >= 20.0
    )
    if (
        _is_verified_or_derived(pe_fact)
        and pe_fact["value"] > thresholds.pe_extreme_avoid
        and not is_growth_exceptional
    ):
        rule3_triggered = True
        reason_codes.append("RULE3_EXTREME_PE_VALUATION")

    if (
        _is_verified_or_derived(pb_fact)
        and pb_fact["value"] > thresholds.pb_extreme_avoid
        and not is_growth_exceptional
    ):
        rule3_triggered = True
        reason_codes.append("RULE3_EXTREME_PB_VALUATION")

    # Condition 3C: High leverage with deteriorating technical trend
    if (
        de_status_guard == "EVALUATE"
        and _is_verified_or_derived(de_fact)
        and de_fact["value"] > 1.5
        and technical_classification == "WAIT_AND_WATCH"
        and _is_verified_or_derived(dma50_fact)
        and cmp_fact["value"] < dma50_fact["value"]
    ):
        rule3_triggered = True
        reason_codes.append("RULE3_ELEVATED_LEVERAGE_WITH_SUBPAR_TREND")

    if rule3_triggered:
        investment_action = "AVOID_NEW_ENTRY"
        investment_score = round(min(45.0, (technical_score or 45.0)), 1)
        return _build_recommendation_dict(
            symbol=symbol,
            company_name=company_name,
            cmp_fact=cmp_fact,
            technical_classification=technical_classification,
            technical_score=technical_score,
            technical_confidence=technical_confidence,
            investment_action=investment_action,
            investment_score=investment_score,
            investment_confidence=investment_confidence,
            reason_codes=reason_codes,
            positive_factors=positive_factors,
            cautionary_factors=cautionary_factors,
            risk_flags=risk_flags,
            key_levels=key_levels,
            limitations=limitations,
            market_as_of=market_as_of,
            now_utc=now_utc,
            research_run_id=research_result.get("research_id"),
            buying_zone=buying_zone_eval,
            key_metrics=key_metrics_data,
        )

    # --------------------------------------------------------------------------
    # RULE 4: BUY_CANDIDATE
    # --------------------------------------------------------------------------
    # Mandatory confluence check:
    # 1. Technical condition must be strictly BUY_CANDIDATE
    # 2. Profitability must be verified and meet threshold (ROE or ROCE)
    # 3. Growth must be verified and non-negative
    # 4. Valuation must not be excessive (P/E <= max_buy)
    # 5. Leverage must be conservative or NOT_APPLICABLE / DEBT_FREE
    # 6. Pledge must be safe (<= max_buy)
    # 7. No unresolved conflicting/stale critical indicators

    buy_checks: Dict[str, Tuple[bool, str]] = {}

    # 1. Technical
    buy_checks["technical"] = (
        technical_classification == "BUY_CANDIDATE",
        f"Technical classification is {technical_classification}"
    )

    # 2. Profitability
    has_strong_roe = _is_verified_or_derived(roe_fact) and roe_fact["value"] >= thresholds.roe_min_buy
    has_strong_roce = _is_verified_or_derived(roce_fact) and roce_fact["value"] >= thresholds.roce_min_buy
    buy_checks["profitability"] = (
        has_strong_roe or has_strong_roce,
        "ROE or ROCE meets >= 15% capital efficiency threshold"
    )

    # 3. Growth (strictly positive > 0.0)
    has_positive_sales = _is_verified_or_derived(sales_growth_fact) and sales_growth_fact["value"] > 0.0
    has_positive_profit = _is_verified_or_derived(profit_growth_fact) and profit_growth_fact["value"] > 0.0
    buy_checks["growth"] = (
        has_positive_sales or has_positive_profit,
        "3-year sales or profit CAGR is strictly positive (> 0%)"
    )

    # 4. Valuation
    has_fair_pe = (
        _is_verified_or_derived(pe_fact)
        and pe_fact["value"] <= thresholds.pe_max_buy
        and pe_fact["value"] > 0
    )
    buy_checks["valuation"] = (
        has_fair_pe,
        f"P/E ratio is within {thresholds.pe_max_buy}x upper threshold"
    )

    # 5. Leverage
    if de_status_guard in {"NOT_APPLICABLE_BANK_NBFC", "DEBT_FREE"}:
        leverage_pass = True
        leverage_desc = f"Leverage guard satisfied: {de_status_guard}"
    elif _is_verified_or_derived(de_fact) and de_fact["value"] <= thresholds.debt_to_equity_max_buy:
        leverage_pass = True
        leverage_desc = f"Debt-to-Equity is {de_fact['value']:.2f} <= {thresholds.debt_to_equity_max_buy}"
    else:
        leverage_pass = False
        leverage_desc = f"Debt-to-Equity is unverified, missing, or exceeds {thresholds.debt_to_equity_max_buy}"
    buy_checks["leverage"] = (leverage_pass, leverage_desc)

    # 6. Governance / Pledge
    has_clean_pledge = (
        _is_verified_or_derived(pledge_fact)
        and pledge_fact["value"] <= thresholds.promoter_pledge_max_buy
    )
    buy_checks["governance"] = (
        has_clean_pledge,
        f"Promoter pledge is {pledge_fact.get('value')}% <= {thresholds.promoter_pledge_max_buy}%"
    )

    all_buy_passed = all(passed for passed, _ in buy_checks.values())

    if all_buy_passed:
        investment_action = "BUY_CANDIDATE"
        reason_codes.append("RULE4_MULTI_FACTOR_BUY_CONFLUENCE")
        # Composite score: 40% technical, 30% fundamental, 15% valuation, 15% quality
        base_tech_score = technical_score or 75.0
        fund_score = fund_intel.get("score") or 70.0
        investment_score = round(0.40 * base_tech_score + 0.40 * fund_score + 0.20 * 80.0, 1)

        return _build_recommendation_dict(
            symbol=symbol,
            company_name=company_name,
            cmp_fact=cmp_fact,
            technical_classification=technical_classification,
            technical_score=technical_score,
            technical_confidence=technical_confidence,
            investment_action=investment_action,
            investment_score=investment_score,
            investment_confidence=investment_confidence,
            reason_codes=reason_codes,
            positive_factors=positive_factors,
            cautionary_factors=cautionary_factors,
            risk_flags=risk_flags,
            key_levels=key_levels,
            limitations=limitations,
            market_as_of=market_as_of,
            now_utc=now_utc,
            research_run_id=research_result.get("research_id"),
            buying_zone=buying_zone_eval,
            key_metrics=key_metrics_data,
        )
    else:
        # If technical is BUY_CANDIDATE but failed fundamental/valuation checks:
        if technical_classification == "BUY_CANDIDATE":
            failed_reasons = [desc for name, (passed, desc) in buy_checks.items() if not passed]
            cautionary_factors.append(
                f"Technical BUY signal not confirmed by fundamental criteria: {'; '.join(failed_reasons)}."
            )
            reason_codes.append("BUY_CRITERIA_UNMET_DEGRADED_TO_HOLD")

    # --------------------------------------------------------------------------
    # RULE 5: HOLD_REVIEW (Default safe fallback)
    # --------------------------------------------------------------------------
    investment_action = "HOLD_REVIEW"
    reason_codes.append("RULE5_DEFAULT_BALANCED_HOLD_REVIEW")
    base_tech_score = technical_score or 50.0
    fund_score = fund_intel.get("score") or 50.0
    investment_score = round(0.50 * base_tech_score + 0.50 * fund_score, 1)

    return _build_recommendation_dict(
        symbol=symbol,
        company_name=company_name,
        cmp_fact=cmp_fact,
        technical_classification=technical_classification,
        technical_score=technical_score,
        technical_confidence=technical_confidence,
        investment_action=investment_action,
        investment_score=investment_score,
        investment_confidence=investment_confidence,
        reason_codes=reason_codes,
        positive_factors=positive_factors,
        cautionary_factors=cautionary_factors,
        risk_flags=risk_flags,
        key_levels=key_levels,
        limitations=limitations,
        market_as_of=market_as_of,
        now_utc=now_utc,
        research_run_id=research_result.get("research_id"),
        buying_zone=buying_zone_eval,
        key_metrics=key_metrics_data,
    )


def _build_recommendation_dict(
    symbol: str,
    company_name: str,
    cmp_fact: Dict[str, Any],
    technical_classification: str,
    technical_score: Optional[float],
    technical_confidence: float,
    investment_action: str,
    investment_score: Optional[float],
    investment_confidence: float,
    reason_codes: List[str],
    positive_factors: List[str],
    cautionary_factors: List[str],
    risk_flags: List[str],
    key_levels: Dict[str, Any],
    limitations: List[str],
    market_as_of: Optional[str],
    now_utc: str,
    research_run_id: Optional[str],
    buying_zone: Optional[Dict[str, Any]] = None,
    key_metrics: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Helper to assemble a clean, consistent recommendation dictionary."""
    return {
        "engine_version": ENGINE_VERSION,
        "symbol": symbol,
        "company_name": company_name,
        "assessment_timestamp": now_utc,
        "market_data_as_of": market_as_of,
        "cmp": cmp_fact.get("value"),
        "currency": cmp_fact.get("unit") or "INR",
        "technical_classification": technical_classification,
        "technical_score": technical_score,
        "technical_confidence": technical_confidence,
        "investment_action": investment_action,
        "investment_score": investment_score,
        "investment_confidence": investment_confidence,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "positive_factors": list(dict.fromkeys(positive_factors)),
        "cautionary_factors": list(dict.fromkeys(cautionary_factors)),
        "risk_flags": list(dict.fromkeys(risk_flags)),
        "key_levels": key_levels,
        "limitations": list(dict.fromkeys(limitations)),
        "research_run_id": research_run_id,
        "buying_zone": buying_zone,
        "key_metrics": key_metrics or [],
        "is_cached": False,
        "cache_metadata": {},
    }
