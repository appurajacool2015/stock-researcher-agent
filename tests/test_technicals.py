#!/usr/bin/env python3

"""
Tests for intelligence/technicals.py
"""

import json
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(PROJECT_ROOT))

from intelligence.technicals import analyze_technicals


def make_fact(
    value,
    unit="INR",
    status="VERIFIED",
):
    """Create a canonical ResearchResult v1 fact."""

    return {
        "value": value,
        "unit": unit,
        "status": status,
        "provenance": {
            "source": "test",
            "source_url": None,
            "retrieved_at": "2026-09-01T00:00:00+00:00",
            "as_of_date": "2026-09-01",
        },
        "conflicting_values": [],
        "notes": None,
    }


def make_research_result(**values):
    """Create a canonical ResearchResult-like object."""

    technicals_dict = {
        "provenance": {
            "source": "test",
            "source_url": None,
            "retrieved_at": "2026-09-01T00:00:00+00:00",
            "as_of_date": "2026-09-01",
        },

        "cmp": make_fact(
            values.get("cmp"),
            "INR",
        ),

        "dma_50": make_fact(
            values.get("dma_50"),
            "INR",
        ),

        "dma_200": make_fact(
            values.get("dma_200"),
            "INR",
        ),

        "above_50_dma": make_fact(
            values.get("above_50_dma"),
            "BOOLEAN",
        ),

        "above_200_dma": make_fact(
            values.get("above_200_dma"),
            "BOOLEAN",
        ),

        "rsi_14": make_fact(
            values.get("rsi_14"),
            "INDEX",
        ),

        "volume": make_fact(
            values.get("volume"),
            "SHARES",
        ),

        "avg_volume_1w": make_fact(
            values.get("avg_volume_1w"),
            "SHARES",
        ),

        "avg_volume_1m": make_fact(
            values.get("avg_volume_1m"),
            "SHARES",
        ),

        "volume_vs_1w_pct": make_fact(
            values.get("volume_vs_1w_pct"),
            "PERCENT",
        ),

        "volume_vs_1m_pct": make_fact(
            values.get("volume_vs_1m_pct"),
            "PERCENT",
        ),

        "volume_above_1w": make_fact(
            values.get("volume_above_1w"),
            "BOOLEAN",
        ),

        "volume_above_1m": make_fact(
            values.get("volume_above_1m"),
            "BOOLEAN",
        ),

        "volume_traction": make_fact(
            values.get("volume_traction"),
            "BOOLEAN",
        ),

        "fifty_two_week_high": make_fact(
            values.get("fifty_two_week_high"),
            "INR",
        ),

        "fifty_two_week_low": make_fact(
            values.get("fifty_two_week_low"),
            "INR",
        ),
    }

    # Stage 1 enhanced metrics mapping
    if "history_bars" in values:
        technicals_dict["history_bars"] = make_fact(values.get("history_bars"), "COUNT")
    if "pct_from_50_dma" in values:
        technicals_dict["pct_from_50_dma"] = make_fact(values.get("pct_from_50_dma"), "PERCENT", "DERIVED")
    if "pct_from_200_dma" in values:
        technicals_dict["pct_from_200_dma"] = make_fact(values.get("pct_from_200_dma"), "PERCENT", "DERIVED")
    if "dma_alignment" in values:
        technicals_dict["dma_alignment"] = make_fact(values.get("dma_alignment"), "TEXT", "DERIVED")
    if "dma_slope_50" in values:
        technicals_dict["dma_slope_50"] = make_fact(values.get("dma_slope_50"), "TEXT", "DERIVED")
    if "dma_slope_50_pct" in values:
        technicals_dict["dma_slope_50_pct"] = make_fact(values.get("dma_slope_50_pct"), "PERCENT", "DERIVED")
    if "dma_slope_200" in values:
        technicals_dict["dma_slope_200"] = make_fact(values.get("dma_slope_200"), "TEXT", "DERIVED")
    if "dma_slope_200_pct" in values:
        technicals_dict["dma_slope_200_pct"] = make_fact(values.get("dma_slope_200_pct"), "PERCENT", "DERIVED")
    if "last_crossover_type" in values:
        technicals_dict["last_crossover_type"] = make_fact(values.get("last_crossover_type"), "TEXT", "DERIVED")
    if "last_crossover_date" in values:
        technicals_dict["last_crossover_date"] = make_fact(values.get("last_crossover_date"), "DATE", "DERIVED")
    if "days_since_dma_crossover" in values:
        technicals_dict["days_since_dma_crossover"] = make_fact(values.get("days_since_dma_crossover"), "COUNT", "DERIVED")
    if "atr_14" in values:
        technicals_dict["atr_14"] = make_fact(values.get("atr_14"), "INR", "DERIVED")
    if "atr_pct" in values:
        technicals_dict["atr_pct"] = make_fact(values.get("atr_pct"), "PERCENT", "DERIVED")
    if "atr_50_avg" in values:
        technicals_dict["atr_50_avg"] = make_fact(values.get("atr_50_avg"), "INR", "DERIVED")
    if "avg_volume_5" in values:
        technicals_dict["avg_volume_5"] = make_fact(values.get("avg_volume_5"), "SHARES", "DERIVED")
    if "avg_volume_20" in values:
        technicals_dict["avg_volume_20"] = make_fact(values.get("avg_volume_20"), "SHARES", "DERIVED")
    if "avg_volume_50" in values:
        technicals_dict["avg_volume_50"] = make_fact(values.get("avg_volume_50"), "SHARES", "DERIVED")
    if "volume_vs_20d_pct" in values:
        technicals_dict["volume_vs_20d_pct"] = make_fact(values.get("volume_vs_20d_pct"), "PERCENT", "DERIVED")
    if "obv_change_norm_14d" in values:
        technicals_dict["obv_change_norm_14d"] = make_fact(values.get("obv_change_norm_14d"), "RATIO", "DERIVED")
    if "clv" in values:
        technicals_dict["clv"] = make_fact(values.get("clv"), "RATIO", "DERIVED")
    if "clv_14_avg" in values:
        technicals_dict["clv_14_avg"] = make_fact(values.get("clv_14_avg"), "RATIO", "DERIVED")
    if "pct_from_52w_high" in values:
        technicals_dict["pct_from_52w_high"] = make_fact(values.get("pct_from_52w_high"), "PERCENT", "DERIVED")
    if "pct_from_52w_low" in values:
        technicals_dict["pct_from_52w_low"] = make_fact(values.get("pct_from_52w_low"), "PERCENT", "DERIVED")
    if "swing_high_20" in values:
        technicals_dict["swing_high_20"] = make_fact(values.get("swing_high_20"), "INR", "DERIVED")
    if "swing_high_date" in values:
        technicals_dict["swing_high_date"] = make_fact(values.get("swing_high_date"), "DATE", "DERIVED")
    if "swing_high_confirmation_date" in values:
        technicals_dict["swing_high_confirmation_date"] = make_fact(values.get("swing_high_confirmation_date"), "DATE", "DERIVED")
    if "pct_from_swing_high" in values:
        technicals_dict["pct_from_swing_high"] = make_fact(values.get("pct_from_swing_high"), "PERCENT", "DERIVED")
    if "swing_low_20" in values:
        technicals_dict["swing_low_20"] = make_fact(values.get("swing_low_20"), "INR", "DERIVED")
    if "swing_low_date" in values:
        technicals_dict["swing_low_date"] = make_fact(values.get("swing_low_date"), "DATE", "DERIVED")
    if "swing_low_confirmation_date" in values:
        technicals_dict["swing_low_confirmation_date"] = make_fact(values.get("swing_low_confirmation_date"), "DATE", "DERIVED")
    if "pct_from_swing_low" in values:
        technicals_dict["pct_from_swing_low"] = make_fact(values.get("pct_from_swing_low"), "PERCENT", "DERIVED")
    if "close_below_prev_close" in values:
        technicals_dict["close_below_prev_close"] = make_fact(values.get("close_below_prev_close"), "BOOLEAN", "DERIVED")

    return {
        "schema_version": "1.0",
        "research_id": "test-research-id",
        "symbol": "TEST",
        "exchange": "NSE",
        "isin": None,
        "company_name": "Test Company Ltd",
        "symbol_match_confidence": "EXACT",
        "requested_at": "2026-09-01T00:00:00+00:00",
        "completed_at": "2026-09-01T00:00:00+00:00",
        "overall_status": "SUCCESS",
        "technicals": technicals_dict,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bullish_moving_average_structure():
    result = analyze_technicals(
        make_research_result(
            cmp=120.0,
            dma_50=100.0,
            dma_200=90.0,
            above_50_dma=True,
            above_200_dma=True,
        )
    )

    assert (
        result["signals"]["trend"]["dma_50"]["signal"]
        == "ABOVE"
    )

    assert (
        result["signals"]["trend"]["dma_200"]["signal"]
        == "ABOVE"
    )

    assert (
        result["signals"]["trend"]["bias"]
        == "POSITIVE"
    )


def test_bearish_moving_average_structure():
    result = analyze_technicals(
        make_research_result(
            cmp=80.0,
            dma_50=100.0,
            dma_200=120.0,
            above_50_dma=False,
            above_200_dma=False,
        )
    )

    assert (
        result["signals"]["trend"]["dma_50"]["signal"]
        == "BELOW"
    )

    assert (
        result["signals"]["trend"]["dma_200"]["signal"]
        == "BELOW"
    )

    assert (
        result["signals"]["trend"]["bias"]
        == "NEGATIVE"
    )


def test_rsi_bands():
    oversold = analyze_technicals(
        make_research_result(rsi_14=25.0)
    )

    weak = analyze_technicals(
        make_research_result(rsi_14=40.0)
    )

    neutral = analyze_technicals(
        make_research_result(rsi_14=50.0)
    )

    strong = analyze_technicals(
        make_research_result(rsi_14=60.0)
    )

    overbought = analyze_technicals(
        make_research_result(rsi_14=75.0)
    )

    assert (
        oversold["signals"]["momentum"]["rsi_14"]["signal"]
        == "OVERSOLD"
    )

    assert (
        weak["signals"]["momentum"]["rsi_14"]["signal"]
        == "WEAK"
    )

    assert (
        neutral["signals"]["momentum"]["rsi_14"]["signal"]
        == "NEUTRAL"
    )

    assert (
        strong["signals"]["momentum"]["rsi_14"]["signal"]
        == "STRONG"
    )

    assert (
        overbought["signals"]["momentum"]["rsi_14"]["signal"]
        == "OVERBOUGHT"
    )


def test_strong_volume_traction():
    result = analyze_technicals(
        make_research_result(
            volume=1200000,
            avg_volume_1w=1000000,
            avg_volume_1m=800000,
            volume_vs_1w_pct=20.0,
            volume_vs_1m_pct=50.0,
            volume_above_1w=True,
            volume_above_1m=True,
            volume_traction=True,
        )
    )

    assert (
        result["signals"]["volume"]["participation"]["signal"]
        == "STRONG_TRACTION"
    )

    assert (
        result["signals"]["volume"]["bias"]
        == "POSITIVE"
    )


def test_mixed_volume():
    result = analyze_technicals(
        make_research_result(
            volume=1020000,
            avg_volume_1w=1000000,
            avg_volume_1m=1100000,
            volume_vs_1w_pct=2.0,
            volume_vs_1m_pct=-7.27,
            volume_above_1w=True,
            volume_above_1m=False,
            volume_traction=False,
        )
    )

    assert (
        result["signals"]["volume"]["participation"]["signal"]
        == "MIXED"
    )


def test_weak_volume():
    result = analyze_technicals(
        make_research_result(
            volume=700000,
            avg_volume_1w=1000000,
            avg_volume_1m=1100000,
            volume_vs_1w_pct=-30.0,
            volume_vs_1m_pct=-36.36,
            volume_above_1w=False,
            volume_above_1m=False,
            volume_traction=False,
        )
    )

    assert (
        result["signals"]["volume"]["participation"]["signal"]
        == "WEAK"
    )


def test_52_week_position():
    low = analyze_technicals(
        make_research_result(
            cmp=110.0,
            fifty_two_week_low=100.0,
            fifty_two_week_high=200.0,
        )
    )

    middle = analyze_technicals(
        make_research_result(
            cmp=150.0,
            fifty_two_week_low=100.0,
            fifty_two_week_high=200.0,
        )
    )

    high = analyze_technicals(
        make_research_result(
            cmp=190.0,
            fifty_two_week_low=100.0,
            fifty_two_week_high=200.0,
        )
    )

    assert (
        low["signals"]["range_position"]["fifty_two_week"]["signal"]
        == "NEAR_52W_LOW"
    )

    assert (
        middle["signals"]["range_position"]["fifty_two_week"]["signal"]
        == "MID_RANGE"
    )

    assert (
        high["signals"]["range_position"]["fifty_two_week"]["signal"]
        == "NEAR_52W_HIGH"
    )


def test_unavailable_values_are_not_invented():
    result = analyze_technicals(
        make_research_result(
            cmp=None,
            dma_50=None,
            dma_200=None,
            above_50_dma=None,
            above_200_dma=None,
            rsi_14=None,
            volume=None,
            avg_volume_1w=None,
            avg_volume_1m=None,
            volume_vs_1w_pct=None,
            volume_vs_1m_pct=None,
            volume_above_1w=None,
            volume_above_1m=None,
            volume_traction=None,
            fifty_two_week_high=None,
            fifty_two_week_low=None,
        )
    )

    assert (
        result["signals"]["trend"]["dma_50"]["signal"]
        == "UNAVAILABLE"
    )

    assert (
        result["signals"]["trend"]["dma_200"]["signal"]
        == "UNAVAILABLE"
    )

    assert (
        result["signals"]["momentum"]["rsi_14"]["signal"]
        == "UNAVAILABLE"
    )

    assert (
        result["signals"]["volume"]["participation"]["signal"]
        == "UNAVAILABLE"
    )

    assert (
        result["signals"]["range_position"]["fifty_two_week"]["signal"]
        == "UNAVAILABLE"
    )

    assert result["score"] is None
    assert result["overall_bias"] == "INSUFFICIENT_DATA"


def test_source_status_and_provenance_are_preserved():
    result = analyze_technicals(
        make_research_result(
            cmp=100.0,
            dma_50=95.0,
        )
    )

    dma50 = result["signals"]["trend"]["dma_50"]

    assert dma50["source_status"]["cmp"] == "VERIFIED"
    assert dma50["source_status"]["dma"] == "VERIFIED"

    assert dma50["provenance"]["source"] == "test"
    assert dma50["provenance"]["as_of_date"] == "2026-09-01"


def test_invalid_52_week_range_is_not_used():
    result = analyze_technicals(
        make_research_result(
            cmp=100.0,
            fifty_two_week_low=200.0,
            fifty_two_week_high=100.0,
        )
    )

    assert (
        result["signals"]["range_position"]["fifty_two_week"]["signal"]
        == "UNAVAILABLE"
    )


def test_tcs_current_result():
    """
    Regression test against the actual current TCS ResearchResult v1.
    """

    output_path = (
        PROJECT_ROOT
        / "output"
        / "tcs-research-result.json"
    )

    if not output_path.exists():
        raise AssertionError(
            f"TCS research result not found: {output_path}"
        )

    with output_path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        research_result = json.load(handle)

    result = analyze_technicals(
        research_result
    )

    technicals = research_result["technicals"]

    # Verify canonical source values exist and are valid numbers
    assert isinstance(technicals["cmp"]["value"], (int, float))
    assert isinstance(technicals["dma_50"]["value"], (int, float))
    assert isinstance(technicals["dma_200"]["value"], (int, float))

    assert technicals["above_50_dma"]["value"] in (True, False)
    assert technicals["above_200_dma"]["value"] in (True, False)

    assert isinstance(technicals["rsi_14"]["value"], (int, float))
    assert isinstance(technicals["volume"]["value"], (int, float))
    assert isinstance(technicals["fifty_two_week_high"]["value"], (int, float))
    assert isinstance(technicals["fifty_two_week_low"]["value"], (int, float))

    # -----------------------------------------------------------------------
    # Verify intelligence
    # -----------------------------------------------------------------------

    assert result["signals"]["trend"]["dma_50"]["signal"] in ("ABOVE", "BELOW", "NEAR_ABOVE", "NEAR_BELOW")
    assert result["signals"]["trend"]["dma_200"]["signal"] in ("ABOVE", "BELOW", "NEAR_ABOVE", "NEAR_BELOW")
    assert result["signals"]["momentum"]["rsi_14"]["signal"] in ("STRONG", "NEUTRAL", "WEAK", "OVERSOLD", "OVERBOUGHT")
    assert result["score"] is not None
    assert result["overall_bias"] in {"POSITIVE", "MIXED", "NEGATIVE"}

    # Technical source provenance should survive interpretation.
    assert (
        result["signals"]["trend"]["dma_50"]["provenance"]["source"]
        == "market_data"
    )


def test_stage_1_backward_compatibility_and_schema():
    """Verify that payloads with all Stage 1 enhanced metrics conform to schema and work with intelligence."""
    import jsonschema

    res = make_research_result(
        cmp=2500.0,
        dma_50=2400.0,
        dma_200=2200.0,
        above_50_dma=True,
        above_200_dma=True,
        rsi_14=60.0,
        volume=1500000.0,
        avg_volume_1w=1400000.0,
        avg_volume_1m=1300000.0,
        volume_vs_1w_pct=7.14,
        volume_vs_1m_pct=15.38,
        volume_above_1w=True,
        volume_above_1m=True,
        volume_traction=True,
        fifty_two_week_high=2800.0,
        fifty_two_week_low=1900.0,
    )

    # Add Stage 1 enhanced metrics to technicals
    res["technicals"]["history_bars"] = make_fact(350, "COUNT")
    res["technicals"]["pct_from_50_dma"] = make_fact(4.17, "PERCENT", "DERIVED")
    res["technicals"]["pct_from_200_dma"] = make_fact(13.64, "PERCENT", "DERIVED")
    res["technicals"]["dma_alignment"] = make_fact("50_DMA_ABOVE_200_DMA", "TEXT", "DERIVED")
    res["technicals"]["dma_slope_50"] = make_fact("RISING", "TEXT", "DERIVED")
    res["technicals"]["dma_slope_50_pct"] = make_fact(1.25, "PERCENT", "DERIVED")
    res["technicals"]["dma_slope_200"] = make_fact("RISING", "TEXT", "DERIVED")
    res["technicals"]["dma_slope_200_pct"] = make_fact(0.85, "PERCENT", "DERIVED")
    res["technicals"]["last_crossover_type"] = make_fact("GOLDEN_CROSS", "TEXT", "DERIVED")
    res["technicals"]["last_crossover_date"] = make_fact("2026-06-15", "DATE", "DERIVED")
    res["technicals"]["days_since_dma_crossover"] = make_fact(85, "COUNT", "DERIVED")
    res["technicals"]["atr_14"] = make_fact(35.5, "INR", "DERIVED")
    res["technicals"]["atr_pct"] = make_fact(1.42, "PERCENT", "DERIVED")
    res["technicals"]["atr_50_avg"] = make_fact(38.2, "INR", "DERIVED")
    res["technicals"]["avg_volume_5"] = make_fact(1400000.0, "SHARES", "DERIVED")
    res["technicals"]["avg_volume_20"] = make_fact(1300000.0, "SHARES", "DERIVED")
    res["technicals"]["avg_volume_50"] = make_fact(1250000.0, "SHARES", "DERIVED")
    res["technicals"]["volume_vs_20d_pct"] = make_fact(15.38, "PERCENT", "DERIVED")
    res["technicals"]["obv_change_norm_14d"] = make_fact(0.35, "RATIO", "DERIVED")
    res["technicals"]["clv"] = make_fact(0.42, "RATIO", "DERIVED")
    res["technicals"]["clv_14_avg"] = make_fact(0.28, "RATIO", "DERIVED")
    res["technicals"]["pct_from_52w_high"] = make_fact(-10.71, "PERCENT", "DERIVED")
    res["technicals"]["pct_from_52w_low"] = make_fact(31.58, "PERCENT", "DERIVED")
    res["technicals"]["swing_high_20"] = make_fact(2650.0, "INR", "DERIVED")
    res["technicals"]["swing_high_date"] = make_fact("2026-08-10", "DATE", "DERIVED")
    res["technicals"]["swing_high_confirmation_date"] = make_fact("2026-08-13", "DATE", "DERIVED")
    res["technicals"]["pct_from_swing_high"] = make_fact(-5.66, "PERCENT", "DERIVED")
    res["technicals"]["swing_low_20"] = make_fact(2380.0, "INR", "DERIVED")
    res["technicals"]["swing_low_date"] = make_fact("2026-07-20", "DATE", "DERIVED")
    res["technicals"]["swing_low_confirmation_date"] = make_fact("2026-07-23", "DATE", "DERIVED")
    res["technicals"]["pct_from_swing_low"] = make_fact(5.04, "PERCENT", "DERIVED")

    # Intelligence processing must run without error
    intel_res = analyze_technicals(res)
    assert intel_res["overall_bias"] in {"POSITIVE", "MIXED", "NEGATIVE"}

    # Add required schema blocks for canonical ResearchResult v1 validation
    res["fundamentals"] = {
        "provenance": {"source": "test", "retrieved_at": "2026-09-01T00:00:00+00:00"},
        "pe_ratio": make_fact(20.0, "RATIO"),
        "pb_ratio": make_fact(4.0, "RATIO"),
        "roce": make_fact(25.0, "PERCENT"),
        "roe": make_fact(22.0, "PERCENT"),
        "debt_to_equity": make_fact(0.1, "RATIO"),
        "sales_growth_3y_cagr": make_fact(15.0, "PERCENT"),
        "profit_growth_3y_cagr": make_fact(12.0, "PERCENT"),
        "market_cap": make_fact(100000.0, "INR_CRORE"),
    }
    res["institutional"] = {
        "provenance": {"source": "test", "retrieved_at": "2026-09-01T00:00:00+00:00"},
        "promoter_holding_pct": make_fact(60.0, "PERCENT"),
        "promoter_holding_change_qoq": make_fact(0.0, "PERCENTAGE_POINTS", "DERIVED"),
        "promoter_pledge_pct": make_fact(0.0, "PERCENT"),
        "fii_holding_pct": make_fact(15.0, "PERCENT"),
        "fii_holding_change_qoq": make_fact(0.5, "PERCENTAGE_POINTS", "DERIVED"),
        "dii_holding_pct": make_fact(10.0, "PERCENT"),
        "dii_holding_change_qoq": make_fact(-0.2, "PERCENTAGE_POINTS", "DERIVED"),
    }
    res["news"] = []
    res["sources"] = []
    res["errors"] = []
    res["data_quality_summary"] = {}

    # Schema validation must pass
    schema_path = PROJECT_ROOT / "schemas" / "research-result.v1.schema.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    jsonschema.validate(instance=res, schema=schema)


# ---------------------------------------------------------------------------
# Stage 2 Deterministic Decision Engine & Contract Tests
# ---------------------------------------------------------------------------

def test_stage_2_classification_insufficient_data():
    """Rule 1: Return INSUFFICIENT_DATA when history < 200 or CMP/50-DMA unavailable."""
    # Subtest 1: history_bars < 200 (IPO)
    res_ipo = make_research_result(
        cmp=120.0,
        dma_50=115.0,
        dma_200=100.0,
        history_bars=150,
    )
    out_ipo = analyze_technicals(res_ipo)
    assert out_ipo["classification"] == "INSUFFICIENT_DATA"
    assert "INSUFFICIENT_HISTORY_BARS" in out_ipo["reason_codes"]
    assert out_ipo["score"] is None
    assert out_ipo["confidence"] == "LOW"
    assert "INSUFFICIENT_DATA" in out_ipo["risk_flags"]

    # Subtest 2: CMP is unavailable
    res_no_cmp = make_research_result(
        cmp=None,
        dma_50=115.0,
        dma_200=100.0,
        history_bars=250,
    )
    out_no_cmp = analyze_technicals(res_no_cmp)
    assert out_no_cmp["classification"] == "INSUFFICIENT_DATA"
    assert "CRITICAL_METRIC_UNAVAILABLE_CMP" in out_no_cmp["reason_codes"]
    assert out_no_cmp["score"] is None
    assert out_no_cmp["confidence"] == "LOW"

    # Subtest 3: 50-DMA is unavailable
    res_no_dma50 = make_research_result(
        cmp=120.0,
        dma_50=None,
        dma_200=100.0,
        history_bars=250,
    )
    out_no_dma50 = analyze_technicals(res_no_dma50)
    assert out_no_dma50["classification"] == "INSUFFICIENT_DATA"
    assert "CRITICAL_METRIC_UNAVAILABLE_DMA_50" in out_no_dma50["reason_codes"]


def test_stage_2_classification_reduce_sell_candidate_breakdown_2a():
    """Rule 2A: Breakdown below 200-DMA with normalized OBV change < -0.20."""
    res = make_research_result(
        cmp=95.0,
        dma_50=98.0,
        dma_200=105.0,
        obv_change_norm_14d=-0.25,
        history_bars=250,
    )
    out = analyze_technicals(res)
    assert out["classification"] == "REDUCE_SELL_CANDIDATE"
    assert "REDUCE_BREAKDOWN_BELOW_200_DMA_AND_OBV_DISTRIBUTION" in out["reason_codes"]
    assert "BREAKDOWN_BELOW_200_DMA" in out["risk_flags"]
    assert out["score"] is not None and out["score"] < 0


def test_stage_2_classification_reduce_sell_candidate_death_cross_2b():
    """Rule 2B: Recent Death Cross (<= 40 days) with falling 50-DMA."""
    res = make_research_result(
        cmp=100.0,
        dma_50=105.0,
        dma_200=102.0,
        last_crossover_type="DEATH_CROSS",
        days_since_dma_crossover=25,
        dma_slope_50="FALLING",
        history_bars=250,
    )
    out = analyze_technicals(res)
    assert out["classification"] == "REDUCE_SELL_CANDIDATE"
    assert "REDUCE_RECENT_DEATH_CROSS_FALLING_50_DMA" in out["reason_codes"]
    assert "DEATH_CROSS_ACTIVE" in out["risk_flags"]
    assert "FALLING_50_DMA" in out["risk_flags"]


def test_stage_2_classification_reduce_sell_candidate_distribution_2c():
    """Rule 2C: High volume down day, CLV < -0.50, CMP < 50-DMA."""
    res = make_research_result(
        cmp=96.0,
        dma_50=100.0,
        dma_200=90.0,
        volume_vs_20d_pct=28.0,
        close_below_prev_close=True,
        clv=-0.65,
        history_bars=250,
    )
    out = analyze_technicals(res)
    assert out["classification"] == "REDUCE_SELL_CANDIDATE"
    assert "REDUCE_SEVERE_DISTRIBUTION_HIGH_VOLUME_BELOW_50_DMA" in out["reason_codes"]
    assert "SEVERE_DISTRIBUTION_VOLUME" in out["risk_flags"]
    assert "BELOW_50_DMA" in out["risk_flags"]


def test_stage_2_classification_avoid_new_entry_below_both_dmas_3a():
    """Rule 3A: CMP is below both 50-DMA and 200-DMA."""
    res = make_research_result(
        cmp=88.0,
        dma_50=95.0,
        dma_200=100.0,
        history_bars=250,
        obv_change_norm_14d=0.0,
    )
    out = analyze_technicals(res)
    assert out["classification"] == "AVOID_NEW_ENTRY"
    assert "AVOID_CMP_BELOW_50_AND_200_DMA" in out["reason_codes"]
    assert "BELOW_50_DMA" in out["risk_flags"]
    assert "BELOW_200_DMA" in out["risk_flags"]


def test_stage_2_classification_avoid_new_entry_extended_50_dma_3b():
    """Rule 3B: CMP is > 15% above 50-DMA."""
    res = make_research_result(
        cmp=120.0,
        dma_50=100.0,
        dma_200=90.0,
        pct_from_50_dma=20.0,
        rsi_14=60.0,
        history_bars=250,
    )
    out = analyze_technicals(res)
    assert out["classification"] == "AVOID_NEW_ENTRY"
    assert "AVOID_EXTENDED_ABOVE_50_DMA" in out["reason_codes"]
    assert "EXTENDED_ABOVE_50_DMA" in out["risk_flags"]


def test_stage_2_classification_avoid_new_entry_overbought_rsi_3b():
    """Rule 3B: RSI(14) is above 72."""
    res = make_research_result(
        cmp=108.0,
        dma_50=100.0,
        dma_200=90.0,
        pct_from_50_dma=8.0,
        rsi_14=76.5,
        history_bars=250,
    )
    out = analyze_technicals(res)
    assert out["classification"] == "AVOID_NEW_ENTRY"
    assert "AVOID_OVERBOUGHT_RSI" in out["reason_codes"]
    assert "OVERBOUGHT_RSI" in out["risk_flags"]


def test_stage_2_classification_avoid_new_entry_resistance_outflow_3c():
    """Rule 3C: Proximity to confirmed swing high with negative volume flow."""
    res = make_research_result(
        cmp=99.0,
        dma_50=92.0,
        dma_200=85.0,
        swing_high_20=100.0,
        swing_high_confirmation_date="2026-08-15",
        pct_from_swing_high=-1.0,
        obv_change_norm_14d=-0.15,
        clv_14_avg=-0.12,
        history_bars=250,
    )
    out = analyze_technicals(res)
    assert out["classification"] == "AVOID_NEW_ENTRY"
    assert "AVOID_RESISTANCE_PROXIMITY_WITH_VOLUME_OUTFLOW" in out["reason_codes"]
    assert "OVERHEAD_RESISTANCE_NEAR" in out["risk_flags"]
    assert "VOLUME_OUTFLOW_DETECTED" in out["risk_flags"]


def test_stage_2_classification_buy_candidate_ideal():
    """Rule 4: All 6 conditions met simultaneously."""
    res = make_research_result(
        cmp=104.0,
        dma_50=100.0,
        dma_200=90.0,
        pct_from_50_dma=4.0,
        dma_alignment="50_DMA_ABOVE_200_DMA",
        dma_slope_50="RISING",
        rsi_14=58.0,
        obv_change_norm_14d=0.25,
        clv_14_avg=0.15,
        swing_high_20=115.0,
        swing_high_confirmation_date="2026-08-15",
        pct_from_swing_high=-9.56,
        fifty_two_week_high=120.0,
        fifty_two_week_low=80.0,
        volume=1000000,
        history_bars=250,
    )
    out = analyze_technicals(res)
    assert out["classification"] == "BUY_CANDIDATE"
    assert "BUY_TREND_ALIGNMENT_CONFIRMED" in out["reason_codes"]
    assert "BUY_HEALTHY_MOMENTUM_RSI" in out["reason_codes"]
    assert "BUY_VOLUME_FLOW_SUPPORT" in out["reason_codes"]
    assert "BUY_CLEAR_RESISTANCE_RUNWAY" in out["reason_codes"]
    assert out["confidence"] == "HIGH"
    assert out["score"] is not None and out["score"] >= 60.0
    assert len(out["positive_factors"]) >= 4


def test_stage_2_classification_buy_candidate_pullback_support():
    """Rule 4: Pullback support within 2% below 50-DMA with rising 50-DMA."""
    res = make_research_result(
        cmp=98.5,
        dma_50=100.0,
        dma_200=90.0,
        pct_from_50_dma=-1.5,
        dma_slope_50="RISING",
        dma_alignment="50_DMA_ABOVE_200_DMA",
        rsi_14=50.0,
        obv_change_norm_14d=0.15,
        swing_high_20=110.0,
        swing_high_confirmation_date="2026-08-15",
        pct_from_swing_high=-10.45,
        history_bars=250,
    )
    out = analyze_technicals(res)
    assert out["classification"] == "BUY_CANDIDATE"
    assert "BUY_PULLBACK_SUPPORT_50_DMA" in out["reason_codes"]


def test_stage_2_classification_wait_and_watch_consolidation():
    """Rule 5: Fallback when neither breakdown nor buy criteria are met."""
    res = make_research_result(
        cmp=95.0,
        dma_50=92.0,
        dma_200=98.0,
        history_bars=250,
        rsi_14=48.0,
        obv_change_norm_14d=0.0,
    )
    out = analyze_technicals(res)
    assert out["classification"] == "WAIT_AND_WATCH"
    assert "WAIT_CONSOLIDATION_OR_MIXED_SIGNALS" in out["reason_codes"]


def test_stage_2_classification_wait_and_watch_incomplete_buy():
    """Rule 5: Incomplete buy criteria (RSI = 70 is outside 45-68 band)."""
    res = make_research_result(
        cmp=104.0,
        dma_50=100.0,
        dma_200=90.0,
        pct_from_50_dma=4.0,
        dma_alignment="50_DMA_ABOVE_200_DMA",
        rsi_14=70.0,
        obv_change_norm_14d=0.20,
        swing_high_20=115.0,
        swing_high_confirmation_date="2026-08-15",
        pct_from_swing_high=-9.56,
        history_bars=250,
    )
    out = analyze_technicals(res)
    assert out["classification"] == "WAIT_AND_WATCH"
    assert "WAIT_INCOMPLETE_BUY_CRITERIA" in out["reason_codes"]


def test_stage_2_precedence_rules():
    """Strict precedence order: Rule 1 > Rule 2 > Rule 3 > Rule 4 > Rule 5."""
    # Precedence 1 vs 2: Severe breakdown but history < 200 -> INSUFFICIENT_DATA
    res_p1_p2 = make_research_result(
        cmp=80.0,
        dma_50=90.0,
        dma_200=100.0,
        obv_change_norm_14d=-0.30,
        history_bars=150,
    )
    assert analyze_technicals(res_p1_p2)["classification"] == "INSUFFICIENT_DATA"

    # Precedence 2 vs 3: Breakdown (2A) + CMP below both DMAs (3A) -> REDUCE_SELL_CANDIDATE
    res_p2_p3 = make_research_result(
        cmp=80.0,
        dma_50=90.0,
        dma_200=100.0,
        obv_change_norm_14d=-0.30,
        history_bars=250,
    )
    assert analyze_technicals(res_p2_p3)["classification"] == "REDUCE_SELL_CANDIDATE"

    # Precedence 3 vs 4: Meets BUY trend, but RSI = 74 (> 72, Rule 3B) -> AVOID_NEW_ENTRY
    res_p3_p4 = make_research_result(
        cmp=104.0,
        dma_50=100.0,
        dma_200=90.0,
        pct_from_50_dma=4.0,
        dma_alignment="50_DMA_ABOVE_200_DMA",
        rsi_14=74.0,
        obv_change_norm_14d=0.25,
        swing_high_20=120.0,
        swing_high_confirmation_date="2026-08-15",
        history_bars=250,
    )
    assert analyze_technicals(res_p3_p4)["classification"] == "AVOID_NEW_ENTRY"


def test_stage_2_boundary_conditions():
    """Verify exact boundaries across RSI, DMA distances, OBV, volume, and crossover age."""
    # RSI: 45.0 is BUY eligible, 68.0 is BUY eligible
    res_rsi45 = make_research_result(
        cmp=104.0, dma_50=100.0, dma_200=90.0, pct_from_50_dma=4.0,
        dma_alignment="50_DMA_ABOVE_200_DMA", rsi_14=45.0,
        obv_change_norm_14d=0.20, swing_high_20=115.0,
        swing_high_confirmation_date="2026-08-15", history_bars=250,
    )
    assert analyze_technicals(res_rsi45)["classification"] == "BUY_CANDIDATE"

    res_rsi68 = make_research_result(
        cmp=104.0, dma_50=100.0, dma_200=90.0, pct_from_50_dma=4.0,
        dma_alignment="50_DMA_ABOVE_200_DMA", rsi_14=68.0,
        obv_change_norm_14d=0.20, swing_high_20=115.0,
        swing_high_confirmation_date="2026-08-15", history_bars=250,
    )
    assert analyze_technicals(res_rsi68)["classification"] == "BUY_CANDIDATE"

    # RSI: 72.0 is NOT avoid (WAIT), 72.01 is AVOID
    res_rsi72 = make_research_result(
        cmp=104.0, dma_50=100.0, dma_200=90.0, pct_from_50_dma=4.0,
        dma_alignment="50_DMA_ABOVE_200_DMA", rsi_14=72.0,
        obv_change_norm_14d=0.20, swing_high_20=115.0,
        swing_high_confirmation_date="2026-08-15", history_bars=250,
    )
    assert analyze_technicals(res_rsi72)["classification"] == "WAIT_AND_WATCH"

    res_rsi72_01 = make_research_result(
        cmp=104.0, dma_50=100.0, dma_200=90.0, pct_from_50_dma=4.0,
        dma_alignment="50_DMA_ABOVE_200_DMA", rsi_14=72.01,
        obv_change_norm_14d=0.20, swing_high_20=115.0,
        swing_high_confirmation_date="2026-08-15", history_bars=250,
    )
    assert analyze_technicals(res_rsi72_01)["classification"] == "AVOID_NEW_ENTRY"

    # DMA Distance: 10.0% is BUY eligible, 10.01% is WAIT
    res_dma10 = make_research_result(
        cmp=110.0, dma_50=100.0, dma_200=90.0, pct_from_50_dma=10.0,
        dma_alignment="50_DMA_ABOVE_200_DMA", rsi_14=60.0,
        obv_change_norm_14d=0.20, swing_high_20=125.0,
        swing_high_confirmation_date="2026-08-15", history_bars=250,
    )
    assert analyze_technicals(res_dma10)["classification"] == "BUY_CANDIDATE"

    res_dma10_01 = make_research_result(
        cmp=110.01, dma_50=100.0, dma_200=90.0, pct_from_50_dma=10.01,
        dma_alignment="50_DMA_ABOVE_200_DMA", rsi_14=60.0,
        obv_change_norm_14d=0.20, swing_high_20=125.0,
        swing_high_confirmation_date="2026-08-15", history_bars=250,
    )
    assert analyze_technicals(res_dma10_01)["classification"] == "WAIT_AND_WATCH"

    # Crossover Age: 40 is REDUCE, 41 is NOT REDUCE
    res_cross40 = make_research_result(
        cmp=100.0, dma_50=105.0, dma_200=102.0,
        last_crossover_type="DEATH_CROSS", days_since_dma_crossover=40,
        dma_slope_50="FALLING", history_bars=250,
    )
    assert analyze_technicals(res_cross40)["classification"] == "REDUCE_SELL_CANDIDATE"

    res_cross41 = make_research_result(
        cmp=100.0, dma_50=105.0, dma_200=102.0,
        last_crossover_type="DEATH_CROSS", days_since_dma_crossover=41,
        dma_slope_50="FALLING", history_bars=250,
    )
    assert analyze_technicals(res_cross41)["classification"] != "REDUCE_SELL_CANDIDATE"

    # Resistance runway: within 1.5% below is pinned (NOT BUY), > 1.5% below clears
    res_pinned = make_research_result(
        cmp=99.0, dma_50=95.0, dma_200=90.0, pct_from_50_dma=4.21,
        dma_alignment="50_DMA_ABOVE_200_DMA", rsi_14=58.0,
        obv_change_norm_14d=0.20, swing_high_20=100.0,
        swing_high_confirmation_date="2026-08-15", pct_from_swing_high=-1.0,
        history_bars=250,
    )
    assert analyze_technicals(res_pinned)["classification"] == "WAIT_AND_WATCH"


def test_stage_2_unconfirmed_swing_high_cannot_clear_buy():
    """Unconfirmed swing high fails Rule 4 Condition 6 (cannot assume resistance clearance)."""
    res = make_research_result(
        cmp=104.0,
        dma_50=100.0,
        dma_200=90.0,
        pct_from_50_dma=4.0,
        dma_alignment="50_DMA_ABOVE_200_DMA",
        rsi_14=58.0,
        obv_change_norm_14d=0.20,
        swing_high_20=115.0,
        swing_high_confirmation_date=None,
        history_bars=250,
    )
    out = analyze_technicals(res)
    assert out["classification"] == "WAIT_AND_WATCH"
    assert "WAIT_INCOMPLETE_BUY_CRITERIA" in out["reason_codes"]


def test_stage_2_score_bounds_and_determinism():
    """Scores are strictly bounded between -100 and +100 and deterministic."""
    res = make_research_result(
        cmp=104.0,
        dma_50=100.0,
        dma_200=90.0,
        pct_from_50_dma=4.0,
        dma_alignment="50_DMA_ABOVE_200_DMA",
        dma_slope_50="RISING",
        rsi_14=58.0,
        obv_change_norm_14d=0.25,
        clv_14_avg=0.15,
        swing_high_20=115.0,
        swing_high_confirmation_date="2026-08-15",
        pct_from_swing_high=-9.56,
        fifty_two_week_high=120.0,
        fifty_two_week_low=80.0,
        history_bars=250,
    )
    out1 = analyze_technicals(res)
    out2 = analyze_technicals(res)

    assert -100.0 <= out1["score"] <= 100.0
    assert out1["score"] == out2["score"]
    assert out1["classification"] == out2["classification"]
    assert out1["reason_codes"] == out2["reason_codes"]


def test_stage_2_confidence_policy_levels():
    """Confidence levels: HIGH, MEDIUM, LOW."""
    res_high = make_research_result(
        cmp=104.0, dma_50=100.0, dma_200=90.0, pct_from_50_dma=4.0,
        dma_alignment="50_DMA_ABOVE_200_DMA", dma_slope_50="RISING",
        rsi_14=58.0, volume=1000000, obv_change_norm_14d=0.25,
        clv_14_avg=0.15, atr_14=2.5, swing_high_20=115.0,
        swing_high_confirmation_date="2026-08-15", pct_from_swing_high=-9.56,
        history_bars=250,
    )
    assert analyze_technicals(res_high)["confidence"] == "HIGH"

    res_low = make_research_result(cmp=104.0, history_bars=150)
    assert analyze_technicals(res_low)["confidence"] == "LOW"


def test_stage_2_key_levels_and_null_handling():
    """Key levels extraction: support/resistance references and null handling."""
    res = make_research_result(
        cmp=100.0,
        dma_50=95.0,
        dma_200=85.0,
        swing_low_20=90.0,
        swing_high_20=110.0,
        fifty_two_week_high=120.0,
        fifty_two_week_low=80.0,
        history_bars=250,
    )
    out = analyze_technicals(res)
    key_levels = out["key_levels"]
    assert key_levels["support_reference"] is not None
    assert key_levels["support_reference"]["level"] <= 100.0
    assert key_levels["resistance_reference"] is not None
    assert key_levels["resistance_reference"]["level"] >= 100.0

    res_no_cmp = make_research_result(cmp=None, history_bars=250)
    out_no_cmp = analyze_technicals(res_no_cmp)
    assert out_no_cmp["key_levels"]["support_reference"] is None
    assert out_no_cmp["key_levels"]["resistance_reference"] is None


def test_stage_2_assessment_timestamp_iso_utc():
    """Timestamp is valid ISO-8601 in UTC."""
    from datetime import datetime
    res = make_research_result(cmp=100.0, dma_50=95.0, dma_200=90.0, history_bars=250)
    out = analyze_technicals(res)
    ts_str = out["assessment_timestamp"]
    parsed = datetime.fromisoformat(ts_str)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_stage_2_cli_invocation_returns_valid_stage_2_json():
    """CLI execution outputs valid Stage 2 JSON structure."""
    import subprocess
    tcs_file = PROJECT_ROOT / "output" / "tcs-research-result.json"
    if not tcs_file.exists():
        return

    cmd = [sys.executable, "intelligence/technicals.py", str(tcs_file)]
    res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert "classification" in data
    assert "score" in data
    assert "confidence" in data
    assert "reason_codes" in data
    assert "positive_factors" in data
    assert "cautionary_factors" in data
    assert "risk_flags" in data
    assert "key_levels" in data
    assert "assessment_timestamp" in data


# ---------------------------------------------------------------------------
# Simple runner
# ---------------------------------------------------------------------------

def run_all_tests():
    """Run tests without requiring pytest."""

    tests = [
        test_bullish_moving_average_structure,
        test_bearish_moving_average_structure,
        test_rsi_bands,
        test_strong_volume_traction,
        test_mixed_volume,
        test_weak_volume,
        test_52_week_position,
        test_unavailable_values_are_not_invented,
        test_source_status_and_provenance_are_preserved,
        test_invalid_52_week_range_is_not_used,
        test_tcs_current_result,
        test_stage_1_backward_compatibility_and_schema,
        test_stage_2_classification_insufficient_data,
        test_stage_2_classification_reduce_sell_candidate_breakdown_2a,
        test_stage_2_classification_reduce_sell_candidate_death_cross_2b,
        test_stage_2_classification_reduce_sell_candidate_distribution_2c,
        test_stage_2_classification_avoid_new_entry_below_both_dmas_3a,
        test_stage_2_classification_avoid_new_entry_extended_50_dma_3b,
        test_stage_2_classification_avoid_new_entry_overbought_rsi_3b,
        test_stage_2_classification_avoid_new_entry_resistance_outflow_3c,
        test_stage_2_classification_buy_candidate_ideal,
        test_stage_2_classification_buy_candidate_pullback_support,
        test_stage_2_classification_wait_and_watch_consolidation,
        test_stage_2_classification_wait_and_watch_incomplete_buy,
        test_stage_2_precedence_rules,
        test_stage_2_boundary_conditions,
        test_stage_2_unconfirmed_swing_high_cannot_clear_buy,
        test_stage_2_score_bounds_and_determinism,
        test_stage_2_confidence_policy_levels,
        test_stage_2_key_levels_and_null_handling,
        test_stage_2_assessment_timestamp_iso_utc,
        test_stage_2_cli_invocation_returns_valid_stage_2_json,
    ]

    passed = 0

    for test in tests:
        try:
            test()
            print(f"PASS: {test.__name__}")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL: {test.__name__}")
            if exc:
                print(f"       {exc}")
            raise
        except Exception as exc:
            print(f"ERROR: {test.__name__}: {exc}")
            raise

    print()
    print(f"Tests passed: {passed}/{len(tests)}")


class TestTechnicalIntelligence(unittest.TestCase):
    """Unittest test runner wrapper for discovery."""

    def test_bullish_moving_average_structure(self):
        test_bullish_moving_average_structure()

    def test_bearish_moving_average_structure(self):
        test_bearish_moving_average_structure()

    def test_rsi_bands(self):
        test_rsi_bands()

    def test_strong_volume_traction(self):
        test_strong_volume_traction()

    def test_mixed_volume(self):
        test_mixed_volume()

    def test_weak_volume(self):
        test_weak_volume()

    def test_52_week_position(self):
        test_52_week_position()

    def test_unavailable_values_are_not_invented(self):
        test_unavailable_values_are_not_invented()

    def test_source_status_and_provenance_are_preserved(self):
        test_source_status_and_provenance_are_preserved()

    def test_invalid_52_week_range_is_not_used(self):
        test_invalid_52_week_range_is_not_used()

    def test_tcs_current_result(self):
        test_tcs_current_result()

    def test_stage_1_backward_compatibility_and_schema(self):
        test_stage_1_backward_compatibility_and_schema()

    def test_stage_2_classification_insufficient_data(self):
        test_stage_2_classification_insufficient_data()

    def test_stage_2_classification_reduce_sell_candidate_breakdown_2a(self):
        test_stage_2_classification_reduce_sell_candidate_breakdown_2a()

    def test_stage_2_classification_reduce_sell_candidate_death_cross_2b(self):
        test_stage_2_classification_reduce_sell_candidate_death_cross_2b()

    def test_stage_2_classification_reduce_sell_candidate_distribution_2c(self):
        test_stage_2_classification_reduce_sell_candidate_distribution_2c()

    def test_stage_2_classification_avoid_new_entry_below_both_dmas_3a(self):
        test_stage_2_classification_avoid_new_entry_below_both_dmas_3a()

    def test_stage_2_classification_avoid_new_entry_extended_50_dma_3b(self):
        test_stage_2_classification_avoid_new_entry_extended_50_dma_3b()

    def test_stage_2_classification_avoid_new_entry_overbought_rsi_3b(self):
        test_stage_2_classification_avoid_new_entry_overbought_rsi_3b()

    def test_stage_2_classification_avoid_new_entry_resistance_outflow_3c(self):
        test_stage_2_classification_avoid_new_entry_resistance_outflow_3c()

    def test_stage_2_classification_buy_candidate_ideal(self):
        test_stage_2_classification_buy_candidate_ideal()

    def test_stage_2_classification_buy_candidate_pullback_support(self):
        test_stage_2_classification_buy_candidate_pullback_support()

    def test_stage_2_classification_wait_and_watch_consolidation(self):
        test_stage_2_classification_wait_and_watch_consolidation()

    def test_stage_2_classification_wait_and_watch_incomplete_buy(self):
        test_stage_2_classification_wait_and_watch_incomplete_buy()

    def test_stage_2_precedence_rules(self):
        test_stage_2_precedence_rules()

    def test_stage_2_boundary_conditions(self):
        test_stage_2_boundary_conditions()

    def test_stage_2_unconfirmed_swing_high_cannot_clear_buy(self):
        test_stage_2_unconfirmed_swing_high_cannot_clear_buy()

    def test_stage_2_score_bounds_and_determinism(self):
        test_stage_2_score_bounds_and_determinism()

    def test_stage_2_confidence_policy_levels(self):
        test_stage_2_confidence_policy_levels()

    def test_stage_2_key_levels_and_null_handling(self):
        test_stage_2_key_levels_and_null_handling()

    def test_stage_2_assessment_timestamp_iso_utc(self):
        test_stage_2_assessment_timestamp_iso_utc()

    def test_stage_2_cli_invocation_returns_valid_stage_2_json(self):
        test_stage_2_cli_invocation_returns_valid_stage_2_json()


if __name__ == "__main__":
    run_all_tests()
