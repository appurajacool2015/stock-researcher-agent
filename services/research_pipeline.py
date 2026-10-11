#!/usr/bin/env python3

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[1]

# Project structure:
#
# stock-intelligence/
# ├── schemas/
# │   └── research-result.v1.schema.json
# └── stock-researcher/
#     ├── services/
#     ├── adapters/
#     └── output/
#
# Therefore BASE_DIR.parent / schemas is correct.

LOCAL_SCHEMA_PATH = (
    BASE_DIR
    / "schemas"
    / "research-result.v1.schema.json"
)

FALLBACK_SCHEMA_PATH = (
    BASE_DIR.parent
    / "schemas"
    / "research-result.v1.schema.json"
)

SCHEMA_PATH = (
    LOCAL_SCHEMA_PATH
    if LOCAL_SCHEMA_PATH.exists()
    else FALLBACK_SCHEMA_PATH
)

OUTPUT_DIR = (
    BASE_DIR
    / "output"
)


# ============================================================
# ADAPTER IMPORTS
# ============================================================

from adapters.screener import ScreenerAdapter
from adapters.market_data import MarketDataAdapter
from adapters.news import NewsAdapter


# ============================================================
# OPTIONAL JSONSCHEMA
# ============================================================

try:
    import jsonschema
except ImportError:
    jsonschema = None


# ============================================================
# TIME HELPERS
# ============================================================

def utc_now() -> str:
    """
    Return current UTC timestamp in ISO-8601 format.
    """
    return datetime.now(timezone.utc).isoformat()


def get_adapter_as_of_date(
    adapter_data: Dict[str, Any],
) -> Optional[str]:
    """
    Extract an adapter-level as-of date.

    Used primarily by market_data where the entire
    daily technical dataset corresponds to the latest
    available trading date.
    """

    value = adapter_data.get("as_of_date")

    if value:
        return str(value)

    return None


def get_screener_as_of_dates(
    screener_data: Dict[str, Any],
) -> Dict[str, Optional[str]]:
    """
    Extract block-level as-of dates produced by the
    Screener adapter.

    Expected adapter structure:

        "as_of_dates": {
            "fundamentals": "2026-03-31",
            "institutional": "2026-06-30"
        }

    Missing values are returned as None.
    """

    raw = screener_data.get(
        "as_of_dates",
        {},
    )

    if not isinstance(raw, dict):
        return {
            "fundamentals": None,
            "institutional": None,
        }

    return {
        "fundamentals": (
            str(raw["fundamentals"])
            if raw.get("fundamentals")
            else None
        ),
        "institutional": (
            str(raw["institutional"])
            if raw.get("institutional")
            else None
        ),
    }


# ============================================================
# DATAPOINT HELPERS
# ============================================================

def datapoint(
    value: Any,
    unit: str,
    status: str,
    source: str,
    source_url: Optional[str] = None,
    retrieved_at: Optional[str] = None,
    as_of_date: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a standard ResearchResult data point.
    """

    return {
        "value": value,
        "unit": unit,
        "status": status,
        "provenance": {
            "source": source,
            "source_url": source_url,
            "retrieved_at": retrieved_at,
            "as_of_date": as_of_date,
        },
        "conflicting_values": [],
        "notes": notes,
    }


def block_provenance(
    source: str,
    source_url: Optional[str],
    retrieved_at: str,
    as_of_date: Optional[str],
) -> Dict[str, Any]:
    """
    Create block-level provenance.

    This is deliberately separate from individual
    datapoint provenance.

    Example:

        fundamentals.provenance
        technicals.provenance
        institutional.provenance
    """

    return {
        "source": source,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "as_of_date": as_of_date,
    }


def verified_or_unavailable(
    value: Any,
    unit: str,
    source: str,
    source_url: Optional[str],
    retrieved_at: str,
    as_of_date: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convert an adapter value into VERIFIED or UNAVAILABLE.
    """

    if value is None:
        return datapoint(
            value=None,
            unit=unit,
            status="UNAVAILABLE",
            source=source,
            source_url=source_url,
            retrieved_at=retrieved_at,
            as_of_date=as_of_date,
            notes=notes,
        )

    return datapoint(
        value=value,
        unit=unit,
        status="VERIFIED",
        source=source,
        source_url=source_url,
        retrieved_at=retrieved_at,
        as_of_date=as_of_date,
        notes=notes,
    )


def derived_datapoint(
    value: Any,
    unit: str,
    source: str,
    source_url: Optional[str],
    retrieved_at: str,
    as_of_date: Optional[str],
    notes: str,
) -> Dict[str, Any]:
    """
    Create a DERIVED data point.
    """

    if value is None:
        return datapoint(
            value=None,
            unit=unit,
            status="UNAVAILABLE",
            source=source,
            source_url=source_url,
            retrieved_at=retrieved_at,
            as_of_date=as_of_date,
            notes=notes,
        )

    return datapoint(
        value=value,
        unit=unit,
        status="DERIVED",
        source=source,
        source_url=source_url,
        retrieved_at=retrieved_at,
        as_of_date=as_of_date,
        notes=notes,
    )


# ============================================================
# STATUS COUNTING
# ============================================================

def count_statuses(
    result: Dict[str, Any],
) -> Dict[str, int]:
    """
    Count all ResearchResult data-point statuses.
    """

    counts = {
        "verified": 0,
        "derived": 0,
        "unavailable": 0,
        "stale": 0,
        "conflicting": 0,
        "failed": 0,
    }

    def walk(value: Any) -> None:

        if isinstance(value, dict):

            if (
                "value" in value
                and "status" in value
                and isinstance(
                    value["status"],
                    str,
                )
            ):

                status = value[
                    "status"
                ].lower()

                if status in counts:
                    counts[status] += 1

                return

            for child in value.values():
                walk(child)

        elif isinstance(value, list):

            for child in value:
                walk(child)

    walk(result)

    return counts


# ============================================================
# NORMALIZATION
# ============================================================

def build_research_result(
    screener_data: Dict[str, Any],
    market_data: Dict[str, Any],
    news_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Convert Screener + Market Data adapter output
    into ResearchResult v1.

    Important provenance model:

        Screener:
          fundamentals -> fundamentals as-of date
          institutional -> institutional as-of date

        Market Data:
          technicals -> market-data as-of date
    """

    requested_at = utc_now()

    # --------------------------------------------------------
    # Retrieval timestamps
    # --------------------------------------------------------

    screener_retrieved_at = (
        screener_data.get(
            "retrieved_at"
        )
        or requested_at
    )

    market_retrieved_at = (
        market_data.get(
            "retrieved_at"
        )
        or requested_at
    )

    # --------------------------------------------------------
    # Source URLs
    # --------------------------------------------------------

    screener_url = screener_data.get(
        "url"
    )

    # --------------------------------------------------------
    # Block-level as-of dates
    # --------------------------------------------------------

    screener_as_of_dates = (
        get_screener_as_of_dates(
            screener_data
        )
    )

    fundamentals_as_of_date = (
        screener_as_of_dates[
            "fundamentals"
        ]
    )

    institutional_as_of_date = (
        screener_as_of_dates[
            "institutional"
        ]
    )

    market_as_of_date = (
        get_adapter_as_of_date(
            market_data
        )
    )

    # --------------------------------------------------------
    # Identity
    # --------------------------------------------------------

    symbol = (
        screener_data.get("symbol")
        or market_data.get("symbol")
        or ""
    ).upper()

    company_name = (
        screener_data.get(
            "company_name"
        )
        or symbol
    )

    # --------------------------------------------------------
    # Raw adapter blocks
    # --------------------------------------------------------

    fundamentals_raw = (
        screener_data.get(
            "fundamentals",
            {},
        )
    )

    institutional_raw = (
        screener_data.get(
            "institutional",
            {},
        )
    )

    technicals_raw = (
        market_data.get(
            "indicators",
            {},
        )
    )

    # ========================================================
    # FUNDAMENTALS
    # ========================================================

    fundamentals = {}

    # --------------------------------------------------------
    # P/E
    # --------------------------------------------------------

    fundamentals["pe_ratio"] = (
        verified_or_unavailable(
            fundamentals_raw.get("pe"),
            "RATIO",
            "screener",
            screener_url,
            screener_retrieved_at,
            fundamentals_as_of_date,
        )
    )

    # --------------------------------------------------------
    # P/B = CMP / Book Value
    # --------------------------------------------------------

    cmp_value = technicals_raw.get(
        "cmp"
    )

    book_value = fundamentals_raw.get(
        "book_value"
    )

    if (
        cmp_value is not None
        and book_value is not None
        and book_value != 0
    ):

        try:

            pb_ratio = round(
                float(cmp_value)
                / float(book_value),
                4,
            )

        except (
            TypeError,
            ValueError,
            ZeroDivisionError,
        ):

            pb_ratio = None

    else:

        pb_ratio = None

    if pb_ratio is not None:

        fundamentals["pb_ratio"] = (
            derived_datapoint(
                value=pb_ratio,
                unit="RATIO",
                source="screener",
                source_url=screener_url,
                retrieved_at=screener_retrieved_at,
                as_of_date=fundamentals_as_of_date,
                notes=(
                    "Derived as Current Market Price / "
                    "Book Value per Share."
                ),
            )
        )

    else:

        fundamentals["pb_ratio"] = (
            datapoint(
                value=None,
                unit="RATIO",
                status="UNAVAILABLE",
                source="screener",
                source_url=screener_url,
                retrieved_at=screener_retrieved_at,
                as_of_date=fundamentals_as_of_date,
                notes=(
                    "Unable to derive P/B because "
                    "CMP or Book Value is unavailable."
                ),
            )
        )

    # --------------------------------------------------------
    # ROCE
    # --------------------------------------------------------

    fundamentals["roce"] = (
        verified_or_unavailable(
            fundamentals_raw.get("roce"),
            "PERCENT",
            "screener",
            screener_url,
            screener_retrieved_at,
            fundamentals_as_of_date,
        )
    )

    # --------------------------------------------------------
    # ROE
    # --------------------------------------------------------

    fundamentals["roe"] = (
        verified_or_unavailable(
            fundamentals_raw.get("roe"),
            "PERCENT",
            "screener",
            screener_url,
            screener_retrieved_at,
            fundamentals_as_of_date,
        )
    )

    # --------------------------------------------------------
    # Debt / Equity
    # --------------------------------------------------------

    fundamentals["debt_to_equity"] = (
        verified_or_unavailable(
            fundamentals_raw.get(
                "debt_to_equity"
            ),
            "RATIO",
            "screener",
            screener_url,
            screener_retrieved_at,
            fundamentals_as_of_date,
            notes=(
                "Debt-to-equity was not directly "
                "available from the current Screener "
                "snapshot."
                if fundamentals_raw.get(
                    "debt_to_equity"
                ) is None
                else None
            ),
        )
    )

    # --------------------------------------------------------
    # Sales growth
    # --------------------------------------------------------

    fundamentals[
        "sales_growth_3y_cagr"
    ] = verified_or_unavailable(
        fundamentals_raw.get(
            "sales_growth_3y"
        ),
        "PERCENT",
        "screener",
        screener_url,
        screener_retrieved_at,
        fundamentals_as_of_date,
    )

    # --------------------------------------------------------
    # Profit growth
    # --------------------------------------------------------

    fundamentals[
        "profit_growth_3y_cagr"
    ] = verified_or_unavailable(
        fundamentals_raw.get(
            "profit_growth_3y"
        ),
        "PERCENT",
        "screener",
        screener_url,
        screener_retrieved_at,
        fundamentals_as_of_date,
    )

    # --------------------------------------------------------
    # Market cap
    # --------------------------------------------------------

    fundamentals["market_cap"] = (
        verified_or_unavailable(
            fundamentals_raw.get(
                "market_cap"
            ),
            "INR_CRORE",
            "screener",
            screener_url,
            screener_retrieved_at,
            fundamentals_as_of_date,
        )
    )

    # Add block provenance.
    fundamentals = {
        "provenance": block_provenance(
            source="screener",
            source_url=screener_url,
            retrieved_at=screener_retrieved_at,
            as_of_date=fundamentals_as_of_date,
        ),
        **fundamentals,
    }

    # ========================================================
    # TECHNICALS
    # ========================================================

    technicals = {}

    # --------------------------------------------------------
    # CMP
    # --------------------------------------------------------

    technicals["cmp"] = (
        verified_or_unavailable(
            technicals_raw.get("cmp"),
            "INR",
            "market_data",
            None,
            market_retrieved_at,
            market_as_of_date,
        )
    )

    # --------------------------------------------------------
    # 50 DMA
    # --------------------------------------------------------

    technicals["dma_50"] = (
        verified_or_unavailable(
            technicals_raw.get("dma_50"),
            "INR",
            "market_data",
            None,
            market_retrieved_at,
            market_as_of_date,
        )
    )

    # --------------------------------------------------------
    # 200 DMA
    # --------------------------------------------------------

    technicals["dma_200"] = (
        verified_or_unavailable(
            technicals_raw.get("dma_200"),
            "INR",
            "market_data",
            None,
            market_retrieved_at,
            market_as_of_date,
        )
    )

    # --------------------------------------------------------
    # Above 50 DMA
    # --------------------------------------------------------

    technicals["above_50_dma"] = (
        verified_or_unavailable(
            technicals_raw.get(
                "above_50_dma"
            ),
            "BOOLEAN",
            "market_data",
            None,
            market_retrieved_at,
            market_as_of_date,
        )
    )

    # --------------------------------------------------------
    # Above 200 DMA
    # --------------------------------------------------------

    technicals["above_200_dma"] = (
        verified_or_unavailable(
            technicals_raw.get(
                "above_200_dma"
            ),
            "BOOLEAN",
            "market_data",
            None,
            market_retrieved_at,
            market_as_of_date,
        )
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    technicals["rsi_14"] = (
        verified_or_unavailable(
            technicals_raw.get("rsi_14"),
            "INDEX",
            "market_data",
            None,
            market_retrieved_at,
            market_as_of_date,
        )
    )

    # --------------------------------------------------------
    # Current volume
    # --------------------------------------------------------

    technicals["volume"] = (
        verified_or_unavailable(
            technicals_raw.get("volume"),
            "SHARES",
            "market_data",
            None,
            market_retrieved_at,
            market_as_of_date,
        )
    )

    # --------------------------------------------------------
    # Average volume 1 week
    # --------------------------------------------------------

    technicals["avg_volume_1w"] = (
        verified_or_unavailable(
            technicals_raw.get(
                "avg_volume_1w"
            ),
            "SHARES",
            "market_data",
            None,
            market_retrieved_at,
            market_as_of_date,
        )
    )

    # --------------------------------------------------------
    # Average volume 1 month
    # --------------------------------------------------------

    technicals["avg_volume_1m"] = (
        verified_or_unavailable(
            technicals_raw.get(
                "avg_volume_1m"
            ),
            "SHARES",
            "market_data",
            None,
            market_retrieved_at,
            market_as_of_date,
        )
    )

    # --------------------------------------------------------
    # Volume vs 1 week
    # --------------------------------------------------------

    technicals["volume_vs_1w_pct"] = (
        verified_or_unavailable(
            technicals_raw.get(
                "volume_vs_1w_pct"
            ),
            "PERCENT",
            "market_data",
            None,
            market_retrieved_at,
            market_as_of_date,
        )
    )

    # --------------------------------------------------------
    # Volume vs 1 month
    # --------------------------------------------------------

    technicals["volume_vs_1m_pct"] = (
        verified_or_unavailable(
            technicals_raw.get(
                "volume_vs_1m_pct"
            ),
            "PERCENT",
            "market_data",
            None,
            market_retrieved_at,
            market_as_of_date,
        )
    )

    # --------------------------------------------------------
    # Volume above 1 week
    # --------------------------------------------------------

    technicals["volume_above_1w"] = (
        verified_or_unavailable(
            technicals_raw.get(
                "volume_above_1w"
            ),
            "BOOLEAN",
            "market_data",
            None,
            market_retrieved_at,
            market_as_of_date,
        )
    )

    # --------------------------------------------------------
    # Volume above 1 month
    # --------------------------------------------------------

    technicals["volume_above_1m"] = (
        verified_or_unavailable(
            technicals_raw.get(
                "volume_above_1m"
            ),
            "BOOLEAN",
            "market_data",
            None,
            market_retrieved_at,
            market_as_of_date,
        )
    )

    # --------------------------------------------------------
    # Volume traction
    # --------------------------------------------------------

    technicals["volume_traction"] = (
        verified_or_unavailable(
            technicals_raw.get(
                "volume_traction"
            ),
            "BOOLEAN",
            "market_data",
            None,
            market_retrieved_at,
            market_as_of_date,
            notes=(
                "True when current volume is above "
                "the 1-week average and the 1-week "
                "average is above the 1-month average."
            ),
        )
    )

    # --------------------------------------------------------
    # 52-week high
    # --------------------------------------------------------

    technicals[
        "fifty_two_week_high"
    ] = verified_or_unavailable(
        technicals_raw.get(
            "fifty_two_week_high"
        ),
        "INR",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
    )

    # --------------------------------------------------------
    # 52-week low
    # --------------------------------------------------------

    technicals[
        "fifty_two_week_low"
    ] = verified_or_unavailable(
        technicals_raw.get(
            "fifty_two_week_low"
        ),
        "INR",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
    )

    # --------------------------------------------------------
    # STAGE 1 ENHANCED TECHNICAL METRICS
    # --------------------------------------------------------

    technicals["history_bars"] = verified_or_unavailable(
        technicals_raw.get("history_bars"),
        "COUNT",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
    )

    technicals["pct_from_50_dma"] = derived_datapoint(
        technicals_raw.get("pct_from_50_dma"),
        "PERCENT",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Distance of CMP from 50-day simple moving average.",
    )

    technicals["pct_from_200_dma"] = derived_datapoint(
        technicals_raw.get("pct_from_200_dma"),
        "PERCENT",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Distance of CMP from 200-day simple moving average.",
    )

    alignment_val = technicals_raw.get("dma_alignment")
    if alignment_val and alignment_val != "UNAVAILABLE":
        technicals["dma_alignment"] = datapoint(
            value=alignment_val,
            unit="TEXT",
            status="DERIVED",
            source="market_data",
            retrieved_at=market_retrieved_at,
            as_of_date=market_as_of_date,
            notes="Relative alignment of 50 DMA vs 200 DMA.",
        )
    else:
        technicals["dma_alignment"] = datapoint(
            value=None,
            unit="TEXT",
            status="UNAVAILABLE",
            source="market_data",
            retrieved_at=market_retrieved_at,
            as_of_date=market_as_of_date,
            notes="Insufficient history (<200 bars) for 50/200 DMA alignment.",
        )

    slope50_val = technicals_raw.get("dma_slope_50")
    if slope50_val and slope50_val != "UNAVAILABLE":
        technicals["dma_slope_50"] = datapoint(
            value=slope50_val,
            unit="TEXT",
            status="DERIVED",
            source="market_data",
            retrieved_at=market_retrieved_at,
            as_of_date=market_as_of_date,
            notes="10-session slope of 50 DMA (provisional ±0.50% flat tolerance).",
        )
    else:
        technicals["dma_slope_50"] = datapoint(
            value=None,
            unit="TEXT",
            status="UNAVAILABLE",
            source="market_data",
            retrieved_at=market_retrieved_at,
            as_of_date=market_as_of_date,
            notes="Insufficient history (<60 bars) for 50 DMA slope.",
        )

    technicals["dma_slope_50_pct"] = derived_datapoint(
        technicals_raw.get("dma_slope_50_pct"),
        "PERCENT",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "10-session percentage change of 50 DMA.",
    )

    slope200_val = technicals_raw.get("dma_slope_200")
    if slope200_val and slope200_val != "UNAVAILABLE":
        technicals["dma_slope_200"] = datapoint(
            value=slope200_val,
            unit="TEXT",
            status="DERIVED",
            source="market_data",
            retrieved_at=market_retrieved_at,
            as_of_date=market_as_of_date,
            notes="10-session slope of 200 DMA (provisional ±0.50% flat tolerance).",
        )
    else:
        technicals["dma_slope_200"] = datapoint(
            value=None,
            unit="TEXT",
            status="UNAVAILABLE",
            source="market_data",
            retrieved_at=market_retrieved_at,
            as_of_date=market_as_of_date,
            notes="Insufficient history (<210 bars) for 200 DMA slope.",
        )

    technicals["dma_slope_200_pct"] = derived_datapoint(
        technicals_raw.get("dma_slope_200_pct"),
        "PERCENT",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "10-session percentage change of 200 DMA.",
    )

    crossover_type = technicals_raw.get("last_crossover_type")
    crossover_notes = technicals_raw.get("crossover_notes")
    if crossover_type in ("GOLDEN_CROSS", "DEATH_CROSS", "NOT_FOUND_IN_LOOKBACK"):
        technicals["last_crossover_type"] = datapoint(
            value=crossover_type,
            unit="TEXT",
            status="DERIVED",
            source="market_data",
            retrieved_at=market_retrieved_at,
            as_of_date=market_as_of_date,
            notes=crossover_notes or "Historical 50/200 DMA crossover status.",
        )
    else:
        technicals["last_crossover_type"] = datapoint(
            value=None,
            unit="TEXT",
            status="UNAVAILABLE",
            source="market_data",
            retrieved_at=market_retrieved_at,
            as_of_date=market_as_of_date,
            notes=crossover_notes or "Insufficient history (<200 bars) for crossover detection.",
        )

    technicals["last_crossover_date"] = derived_datapoint(
        technicals_raw.get("last_crossover_date"),
        "DATE",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Date of most recent 50/200 DMA crossover.",
    )

    technicals["days_since_dma_crossover"] = derived_datapoint(
        technicals_raw.get("days_since_dma_crossover"),
        "COUNT",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Trading sessions elapsed since most recent 50/200 DMA crossover.",
    )

    technicals["atr_14"] = derived_datapoint(
        technicals_raw.get("atr_14"),
        "INR",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Wilder's 14-session Average True Range.",
    )

    technicals["atr_pct"] = derived_datapoint(
        technicals_raw.get("atr_pct"),
        "PERCENT",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "ATR(14) as percentage of Current Market Price.",
    )

    technicals["atr_50_avg"] = derived_datapoint(
        technicals_raw.get("atr_50_avg"),
        "INR",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "50-session simple moving average baseline of ATR(14).",
    )

    technicals["avg_volume_5"] = derived_datapoint(
        technicals_raw.get("avg_volume_5"),
        "SHARES",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "5-session simple moving average of volume.",
    )

    technicals["avg_volume_20"] = derived_datapoint(
        technicals_raw.get("avg_volume_20"),
        "SHARES",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "20-session simple moving average of volume.",
    )

    technicals["avg_volume_50"] = derived_datapoint(
        technicals_raw.get("avg_volume_50"),
        "SHARES",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "50-session simple moving average of volume.",
    )

    technicals["volume_vs_20d_pct"] = derived_datapoint(
        technicals_raw.get("volume_vs_20d_pct"),
        "PERCENT",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Current volume relative to 20-session volume average.",
    )

    technicals["obv_change_norm_14d"] = derived_datapoint(
        technicals_raw.get("obv_change_norm_14d"),
        "RATIO",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Normalized 14-session OBV change relative to 20-day volume baseline; provisional ±0.20 threshold.",
    )

    technicals["clv"] = derived_datapoint(
        technicals_raw.get("clv"),
        "RATIO",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Close Location Value for latest session (guarded 0.0 on zero-range candles).",
    )

    technicals["clv_14_avg"] = derived_datapoint(
        technicals_raw.get("clv_14_avg"),
        "RATIO",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "14-session simple moving average of Close Location Value.",
    )

    technicals["pct_from_52w_high"] = derived_datapoint(
        technicals_raw.get("pct_from_52w_high"),
        "PERCENT",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Distance of CMP from 52-week High (raw daily High over 252 sessions).",
    )

    technicals["pct_from_52w_low"] = derived_datapoint(
        technicals_raw.get("pct_from_52w_low"),
        "PERCENT",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Distance of CMP from 52-week Low (raw daily Low over 252 sessions).",
    )

    technicals["swing_high_20"] = derived_datapoint(
        technicals_raw.get("swing_high_20"),
        "INR",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Confirmed 20-session swing high price level (3-session confirmation lag).",
    )

    technicals["swing_high_date"] = derived_datapoint(
        technicals_raw.get("swing_high_date"),
        "DATE",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Date of confirmed 20-session swing high peak.",
    )

    technicals["swing_high_confirmation_date"] = derived_datapoint(
        technicals_raw.get("swing_high_confirmation_date"),
        "DATE",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Confirmation date of 20-session swing high (3-session lag prevents look-ahead).",
    )

    technicals["pct_from_swing_high"] = derived_datapoint(
        technicals_raw.get("pct_from_swing_high"),
        "PERCENT",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Distance of CMP from confirmed 20-session swing high.",
    )

    technicals["swing_low_20"] = derived_datapoint(
        technicals_raw.get("swing_low_20"),
        "INR",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Confirmed 20-session swing low price level (3-session confirmation lag).",
    )

    technicals["swing_low_date"] = derived_datapoint(
        technicals_raw.get("swing_low_date"),
        "DATE",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Date of confirmed 20-session swing low trough.",
    )

    technicals["swing_low_confirmation_date"] = derived_datapoint(
        technicals_raw.get("swing_low_confirmation_date"),
        "DATE",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Confirmation date of 20-session swing low (3-session lag prevents look-ahead).",
    )

    technicals["pct_from_swing_low"] = derived_datapoint(
        technicals_raw.get("pct_from_swing_low"),
        "PERCENT",
        "market_data",
        None,
        market_retrieved_at,
        market_as_of_date,
        "Distance of CMP from confirmed 20-session swing low.",
    )

    # Add block provenance.
    technicals = {
        "provenance": block_provenance(
            source="market_data",
            source_url=None,
            retrieved_at=market_retrieved_at,
            as_of_date=market_as_of_date,
        ),
        **technicals,
    }

    # ========================================================
    # INSTITUTIONAL
    # ========================================================

    institutional = {}

    # --------------------------------------------------------
    # Promoter holding
    # --------------------------------------------------------

    institutional[
        "promoter_holding_pct"
    ] = verified_or_unavailable(
        institutional_raw.get(
            "promoter"
        ),
        "PERCENT",
        "screener",
        screener_url,
        screener_retrieved_at,
        institutional_as_of_date,
    )

    # --------------------------------------------------------
    # Promoter holding QoQ change
    # --------------------------------------------------------

    promoter_current = (
        institutional_raw.get(
            "promoter"
        )
    )

    promoter_previous = (
        institutional_raw.get(
            "promoter_previous"
        )
    )

    promoter_change = None

    if (
        promoter_current is not None
        and promoter_previous is not None
    ):

        try:

            promoter_change = round(
                float(promoter_current)
                - float(promoter_previous),
                2,
            )

        except (
            TypeError,
            ValueError,
        ):

            promoter_change = None

    institutional[
        "promoter_holding_change_qoq"
    ] = derived_datapoint(
        value=promoter_change,
        unit="PERCENTAGE_POINTS",
        source="screener",
        source_url=screener_url,
        retrieved_at=screener_retrieved_at,
        as_of_date=institutional_as_of_date,
        notes=(
            "Current promoter holding minus "
            "previous quarter promoter holding."
        ),
    )

    # --------------------------------------------------------
    # Promoter pledge
    # --------------------------------------------------------

    institutional[
        "promoter_pledge_pct"
    ] = verified_or_unavailable(
        institutional_raw.get(
            "promoter_pledge"
        ),
        "PERCENT",
        "screener",
        screener_url,
        screener_retrieved_at,
        institutional_as_of_date,
    )

    # --------------------------------------------------------
    # FII holding
    # --------------------------------------------------------

    institutional[
        "fii_holding_pct"
    ] = verified_or_unavailable(
        institutional_raw.get(
            "fii"
        ),
        "PERCENT",
        "screener",
        screener_url,
        screener_retrieved_at,
        institutional_as_of_date,
    )

    # --------------------------------------------------------
    # FII QoQ change
    # --------------------------------------------------------

    fii_current = (
        institutional_raw.get(
            "fii"
        )
    )

    fii_previous = (
        institutional_raw.get(
            "fii_previous"
        )
    )

    fii_change = None

    if (
        fii_current is not None
        and fii_previous is not None
    ):

        try:

            fii_change = round(
                float(fii_current)
                - float(fii_previous),
                2,
            )

        except (
            TypeError,
            ValueError,
        ):

            fii_change = None

    institutional[
        "fii_holding_change_qoq"
    ] = derived_datapoint(
        value=fii_change,
        unit="PERCENTAGE_POINTS",
        source="screener",
        source_url=screener_url,
        retrieved_at=screener_retrieved_at,
        as_of_date=institutional_as_of_date,
        notes=(
            "Current FII holding minus "
            "previous quarter FII holding."
        ),
    )

    # --------------------------------------------------------
    # DII holding
    # --------------------------------------------------------

    institutional[
        "dii_holding_pct"
    ] = verified_or_unavailable(
        institutional_raw.get(
            "dii"
        ),
        "PERCENT",
        "screener",
        screener_url,
        screener_retrieved_at,
        institutional_as_of_date,
    )

    # --------------------------------------------------------
    # DII QoQ change
    # --------------------------------------------------------

    dii_current = (
        institutional_raw.get(
            "dii"
        )
    )

    dii_previous = (
        institutional_raw.get(
            "dii_previous"
        )
    )

    dii_change = None

    if (
        dii_current is not None
        and dii_previous is not None
    ):

        try:

            dii_change = round(
                float(dii_current)
                - float(dii_previous),
                2,
            )

        except (
            TypeError,
            ValueError,
        ):

            dii_change = None

    institutional[
        "dii_holding_change_qoq"
    ] = derived_datapoint(
        value=dii_change,
        unit="PERCENTAGE_POINTS",
        source="screener",
        source_url=screener_url,
        retrieved_at=screener_retrieved_at,
        as_of_date=institutional_as_of_date,
        notes=(
            "Current DII holding minus "
            "previous quarter DII holding."
        ),
    )

    # Add block provenance.
    institutional = {
        "provenance": block_provenance(
            source="screener",
            source_url=screener_url,
            retrieved_at=screener_retrieved_at,
            as_of_date=institutional_as_of_date,
        ),
        **institutional,
    }

    # ========================================================
    # SOURCES
    # ========================================================

    # ========================================================
    # NEWS NORMALIZATION
    # ========================================================

    news_items = []

    news_retrieved_at = (
        news_data.get("retrieved_at")
        or requested_at
    )

    news_url = news_data.get("url")

    for article in (
        news_data.get("articles") or []
    ):

        headline = article.get("headline")

        if not headline:
            continue

        news_items.append(
            {
                "headline": headline,
                "summary": article.get("summary"),
                "published_at": article.get(
                    "published_at"
                ),
                "provenance": {
                    "source": (
                        article.get("source")
                        or "news"
                    ),
                    "source_url": (
                        article.get("url")
                        or news_url
                    ),
                    "retrieved_at": (
                        news_retrieved_at
                    ),
                    "as_of_date": None,
                },
            }
        )

    # ========================================================
    # SOURCES
    # ========================================================

    sources = [
        {
            "source": "screener",
            "status": "SUCCESS",
            "fields_sourced": 13,
            "source_url": screener_url,
            "retrieved_at": screener_retrieved_at,
            "as_of_date": (
                fundamentals_as_of_date
            ),
        },
        {
            "source": "market_data",
            "status": "SUCCESS",
            "fields_sourced": 16,
            "source_url": None,
            "retrieved_at": market_retrieved_at,
            "as_of_date": market_as_of_date,
        },
        {
            "source": "news",
            "status": (
                "SUCCESS"
                if news_items
                else "PARTIAL"
            ),
            "fields_sourced": len(news_items),
            "source_url": news_url,
            "retrieved_at": news_retrieved_at,
            "as_of_date": None,
        },
    ]

    # ========================================================
    # RESULT
    # ========================================================

    completed_at = utc_now()

    result = {
        "schema_version": "1.0",

        "research_id": (
            f"{symbol.lower()}-pipeline-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        ),

        "symbol": symbol,

        "exchange": "NSE",

        "isin": None,

        "company_name": company_name,

        "symbol_match_confidence": "EXACT",

        "requested_at": requested_at,

        "completed_at": completed_at,

        "overall_status": "PARTIAL",

        "fundamentals": fundamentals,

        "technicals": technicals,

        "institutional": institutional,

        "news": news_items,

        "sources": sources,

        "errors": [],

        "data_quality_summary": {},
    }

    # Calculate quality summary after all datapoints
    # have been assembled.
    result[
        "data_quality_summary"
    ] = count_statuses(result)

    return result


# ============================================================
# VALIDATION
# ============================================================

def validate_schema(
    result: Dict[str, Any],
) -> None:
    """
    Validate ResearchResult against the canonical
    ResearchResult v1 JSON schema.
    """

    if jsonschema is None:
        print(
            "WARNING: jsonschema package is not installed; "
            "skipping schema validation."
        )
        return

    schema_file = None
    if LOCAL_SCHEMA_PATH.exists():
        schema_file = LOCAL_SCHEMA_PATH
    elif FALLBACK_SCHEMA_PATH.exists():
        schema_file = FALLBACK_SCHEMA_PATH

    if not schema_file:
        print(
            f"WARNING: Schema not found at {LOCAL_SCHEMA_PATH} or {FALLBACK_SCHEMA_PATH}; "
            "skipping validation in isolated setup."
        )
        return

    with open(
        schema_file,
        "r",
        encoding="utf-8",
    ) as f:
        schema = json.load(f)

    jsonschema.validate(
        instance=result,
        schema=schema,
    )


# ============================================================
# SAVE
# ============================================================

def save_result(
    result: Dict[str, Any],
) -> Path:
    """
    Save normalized ResearchResult JSON.
    """

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    symbol = result[
        "symbol"
    ].lower()

    output_path = (
        OUTPUT_DIR
        / f"{symbol}-research-result.json"
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            result,
            f,
            indent=2,
            ensure_ascii=False,
        )

        f.write("\n")

    return output_path


# ============================================================
# PIPELINE
# ============================================================

def run_pipeline(
    symbol: str,
) -> Dict[str, Any]:

    symbol = symbol.upper().strip()

    if not symbol:

        raise ValueError(
            "Stock symbol cannot be empty."
        )

    print("=" * 70)
    print("STOCK RESEARCH PIPELINE")
    print("=" * 70)
    print()
    print(f"Symbol: {symbol}")
    print()

    # ========================================================
    # 1. SCREENER
    # ========================================================

    print("1. Screener HTTP")

    screener = ScreenerAdapter()

    screener_data = screener.research(
        symbol
    )

    print(
        f"   Company: "
        f"{screener_data.get('company_name')}"
    )

    print(
        f"   HTML bytes: "
        f"{screener_data.get('html_bytes')}"
    )

    print(
        f"   Tables: "
        f"{screener_data.get('table_count')}"
    )

    print(
        "   ✅ Screener extraction successful"
    )

    print()

    # ========================================================
    # 2. MARKET DATA
    # ========================================================

    print("2. Market Data")

    market = MarketDataAdapter()

    market_data = market.research(
        symbol
    )

    print(
        f"   Yahoo symbol: "
        f"{market_data.get('yahoo_symbol')}"
    )

    print(
        f"   History rows: "
        f"{market_data.get('history_rows')}"
    )

    print(
        "   ✅ Market-data extraction successful"
    )

    print()

    # ========================================================
    # 3. NEWS
    # ========================================================

    print("3. News")

    news = NewsAdapter()

    news_data = news.research(
        symbol,
        screener_data.get("company_name") or symbol,
    )

    print(
        f"   Articles: "
        f"{news_data.get('article_count', 0)}"
    )

    print(
        f"   Lookback: "
        f"{news_data.get('lookback_days')} days"
    )

    print(
        "   ✅ News extraction successful"
    )

    print()

    # ========================================================
    # 4. NORMALIZE
    # ========================================================

    print(
        "4. Normalize → ResearchResult v1"
    )

    result = build_research_result(
        screener_data,
        market_data,
        news_data,
    )

    print(
        "   ✅ ResearchResult object created"
    )

    print()

    # ========================================================
    # 5. VALIDATE
    # ========================================================

    print("5. Validate")

    validate_schema(
        result
    )

    print(
        "✅ ResearchResult v1 schema validation PASSED"
    )

    print()

    # ========================================================
    # 6. SAVE
    # ========================================================

    print("6. Save")

    output_path = save_result(
        result
    )

    print(
        f"   ✅ {output_path}"
    )

    print()

    # ========================================================
    # SUMMARY
    # ========================================================

    print("=" * 70)
    print("PIPELINE SUMMARY")
    print("=" * 70)

    print(
        json.dumps(
            result[
                "data_quality_summary"
            ],
            indent=2,
        )
    )

    print()

    print(
        "Screener + Market Data → "
        "ResearchResult v1 → "
        "Validation → JSON: SUCCESS"
    )

    print()

    # ========================================================
    # RESEARCH RESULT
    # ========================================================

    print("=" * 70)
    print("RESEARCH RESULT")
    print("=" * 70)

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )

    return result


# ============================================================
# CLI
# ============================================================

def main():

    symbol = (
        sys.argv[1].upper().strip()
        if len(sys.argv) > 1
        else "TCS"
    )

    run_pipeline(
        symbol
    )


if __name__ == "__main__":
    main()
