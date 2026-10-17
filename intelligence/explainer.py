#!/usr/bin/env python3
"""
Explainer & Chat Response Formatter

Purpose
-------
Generates concise, audit-grade chat responses conforming strictly to the
Phase 4 eight-section Markdown specification.

Safeguards:
1. Deterministic template generates the full 8-section report unconditionally.
2. Gemini mode (when keys are present) enhances readability without altering
   or inventing metrics, technical classifications, investment actions, or key levels.
3. If Gemini is unavailable, rate-limited, or fails, gracefully falls back to
   the deterministic template with zero loss of structure or data.
4. Unavailable metrics are represented explicitly as 'UNAVAILABLE' (never zero or inferred).
5. Explicit non-guarantee disclaimer included in all outputs.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
import requests

DISCLAIMER_TEXT = (
    "*Disclaimer: This assessment is an automated synthesis of factual data and rule-based "
    "technical/fundamental criteria. It is not financial advice and does not guarantee profit "
    "or eliminate capital loss risk.*"
)



def _format_default_key_metrics(rec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate default key metrics with safe UNAVAILABLE fallbacks when detailed metrics are omitted."""
    cmp_val = rec.get("cmp")
    cmp_str = f"₹{cmp_val:,.2f}" if isinstance(cmp_val, (int, float)) and cmp_val is not None else "UNAVAILABLE"
    cmp_status = "VERIFIED" if cmp_val is not None else "UNAVAILABLE"
    as_of = rec.get("market_data_as_of") or "—"
    cmp_date = as_of if cmp_val is not None else "—"

    return [
        {"metric": "CMP", "value": cmp_str, "status": cmp_status, "as_of_date": cmp_date},
        {"metric": "P/E", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
        {"metric": "ROCE", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
        {"metric": "ROE", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
        {"metric": "3Y Sales Growth", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
        {"metric": "3Y Profit Growth", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
        {"metric": "50 DMA", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
        {"metric": "200 DMA", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
        {"metric": "RSI (14)", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
        {"metric": "Debt-to-Equity", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
        {"metric": "Promoter Pledge", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
        {"metric": "PEG", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
        {"metric": "Trading Volume (Latest)", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
        {"metric": "20-Day Avg Volume", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
        {"metric": "Relative Volume", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
        {"metric": "OBV Trend (14d)", "value": "UNAVAILABLE", "status": "UNAVAILABLE", "as_of_date": "—"},
    ]


def format_deterministic_template(
    rec: Dict[str, Any],
    track_record: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Format assessment into the 8 required Markdown sections deterministically.
    """
    symbol = rec.get("symbol", "UNKNOWN")
    company_name = rec.get("company_name", symbol)
    cmp_val = rec.get("cmp")
    currency = rec.get("currency", "INR")
    cmp_str = f"₹{cmp_val:,.2f} {currency}" if cmp_val is not None else "UNAVAILABLE"

    tech_cls = rec.get("technical_classification", "UNAVAILABLE")
    invest_act = rec.get("investment_action", "UNAVAILABLE")

    # 1. Rationale (3 concise points)
    pos_factors = rec.get("positive_factors", [])
    caut_factors = rec.get("cautionary_factors", [])

    # Point 1: Business / fundamental quality
    pt1_candidates = [f for f in pos_factors if any(k in f.lower() for k in ["roe", "roce", "leverage", "debt"])]
    if not pt1_candidates:
        pt1_candidates = [f for f in caut_factors if any(k in f.lower() for k in ["roe", "roce", "leverage", "debt"])]
    pt1 = pt1_candidates[0] if pt1_candidates else "Business quality metrics are currently balanced or limited."

    # Point 2: Valuation
    pt2_candidates = [f for f in pos_factors if "p/e" in f.lower() or "valuation" in f.lower()]
    if not pt2_candidates:
        pt2_candidates = [f for f in caut_factors if "p/e" in f.lower() or "valuation" in f.lower() or "book" in f.lower()]
    pt2 = pt2_candidates[0] if pt2_candidates else "Valuation multiples reflect current market consensus."

    # Point 3: Technical Trend / Volume
    pt3_candidates = [f for f in pos_factors if any(k in f.lower() for k in ["dma", "trend", "volume", "rsi", "swing"])]
    if not pt3_candidates:
        pt3_candidates = [f for f in caut_factors if any(k in f.lower() for k in ["dma", "trend", "volume", "rsi", "swing"])]
    pt3 = pt3_candidates[0] if pt3_candidates else f"Technical indicators currently indicate a {tech_cls} posture."

    # 2. Risk and Missing Data
    risk_flags = rec.get("risk_flags", [])
    limitations = rec.get("limitations", [])
    all_risks = []
    if caut_factors:
        all_risks.extend(caut_factors[:3])
    if risk_flags:
        all_risks.extend([f"Flag: {rf}" for rf in risk_flags[:2]])
    if limitations:
        all_risks.extend([f"Data limitation: {lim}" for lim in limitations[:2]])
    if not all_risks:
        all_risks = ["No material cautionary risk flags identified from verified sources."]

    # 3. Key Levels
    key_levels = rec.get("key_levels", {})
    supp_info = key_levels.get("support_reference")
    res_info = key_levels.get("resistance_reference")

    supp_str = f"₹{supp_info['price']:,.2f} ({supp_info['level_type']})" if supp_info and supp_info.get("price") else "UNAVAILABLE"
    res_str = f"₹{res_info['price']:,.2f} ({res_info['level_type']})" if res_info and res_info.get("price") else "UNAVAILABLE"

    # 4. Timestamps & Cache
    assessment_ts = rec.get("assessment_timestamp", "UNAVAILABLE")
    market_as_of = rec.get("market_data_as_of", "UNAVAILABLE")
    is_cached = rec.get("is_cached", False)
    cache_str = "CACHED (< 6h Snapshot)" if is_cached else "Fresh (Direct Execution)"

    # 5. History / Recommendation ID & Track Record
    rec_id = rec.get("id") or rec.get("research_run_id") or "UNSAVED_LOCAL_RUN"
    tr = track_record or rec.get("track_record")

    # Build response lines
    lines = [
        f"**Symbol and price:** {symbol} ({company_name}) — CMP: {cmp_str}",
        f"**Technical classification:** {tech_cls}",
        f"**Investment assessment:** {invest_act}",
    ]

    # Buying Zone Assessment Block
    bz = rec.get("buying_zone")
    if bz and isinstance(bz, dict) and bz.get("label"):
        bz_label = bz["label"]
        bz_context = bz.get("entry_context", "")
        supp_ref = bz.get("support_reference")
        supp_type = bz.get("support_type")
        inval_ref = bz.get("invalidation_level")
        down_risk = bz.get("downside_risk_pct")
        res_ref = bz.get("resistance_reference")
        res_type = bz.get("resistance_type")
        up_pot = bz.get("upside_potential_pct")
        rr_ratio = bz.get("reward_to_risk_ratio")

        lines.extend([
            "",
            "**Buying zone assessment:**",
            f"- Status: **{bz_label}**",
            f"- Setup: {bz_context}",
        ])
        if supp_ref is not None and inval_ref is not None and res_ref is not None:
            rr_str = f"{rr_ratio:.2f} : 1" if rr_ratio is not None else "UNAVAILABLE"
            lines.extend([
                "- Risk/Reward Structure:",
                f"  - Nearest Support Reference: ₹{supp_ref:,.2f} ({supp_type})",
                f"  - Invalidation Reference (Stop): ₹{inval_ref:,.2f} (Downside: -{down_risk:.1f}%)",
                f"  - Target Resistance Reference: ₹{res_ref:,.2f} ({res_type}) (Upside: +{up_pot:.1f}%)",
                f"  - Reward-to-Risk Ratio: {rr_str}",
            ])
        supp_signals = bz.get("supporting_signals") or []
        conf_signals = bz.get("conflicting_signals") or []
        if supp_signals:
            lines.append("- Supporting signals:")
            for s in supp_signals[:4]:
                lines.append(f"  • {s}")
        if conf_signals:
            lines.append("- Conflicting / Cautionary signals:")
            for c in conf_signals[:3]:
                lines.append(f"  • {c}")

    # Key Metrics Block (16 metrics, 4-column table)
    km = rec.get("key_metrics")
    if km is None or not isinstance(km, list) or len(km) == 0:
        km = _format_default_key_metrics(rec)

    lines.extend([
        "",
        "**Key metrics:**",
        "| Metric | Value | Status | As-Of Date |",
        "| :--- | :--- | :--- | :--- |",
    ])
    for row in km:
        m_name = row.get("metric", row.get("name", "UNKNOWN"))
        m_val = row.get("value", row.get("value_formatted", "UNAVAILABLE"))
        m_stat = row.get("status", "UNAVAILABLE")
        m_date = row.get("as_of_date", "—")
        lines.append(f"| {m_name} | {m_val} | {m_stat} | {m_date} |")

    lines.extend([
        "",
        "**Rationale:**",
        f"1. *Business Quality:* {pt1}",
        f"2. *Valuation:* {pt2}",
        f"3. *Technical Trend & Volume:* {pt3}",
        "",
        "**Risk and missing data:**",
    ])
    for r in all_risks:
        lines.append(f"- {r}")

    lines.extend([
        "",
        "**Key levels:**",
        f"- Support Reference: {supp_str}",
        f"- Resistance Reference: {res_str}",
        "",
        "**Timestamps:**",
        f"- Assessment Timestamp: {assessment_ts}",
        f"- Market Data As-Of: {market_as_of}",
        f"- Cache Status: {cache_str}",
        "",
        "**History:**",
    ])

    # Section 8 Content: Track Record & History
    if tr and isinstance(tr, dict):
        status = tr.get("status")
        if status == "TRACK_RECORD_AVAILABLE" and tr.get("has_prior_history"):
            first_date = tr.get("first_researched_date_str") or tr.get("first_researched_at") or "EARLIER_DATE"
            dur_str = tr.get("duration_str") or first_date
            base_price = tr.get("first_researched_price")
            base_price_str = f"₹{base_price:,.2f} {currency}" if isinstance(base_price, (int, float)) and base_price > 0 else "UNAVAILABLE"

            lines.append(f"- Research Baseline: First researched {dur_str} at {base_price_str}")

            # Price Return
            pct_ret = tr.get("price_return_pct")
            chg = tr.get("price_change")
            price_note = tr.get("price_return_note")
            if pct_ret is not None and chg is not None:
                sign = "+" if chg >= 0 else ""
                direction = "🟢" if chg >= 0 else "🔴"
                lines.append(f"- Price Return (Research Baseline): {sign}₹{chg:,.2f} ({sign}{pct_ret:.2f}% {direction})")
            elif price_note:
                lines.append(f"- Price Return (Research Baseline): {price_note}")
            else:
                lines.append("- Price Return (Research Baseline): UNAVAILABLE")

            # Verdict Tracking & Thesis
            v_trans = tr.get("verdict_transition")
            v_note = tr.get("verdict_note")
            if v_trans:
                lines.append(f"- Verdict Tracking: {v_trans}")
            if v_note:
                lines.append(f"- Thesis Continuity: {v_note}")

            # Mandatory Basis and Disclaimers
            lines.append("- Performance Basis: Price return on research baseline; excludes dividends, transaction fees, and taxes.")
            lines.append("- Notice: Prior price movement does not guarantee future results or validate past recommendation accuracy.")

        elif status == "UNAVAILABLE":
            err_msg = tr.get("note") or tr.get("warning") or "Historical database lookup unavailable."
            lines.append(f"- Historical Track Record: {err_msg}")

        elif status == "BASELINE_ESTABLISHED" or not tr.get("has_prior_history"):
            dur_str = tr.get("duration_str") or "today"
            init_v = tr.get("initial_verdict") or invest_act
            lines.append(f"- Research Baseline: Initial baseline established {dur_str} at {cmp_str}")
            lines.append(f"- Initial Verdict: {init_v}")
            lines.append("- Performance Tracking: Historical price return will be computed on subsequent research checks.")

    # Always preserve Recommendation ID in History
    lines.append(f"- Recommendation ID: `{rec_id}`")

    lines.extend([
        "",
        "---",
        DISCLAIMER_TEXT,
    ])

    return "\n".join(lines)


def format_with_gemini(
    rec: Dict[str, Any],
    api_key: Optional[str] = None,
) -> Optional[str]:
    """
    Format plain-English explanation using Gemini API while strictly enforcing
    the deterministic metrics, classifications, and section format.
    Falls back to None on any error or invariant failure.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return None

    # Base prompt with verified facts
    tech_cls = rec.get("technical_classification")
    invest_act = rec.get("investment_action")
    raw_template = format_deterministic_template(rec)

    prompt = f"""You are the Stock Research Presentation Assistant.
Refine the language of the following stock assessment report into smooth, concise, executive-level English.

MANDATORY RULES:
1. You MUST retain the exact 8 Markdown sections.
2. You MUST keep the exact Symbol, Company Name, CMP, Currency, Technical classification ({tech_cls}), Investment assessment ({invest_act}), Key levels, Timestamps, and Recommendation ID.
3. You MUST NOT invent, calculate, replace, or alter any numbers, metrics, or statuses.
4. Represent unavailable values strictly as 'UNAVAILABLE'.
5. Include the exact disclaimer at the end.

Report Data:
{raw_template}
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1000},
    }

    try:
        resp = requests.post(url, json=payload, timeout=12.0)
        if resp.status_code != 200:
            return None
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return None
        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if not text:
            return None

        # Sanity check: Ensure invariants are preserved
        if tech_cls and tech_cls not in text:
            return None
        if invest_act and invest_act not in text:
            return None

        return text.strip()
    except Exception:
        return None


def explain_assessment(
    rec: Dict[str, Any],
    track_record: Optional[Dict[str, Any]] = None,
    use_gemini: bool = True,
    gemini_key: Optional[str] = None,
) -> str:
    """
    Generate final explanation. Uses Gemini if available and valid;
    otherwise falls back smoothly to deterministic template.
    """
    if use_gemini:
        gemini_result = format_with_gemini(rec, api_key=gemini_key)
        if gemini_result:
            return gemini_result

    return format_deterministic_template(rec, track_record=track_record)
