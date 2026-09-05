#!/usr/bin/env python3

"""
Tests for intelligence/fundamentals.py

These tests use the canonical ResearchResult v1 structure:

fundamentals
    ├── pe_ratio
    ├── pb_ratio
    ├── roe
    ├── roce
    ├── debt_to_equity
    ├── sales_growth_3y_cagr
    ├── profit_growth_3y_cagr
    └── market_cap
"""

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(PROJECT_ROOT))

from intelligence.fundamentals import analyze_fundamentals


def make_fact(
    value,
    unit="PERCENT",
    status="VERIFIED",
):
    """Create a canonical ResearchResult v1 fact."""

    return {
        "value": value,
        "unit": unit,
        "status": status,
        "provenance": {
            "source": "test",
            "source_url": "https://example.com",
            "retrieved_at": "2026-09-01T00:00:00+00:00",
            "as_of_date": "2026-03-31",
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
        "fundamentals": {
            "provenance": {
                "source": "test",
                "source_url": "https://example.com",
                "retrieved_at": "2026-09-01T00:00:00+00:00",
                "as_of_date": "2026-03-31",
            },
            "pe_ratio": make_fact(
                values.get("pe_ratio"),
                "RATIO",
            ),
            "pb_ratio": make_fact(
                values.get("pb_ratio"),
                "RATIO",
            ),
            "roe": make_fact(
                values.get("roe"),
                "PERCENT",
            ),
            "roce": make_fact(
                values.get("roce"),
                "PERCENT",
            ),
            "debt_to_equity": make_fact(
                values.get("debt_to_equity"),
                "RATIO",
                "UNAVAILABLE"
                if values.get("debt_to_equity") is None
                else "VERIFIED",
            ),
            "sales_growth_3y_cagr": make_fact(
                values.get("sales_growth_3y_cagr"),
                "PERCENT",
            ),
            "profit_growth_3y_cagr": make_fact(
                values.get("profit_growth_3y_cagr"),
                "PERCENT",
            ),
            "market_cap": make_fact(
                values.get("market_cap"),
                "INR_CRORE",
            ),
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_strong_profitability():
    result = analyze_fundamentals(
        make_research_result(
            roe=25.0,
            roce=30.0,
            sales_growth_3y_cagr=18.0,
            profit_growth_3y_cagr=20.0,
            pe_ratio=14.0,
            pb_ratio=2.0,
            debt_to_equity=0.3,
            market_cap=100000.0,
        )
    )

    assert result["signals"]["profitability"]["bias"] == "POSITIVE"

    assert (
        result["signals"]["profitability"]["roe"]["signal"]
        == "STRONG"
    )

    assert (
        result["signals"]["profitability"]["roce"]["signal"]
        == "STRONG"
    )


def test_moderate_growth():
    result = analyze_fundamentals(
        make_research_result(
            roe=20.0,
            roce=22.0,
            sales_growth_3y_cagr=6.0,
            profit_growth_3y_cagr=8.0,
            pe_ratio=20.0,
            pb_ratio=5.0,
            debt_to_equity=0.5,
            market_cap=100000.0,
        )
    )

    assert (
        result["signals"]["growth"]["sales_growth_3y_cagr"]["signal"]
        == "MODERATE"
    )

    assert (
        result["signals"]["growth"]["profit_growth_3y_cagr"]["signal"]
        == "MODERATE"
    )


def test_weak_growth():
    result = analyze_fundamentals(
        make_research_result(
            roe=8.0,
            roce=9.0,
            sales_growth_3y_cagr=2.0,
            profit_growth_3y_cagr=3.0,
            pe_ratio=45.0,
            pb_ratio=12.0,
            debt_to_equity=2.5,
            market_cap=100000.0,
        )
    )

    assert (
        result["signals"]["growth"]["sales_growth_3y_cagr"]["signal"]
        == "WEAK"
    )

    assert (
        result["signals"]["growth"]["profit_growth_3y_cagr"]["signal"]
        == "WEAK"
    )

    assert (
        result["signals"]["leverage"]["debt_to_equity"]["signal"]
        == "VERY_HIGH"
    )


def test_valuation_bands():
    low = analyze_fundamentals(
        make_research_result(
            pe_ratio=12.0,
            pb_ratio=2.0,
        )
    )

    moderate = analyze_fundamentals(
        make_research_result(
            pe_ratio=20.0,
            pb_ratio=5.0,
        )
    )

    high = analyze_fundamentals(
        make_research_result(
            pe_ratio=35.0,
            pb_ratio=8.0,
        )
    )

    very_high = analyze_fundamentals(
        make_research_result(
            pe_ratio=50.0,
            pb_ratio=12.0,
        )
    )

    assert (
        low["signals"]["valuation"]["pe_ratio"]["signal"]
        == "LOW"
    )

    assert (
        low["signals"]["valuation"]["pb_ratio"]["signal"]
        == "LOW"
    )

    assert (
        moderate["signals"]["valuation"]["pe_ratio"]["signal"]
        == "MODERATE"
    )

    assert (
        moderate["signals"]["valuation"]["pb_ratio"]["signal"]
        == "MODERATE"
    )

    assert (
        high["signals"]["valuation"]["pe_ratio"]["signal"]
        == "HIGH"
    )

    assert (
        high["signals"]["valuation"]["pb_ratio"]["signal"]
        == "HIGH"
    )

    assert (
        very_high["signals"]["valuation"]["pe_ratio"]["signal"]
        == "VERY_HIGH"
    )

    assert (
        very_high["signals"]["valuation"]["pb_ratio"]["signal"]
        == "VERY_HIGH"
    )


def test_unavailable_values_are_not_invented():
    result = analyze_fundamentals(
        make_research_result(
            roe=None,
            roce=None,
            sales_growth_3y_cagr=None,
            profit_growth_3y_cagr=None,
            pe_ratio=None,
            pb_ratio=None,
            debt_to_equity=None,
            market_cap=None,
        )
    )

    assert (
        result["signals"]["profitability"]["roe"]["signal"]
        == "UNAVAILABLE"
    )

    assert (
        result["signals"]["profitability"]["roce"]["signal"]
        == "UNAVAILABLE"
    )

    assert (
        result["signals"]["growth"]["sales_growth_3y_cagr"]["signal"]
        == "UNAVAILABLE"
    )

    assert (
        result["signals"]["growth"]["profit_growth_3y_cagr"]["signal"]
        == "UNAVAILABLE"
    )

    assert (
        result["signals"]["valuation"]["pe_ratio"]["signal"]
        == "UNAVAILABLE"
    )

    assert (
        result["signals"]["valuation"]["pb_ratio"]["signal"]
        == "UNAVAILABLE"
    )

    assert (
        result["signals"]["leverage"]["debt_to_equity"]["signal"]
        == "UNAVAILABLE"
    )

    assert result["score"] is None
    assert result["overall_bias"] == "INSUFFICIENT_DATA"


def test_derived_pb_is_accepted():
    """
    P/B is currently present in ResearchResult v1 as a DERIVED fact.

    The intelligence layer should interpret it while preserving its
    source status rather than treating it as unavailable.
    """

    result = analyze_fundamentals(
        make_research_result(
            pe_ratio=16.2,
            pb_ratio=8.0034,
        )
    )

    pb_signal = result["signals"]["valuation"]["pb_ratio"]

    assert pb_signal["signal"] == "HIGH"
    assert pb_signal["value"] == 8.0034


def test_source_status_and_provenance_are_preserved():
    result = analyze_fundamentals(
        make_research_result(
            roe=51.8,
        )
    )

    roe = result["signals"]["profitability"]["roe"]

    assert roe["source_status"] == "VERIFIED"

    assert roe["provenance"]["source"] == "test"

    assert roe["provenance"]["as_of_date"] == "2026-03-31"


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

    result = analyze_fundamentals(research_result)

    fundamentals = research_result["fundamentals"]

    # Verify the canonical source data.
    assert fundamentals["roe"]["value"] == 51.8
    assert fundamentals["roce"]["value"] == 63.0
    assert fundamentals["sales_growth_3y_cagr"]["value"] == 6.0
    assert fundamentals["profit_growth_3y_cagr"]["value"] == 8.0
    assert fundamentals["pe_ratio"]["value"] == 16.2
    assert fundamentals["pb_ratio"]["value"] == 8.0034
    assert fundamentals["debt_to_equity"]["value"] is None

    # Verify intelligence.
    assert (
        result["signals"]["profitability"]["roe"]["signal"]
        == "STRONG"
    )

    assert (
        result["signals"]["profitability"]["roce"]["signal"]
        == "STRONG"
    )

    assert (
        result["signals"]["growth"]["sales_growth_3y_cagr"]["signal"]
        == "MODERATE"
    )

    assert (
        result["signals"]["growth"]["profit_growth_3y_cagr"]["signal"]
        == "MODERATE"
    )

    assert (
        result["signals"]["valuation"]["pe_ratio"]["signal"]
        == "MODERATE"
    )

    assert (
        result["signals"]["valuation"]["pb_ratio"]["signal"]
        == "HIGH"
    )

    assert (
        result["signals"]["leverage"]["debt_to_equity"]["signal"]
        == "UNAVAILABLE"
    )

    # P/B is DERIVED in the source result.
    assert (
        result["signals"]["valuation"]["pb_ratio"]["source_status"]
        == "DERIVED"
    )

    assert result["overall_bias"] in {
        "POSITIVE",
        "MIXED",
    }

    assert result["score"] is not None


# ---------------------------------------------------------------------------
# Simple runner
# ---------------------------------------------------------------------------

def run_all_tests():
    """Run tests without requiring pytest."""

    tests = [
        test_strong_profitability,
        test_moderate_growth,
        test_weak_growth,
        test_valuation_bands,
        test_unavailable_values_are_not_invented,
        test_derived_pb_is_accepted,
        test_source_status_and_provenance_are_preserved,
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
