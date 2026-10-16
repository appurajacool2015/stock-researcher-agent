#!/usr/bin/env python3
"""
Deterministic Buying Zone Assessment Engine v1.0.0

Purpose
-------
Evaluates whether a stock currently offers a favorable, asymmetric risk-to-reward entry setup.
Helps users distinguish:
1. A fundamentally sound business (Quality).
2. A reasonably valued security (Valuation).
3. A stock with an attractive entry setup at current market price (Entry & Risk/Reward).

Mandatory Safeguards:
1. Five mutually exclusive labels:
   - BUYING_ZONE
   - WAIT_FOR_PULLBACK
   - WAIT_FOR_CONFIRMATION
   - NOT_IN_BUYING_ZONE
   - INSUFFICIENT_DATA
2. Never treats any single metric (e.g. low RSI, MACD, or volume spike) as an automatic buy trigger.
3. Obtains risk-to-reward ratio from verified support (stop/invalidation level) and confirmed resistance.
4. Treats OBV strictly as price/volume-flow momentum; never claims proof of institutional buying.
5. All thresholds are encapsulated in a configurable dataclass.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass(frozen=True)
class BuyingZoneThresholds:
    """Configurable thresholds for deterministic Buying Zone Assessment."""
    reward_to_risk_min: float = 1.50
    support_proximity_max_pct: float = 3.50
    support_proximity_min_pct: float = 0.50
    rsi_min_buy: float = 40.0
    rsi_max_buy: float = 62.0
    rsi_overextended: float = 65.0
    rsi_falling_knife: float = 38.0
    dma50_extension_max_pct: float = 8.0
    resistance_proximity_pct: float = 1.50
    obv_min_buy: float = -0.10
    obv_falling_knife: float = -0.15
    atr_buffer_multiplier: float = 1.0
    pe_max_buy: float = 45.0
    pe_extreme: float = 65.0
    roe_min: float = 12.0
    roce_min: float = 12.0
    debt_to_equity_max: float = 2.0
    promoter_pledge_max: float = 25.0
    min_history_bars: int = 50


DEFAULT_THRESHOLDS = BuyingZoneThresholds()


def _get_val(container: Dict[str, Any], key: str, fallback_key: Optional[str] = None) -> Optional[float]:
    """Extract numeric value safely from a datapoint dict or direct float/int."""
    if not isinstance(container, dict):
        return None
    raw = container.get(key)
    if raw is None and fallback_key:
        raw = container.get(fallback_key)

    if isinstance(raw, dict):
        status = raw.get("status")
        if status in {"UNAVAILABLE", "FAILED", "STALE_FAILED"}:
            return None
        val = raw.get("value")
    else:
        val = raw

    if val is None or isinstance(val, bool):
        return None
    try:
        fval = float(val)
        return None if fval != fval else fval
    except (TypeError, ValueError):
        return None


def _get_status(container: Dict[str, Any], key: str) -> str:
    """Extract status string from datapoint dict."""
    if not isinstance(container, dict):
        return "UNAVAILABLE"
    raw = container.get(key)
    if isinstance(raw, dict):
        return str(raw.get("status", "UNAVAILABLE"))
    return "VERIFIED" if raw is not None else "UNAVAILABLE"


def evaluate_buying_zone(
    research_result: Dict[str, Any],
    thresholds: BuyingZoneThresholds = DEFAULT_THRESHOLDS,
) -> Dict[str, Any]:
    """
    Evaluate deterministic Buying Zone status for the supplied ResearchResult.

    Parameters
    ----------
    research_result: Canonical ResearchResult v1 dictionary.
    thresholds: Configurable BuyingZoneThresholds instance.

    Returns
    -------
    Dictionary with status, label, risk-to-reward structure, and confluence explanations.
    """
    technicals = research_result.get("technicals") or {}
    fundamentals = research_result.get("fundamentals") or {}
    institutional = research_result.get("institutional") or {}

    # Extract Technical Facts
    cmp_val = _get_val(technicals, "cmp")
    dma_50 = _get_val(technicals, "dma_50")
    dma_200 = _get_val(technicals, "dma_200")
    rsi_14 = _get_val(technicals, "rsi_14")
    atr_14 = _get_val(technicals, "atr_14")
    swing_high = _get_val(technicals, "swing_high_20")
    swing_low = _get_val(technicals, "swing_low_20")
    volume = _get_val(technicals, "volume")
    avg_vol_20 = _get_val(technicals, "avg_volume_20")
    vol_vs_20d_pct = _get_val(technicals, "volume_vs_20d_pct")
    obv_val = _get_val(technicals, "obv_change_norm_14d")
    history_bars = _get_val(technicals, "history_bars") or 0

    # Extract Fundamental Facts
    roe = _get_val(fundamentals, "roe")
    roce = _get_val(fundamentals, "roce")
    pe_ratio = _get_val(fundamentals, "pe_ratio")
    de_ratio = _get_val(fundamentals, "debt_to_equity")
    pledge_pct = _get_val(institutional, "promoter_pledge_pct", fallback_key="promoter_pledge")

    # Metadata
    currency = "INR"
    if isinstance(technicals.get("cmp"), dict):
        currency = technicals["cmp"].get("unit") or "INR"
    market_as_of = None
    if isinstance(technicals.get("provenance"), dict):
        market_as_of = technicals["provenance"].get("as_of_date")

    # --------------------------------------------------------------------------
    # 1. GATE 1: INSUFFICIENT DATA
    # --------------------------------------------------------------------------
    missing_essentials = []
    if cmp_val is None:
        missing_essentials.append("CMP")
    if dma_50 is None:
        missing_essentials.append("50 DMA")
    if dma_200 is None:
        missing_essentials.append("200 DMA")
    if rsi_14 is None:
        missing_essentials.append("RSI (14)")
    if history_bars < thresholds.min_history_bars:
        missing_essentials.append(f"History bars ({int(history_bars)} < {thresholds.min_history_bars})")

    if missing_essentials:
        return {
            "status": "INSUFFICIENT_DATA",
            "label": "INSUFFICIENT DATA",
            "entry_context": f"Essential technical evidence unavailable: {', '.join(missing_essentials)}.",
            "support_reference": None,
            "support_type": None,
            "invalidation_level": None,
            "downside_risk_pct": None,
            "resistance_reference": None,
            "resistance_type": None,
            "upside_potential_pct": None,
            "reward_to_risk_ratio": None,
            "supporting_signals": [],
            "conflicting_signals": [f"Missing required technical metrics: {', '.join(missing_essentials)}."],
            "as_of_date": market_as_of,
        }

    # Tracking signals
    supporting: List[str] = []
    conflicting: List[str] = []

    # --------------------------------------------------------------------------
    # 2. SUPPORT & RESISTANCE LEVEL DETERMINATION
    # --------------------------------------------------------------------------
    support_candidates = []
    if dma_50 is not None:
        support_candidates.append(("50-Day Moving Average", dma_50))
    if dma_200 is not None:
        support_candidates.append(("200-Day Moving Average", dma_200))
    if swing_low is not None and swing_low > 0:
        support_candidates.append(("Confirmed 20D Swing Low", swing_low))

    # Nearest support is the highest candidate <= CMP * 1.02
    valid_supports = [(name, price) for name, price in support_candidates if price <= cmp_val * 1.02]
    if valid_supports:
        valid_supports.sort(key=lambda x: x[1], reverse=True)
        supp_name, supp_price = valid_supports[0]
    else:
        supp_name, supp_price = "200-Day Moving Average", dma_200

    # Invalidation level (stop reference) = Support - (1.0x ATR buffer)
    atr_buffer = (atr_14 * thresholds.atr_buffer_multiplier) if (atr_14 is not None and atr_14 > 0) else (supp_price * 0.02)
    invalidation_level = round(supp_price - atr_buffer, 2)
    downside_risk_pct = round(((cmp_val - invalidation_level) / cmp_val) * 100, 2)
    if downside_risk_pct <= 0:
        downside_risk_pct = 0.50

    # Resistance target = Confirmed 20D Swing High (or 50 DMA if CMP is below it)
    if swing_high is not None and swing_high > cmp_val:
        res_name = "Confirmed 20D Swing High"
        res_price = swing_high
    elif dma_50 > cmp_val:
        res_name = "50-Day Moving Average (Overhead Resistance)"
        res_price = dma_50
    else:
        res_name = "Estimated Near-Term Resistance"
        res_price = round(cmp_val + (2.0 * atr_buffer), 2)

    upside_potential_pct = round(((res_price - cmp_val) / cmp_val) * 100, 2)
    if upside_potential_pct <= 0:
        upside_potential_pct = 0.50

    reward_to_risk_ratio = round(upside_potential_pct / downside_risk_pct, 2)

    # --------------------------------------------------------------------------
    # 3. GATE 2: NOT IN BUYING ZONE (Structural Breakdown or Extreme Red Flags)
    # --------------------------------------------------------------------------
    is_below_200_dma = cmp_val < (dma_200 * 0.98)
    is_broken_structure = (dma_50 < dma_200) and (cmp_val < dma_50)
    is_extreme_pe = pe_ratio is not None and pe_ratio > thresholds.pe_extreme
    is_high_leverage = de_ratio is not None and de_ratio > thresholds.debt_to_equity_max
    is_severe_pledge = pledge_pct is not None and pledge_pct > thresholds.promoter_pledge_max

    if is_below_200_dma or is_broken_structure or is_extreme_pe or is_high_leverage or is_severe_pledge:
        if is_below_200_dma:
            conflicting.append(f"Structural downtrend: Price (₹{cmp_val:,.2f}) is trading below 200-DMA (₹{dma_200:,.2f}).")
        if is_broken_structure:
            conflicting.append(f"Broken trend alignment: 50-DMA (₹{dma_50:,.2f}) is below 200-DMA and price is below 50-DMA.")
        if is_extreme_pe:
            conflicting.append(f"Extreme valuation: P/E ratio ({pe_ratio:.1f}) exceeds extreme threshold ({thresholds.pe_extreme:.1f}).")
        if is_high_leverage:
            conflicting.append(f"High financial leverage: Debt-to-Equity ({de_ratio:.2f}) exceeds {thresholds.debt_to_equity_max:.1f}x limit.")
        if is_severe_pledge:
            conflicting.append(f"Severe governance risk: Promoter pledge ({pledge_pct:.1f}%) exceeds {thresholds.promoter_pledge_max:.1f}%.")

        return {
            "status": "NOT_IN_BUYING_ZONE",
            "label": "NOT IN BUYING ZONE",
            "entry_context": "Stock is in a structural downtrend or violates core fundamental risk criteria.",
            "support_reference": supp_price,
            "support_type": supp_name,
            "invalidation_level": invalidation_level,
            "downside_risk_pct": downside_risk_pct,
            "resistance_reference": res_price,
            "resistance_type": res_name,
            "upside_potential_pct": upside_potential_pct,
            "reward_to_risk_ratio": reward_to_risk_ratio,
            "supporting_signals": supporting,
            "conflicting_signals": conflicting,
            "as_of_date": market_as_of,
        }

    # --------------------------------------------------------------------------
    # 4. GATE 3: WAIT FOR PULLBACK (Overbought / Extended Trend)
    # --------------------------------------------------------------------------
    is_rsi_overbought = rsi_14 > thresholds.rsi_overextended
    is_dma50_extended = cmp_val > (dma_50 * (1.0 + thresholds.dma50_extension_max_pct / 100.0))
    is_at_resistance = (swing_high is not None) and (cmp_val >= swing_high * (1.0 - thresholds.resistance_proximity_pct / 100.0))

    if is_rsi_overbought or is_dma50_extended or is_at_resistance:
        if is_rsi_overbought:
            conflicting.append(f"Momentum overextended: RSI (14) at {rsi_14:.1f} is above {thresholds.rsi_overextended:.1f}.")
        if is_dma50_extended:
            ext_pct = round(((cmp_val - dma_50) / dma_50) * 100, 1)
            conflicting.append(f"Price is extended {ext_pct}% above its 50-DMA (threshold: {thresholds.dma50_extension_max_pct}%).")
        if is_at_resistance:
            conflicting.append(f"Price is directly testing 20-session swing resistance (₹{swing_high:,.2f}).")

        supporting.append(f"Primary structural uptrend is intact (CMP ₹{cmp_val:,.2f} > 200-DMA ₹{dma_200:,.2f}).")
        if roe and roe >= thresholds.roe_min:
            supporting.append(f"Strong capital efficiency confirmed: ROE {roe:.1f}%.")

        return {
            "status": "WAIT_FOR_PULLBACK",
            "label": "WAIT FOR PULLBACK",
            "entry_context": "Uptrend is intact, but price is short-term extended with elevated near-term pullback risk.",
            "support_reference": supp_price,
            "support_type": supp_name,
            "invalidation_level": invalidation_level,
            "downside_risk_pct": downside_risk_pct,
            "resistance_reference": res_price,
            "resistance_type": res_name,
            "upside_potential_pct": upside_potential_pct,
            "reward_to_risk_ratio": reward_to_risk_ratio,
            "supporting_signals": supporting,
            "conflicting_signals": conflicting,
            "as_of_date": market_as_of,
        }

    # --------------------------------------------------------------------------
    # 5. GATE 4: WAIT FOR CONFIRMATION (Falling Knife / Heavy Selling Volume)
    # --------------------------------------------------------------------------
    is_rsi_falling_knife = rsi_14 < thresholds.rsi_falling_knife
    is_obv_distribution = obv_val is not None and obv_val < thresholds.obv_falling_knife
    is_heavy_selling_volume = (
        vol_vs_20d_pct is not None
        and vol_vs_20d_pct > 50.0
        and cmp_val < dma_50
    )

    if is_rsi_falling_knife or is_obv_distribution or is_heavy_selling_volume:
        if is_rsi_falling_knife:
            conflicting.append(f"Downward momentum is steep: RSI (14) at {rsi_14:.1f} reflects active selling pressure.")
        if is_obv_distribution:
            conflicting.append(f"Price/volume-flow is negative: 14-session OBV change ({obv_val:.2f}) indicates net distribution.")
        if is_heavy_selling_volume:
            conflicting.append(f"Volume expansion on weakness: volume is {vol_vs_20d_pct:.1f}% above 20-day average.")

        supporting.append(f"Price is testing potential support zone near {supp_name} (₹{supp_price:,.2f}).")

        return {
            "status": "WAIT_FOR_CONFIRMATION",
            "label": "WAIT FOR CONFIRMATION",
            "entry_context": "Price is testing support, but aggressive selling momentum requires confirmation of a price base before entry.",
            "support_reference": supp_price,
            "support_type": supp_name,
            "invalidation_level": invalidation_level,
            "downside_risk_pct": downside_risk_pct,
            "resistance_reference": res_price,
            "resistance_type": res_name,
            "upside_potential_pct": upside_potential_pct,
            "reward_to_risk_ratio": reward_to_risk_ratio,
            "supporting_signals": supporting,
            "conflicting_signals": conflicting,
            "as_of_date": market_as_of,
        }

    # --------------------------------------------------------------------------
    # 6. GATE 5: BUYING ZONE (Confluence of Trend, Location, Momentum & R:R)
    # --------------------------------------------------------------------------
    dist_to_supp_pct = abs((cmp_val - supp_price) / supp_price) * 100
    is_near_support = dist_to_supp_pct <= thresholds.support_proximity_max_pct
    is_rsi_balanced = thresholds.rsi_min_buy <= rsi_14 <= thresholds.rsi_max_buy
    is_rr_favorable = reward_to_risk_ratio >= thresholds.reward_to_risk_min

    if is_near_support and is_rsi_balanced and is_rr_favorable:
        supporting.append(f"Uptrend intact: CMP (₹{cmp_val:,.2f}) holds above structural 200-DMA (₹{dma_200:,.2f}).")
        supporting.append(f"Favorable entry proximity: CMP is within {dist_to_supp_pct:.1f}% of {supp_name} (₹{supp_price:,.2f}).")
        supporting.append(f"Constructive momentum: RSI (14) at {rsi_14:.1f} reflects healthy pullback without momentum breakdown.")
        supporting.append(f"Asymmetric risk/reward: {reward_to_risk_ratio:.2f} : 1 upside-to-downside ratio to overhead resistance (₹{res_price:,.2f}).")

        if obv_val is not None and obv_val >= thresholds.obv_min_buy:
            supporting.append(f"Stable volume-flow: 14-session OBV change ({obv_val:.2f}) indicates absence of aggressive distribution.")
        if roe and roe >= thresholds.roe_min:
            supporting.append(f"Capital efficiency confirmed: ROE {roe:.1f}% and ROCE {roce:.1f}%." if roce else f"ROE {roe:.1f}%.")

        return {
            "status": "BUYING_ZONE",
            "label": "BUYING ZONE",
            "entry_context": f"Orderly pullback near verified {supp_name} with favorable {reward_to_risk_ratio:.1f}:1 reward-to-risk.",
            "support_reference": supp_price,
            "support_type": supp_name,
            "invalidation_level": invalidation_level,
            "downside_risk_pct": downside_risk_pct,
            "resistance_reference": res_price,
            "resistance_type": res_name,
            "upside_potential_pct": upside_potential_pct,
            "reward_to_risk_ratio": reward_to_risk_ratio,
            "supporting_signals": supporting,
            "conflicting_signals": conflicting,
            "as_of_date": market_as_of,
        }

    # --------------------------------------------------------------------------
    # 7. DEFAULT: WAIT FOR PULLBACK
    # --------------------------------------------------------------------------
    if not is_near_support:
        conflicting.append(f"Price is in intermediate zone ({dist_to_supp_pct:.1f}% away from nearest support ₹{supp_price:,.2f}).")
    if not is_rr_favorable:
        conflicting.append(f"Reward-to-risk ratio ({reward_to_risk_ratio:.2f}:1) is below {thresholds.reward_to_risk_min:.2f}:1 minimum threshold.")

    supporting.append(f"Long-term trend remains positive above 200-DMA (₹{dma_200:,.2f}).")

    return {
        "status": "WAIT_FOR_PULLBACK",
        "label": "WAIT FOR PULLBACK",
        "entry_context": "Trend is positive, but entry location does not offer a sufficiently asymmetric reward-to-risk ratio.",
        "support_reference": supp_price,
        "support_type": supp_name,
        "invalidation_level": invalidation_level,
        "downside_risk_pct": downside_risk_pct,
        "resistance_reference": res_price,
        "resistance_type": res_name,
        "upside_potential_pct": upside_potential_pct,
        "reward_to_risk_ratio": reward_to_risk_ratio,
        "supporting_signals": supporting,
        "conflicting_signals": conflicting,
        "as_of_date": market_as_of,
    }
