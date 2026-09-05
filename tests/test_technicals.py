#!/usr/bin/env python3

"""
Tests for intelligence/technicals.py
"""

import json
import sys
from pathlib import Path


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
        "technicals": {
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
        },
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

    # -----------------------------------------------------------------------
    # Verify canonical source values
    # -----------------------------------------------------------------------

    assert technicals["cmp"]["value"] == 2369.0
    assert technicals["dma_50"]["value"] == 2257.58
    assert technicals["dma_200"]["value"] == 2608.97

    assert technicals["above_50_dma"]["value"] is True
    assert technicals["above_200_dma"]["value"] is False

    assert technicals["rsi_14"]["value"] == 55.17

    assert technicals["volume"]["value"] == 2677188.0
    assert technicals["avg_volume_1w"]["value"] == 2601390.6
    assert round(
        technicals["avg_volume_1m"]["value"],
        2,
    ) == 2733762.48

    assert technicals["volume_vs_1w_pct"]["value"] == 2.91
    assert technicals["volume_vs_1m_pct"]["value"] == -2.07

    assert technicals["volume_above_1w"]["value"] is True
    assert technicals["volume_above_1m"]["value"] is False
    assert technicals["volume_traction"]["value"] is False

    assert technicals["fifty_two_week_high"]["value"] == 3324.9
    assert technicals["fifty_two_week_low"]["value"] == 1982.6

    # -----------------------------------------------------------------------
    # Verify intelligence
    # -----------------------------------------------------------------------

    assert (
        result["signals"]["trend"]["dma_50"]["signal"]
        == "ABOVE"
    )

    assert (
        result["signals"]["trend"]["dma_200"]["signal"]
        == "BELOW"
    )

    assert (
        result["signals"]["momentum"]["rsi_14"]["signal"]
        == "STRONG"
    )

    assert (
        result["signals"]["volume"]["participation"]["signal"]
        == "MIXED"
    )

    assert (
        result["signals"]["range_position"]["fifty_two_week"]["signal"]
        == "MID_RANGE"
    )

    assert result["score"] is not None

    assert result["overall_bias"] in {
        "POSITIVE",
        "MIXED",
        "NEGATIVE",
    }

    # Technical source provenance should survive interpretation.
    assert (
        result["signals"]["trend"]["dma_50"]["provenance"]["source"]
        == "market_data"
    )


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


if __name__ == "__main__":
    run_all_tests()
