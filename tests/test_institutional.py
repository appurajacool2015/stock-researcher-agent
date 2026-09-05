#!/usr/bin/env python3

"""
Tests for intelligence/institutional.py
"""

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(PROJECT_ROOT))

from intelligence.institutional import analyze_institutional


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
            "as_of_date": "2026-06-30",
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
        "institutional": {
            "provenance": {
                "source": "test",
                "source_url": "https://example.com",
                "retrieved_at": "2026-09-01T00:00:00+00:00",
                "as_of_date": "2026-06-30",
            },

            "promoter_holding_pct": make_fact(
                values.get("promoter_holding_pct"),
            ),

            "promoter_holding_change_qoq": make_fact(
                values.get("promoter_holding_change_qoq"),
                "PERCENTAGE_POINTS",
                "DERIVED",
            ),

            "promoter_pledge_pct": make_fact(
                values.get("promoter_pledge_pct"),
            ),

            "fii_holding_pct": make_fact(
                values.get("fii_holding_pct"),
            ),

            "fii_holding_change_qoq": make_fact(
                values.get("fii_holding_change_qoq"),
                "PERCENTAGE_POINTS",
                "DERIVED",
            ),

            "dii_holding_pct": make_fact(
                values.get("dii_holding_pct"),
            ),

            "dii_holding_change_qoq": make_fact(
                values.get("dii_holding_change_qoq"),
                "PERCENTAGE_POINTS",
                "DERIVED",
            ),
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_strong_institutional_increase():
    result = analyze_institutional(
        make_research_result(
            promoter_holding_pct=70.0,
            promoter_holding_change_qoq=1.5,
            fii_holding_pct=12.0,
            fii_holding_change_qoq=1.2,
            dii_holding_pct=15.0,
            dii_holding_change_qoq=0.8,
            promoter_pledge_pct=0.0,
        )
    )

    assert (
        result["signals"]["promoter"]["qoq_change"]["signal"]
        == "STRONG_INCREASE"
    )

    assert (
        result["signals"]["fii"]["qoq_change"]["signal"]
        == "STRONG_INCREASE"
    )

    assert (
        result["signals"]["dii"]["qoq_change"]["signal"]
        == "INCREASE"
    )

    assert (
        result["signals"]["institutional_direction"]["direction"]
        == "NET_INCREASE"
    )


def test_stable_ownership():
    result = analyze_institutional(
        make_research_result(
            promoter_holding_pct=70.0,
            promoter_holding_change_qoq=0.0,
            fii_holding_pct=10.0,
            fii_holding_change_qoq=0.05,
            dii_holding_pct=15.0,
            dii_holding_change_qoq=-0.05,
            promoter_pledge_pct=0.0,
        )
    )

    assert (
        result["signals"]["promoter"]["qoq_change"]["signal"]
        == "STABLE"
    )

    assert (
        result["signals"]["fii"]["qoq_change"]["signal"]
        == "STABLE"
    )

    assert (
        result["signals"]["dii"]["qoq_change"]["signal"]
        == "STABLE"
    )

    assert (
        result["signals"]["institutional_direction"]["direction"]
        == "BROADLY_STABLE"
    )


def test_decreasing_institutional_ownership():
    result = analyze_institutional(
        make_research_result(
            promoter_holding_pct=68.0,
            promoter_holding_change_qoq=-1.5,
            fii_holding_pct=8.0,
            fii_holding_change_qoq=-1.2,
            dii_holding_pct=12.0,
            dii_holding_change_qoq=-0.8,
            promoter_pledge_pct=10.0,
        )
    )

    assert (
        result["signals"]["promoter"]["qoq_change"]["signal"]
        == "STRONG_DECREASE"
    )

    assert (
        result["signals"]["fii"]["qoq_change"]["signal"]
        == "STRONG_DECREASE"
    )

    assert (
        result["signals"]["dii"]["qoq_change"]["signal"]
        == "DECREASE"
    )

    assert (
        result["signals"]["institutional_direction"]["direction"]
        == "NET_DECREASE"
    )


def test_promoter_pledge_bands():
    no_pledge = analyze_institutional(
        make_research_result(
            promoter_pledge_pct=0.0,
        )
    )

    low = analyze_institutional(
        make_research_result(
            promoter_pledge_pct=5.0,
        )
    )

    moderate = analyze_institutional(
        make_research_result(
            promoter_pledge_pct=20.0,
        )
    )

    high = analyze_institutional(
        make_research_result(
            promoter_pledge_pct=40.0,
        )
    )

    very_high = analyze_institutional(
        make_research_result(
            promoter_pledge_pct=60.0,
        )
    )

    assert (
        no_pledge["signals"]["promoter_pledge"]["signal"]["signal"]
        == "NO_PLEDGE_REPORTED"
    )

    assert (
        low["signals"]["promoter_pledge"]["signal"]["signal"]
        == "LOW"
    )

    assert (
        moderate["signals"]["promoter_pledge"]["signal"]["signal"]
        == "MODERATE"
    )

    assert (
        high["signals"]["promoter_pledge"]["signal"]["signal"]
        == "HIGH"
    )

    assert (
        very_high["signals"]["promoter_pledge"]["signal"]["signal"]
        == "VERY_HIGH"
    )


def test_unavailable_values_are_not_invented():
    result = analyze_institutional(
        make_research_result(
            promoter_holding_pct=None,
            promoter_holding_change_qoq=None,
            promoter_pledge_pct=None,
            fii_holding_pct=None,
            fii_holding_change_qoq=None,
            dii_holding_pct=None,
            dii_holding_change_qoq=None,
        )
    )

    assert (
        result["signals"]["promoter"]["qoq_change"]["signal"]
        == "UNAVAILABLE"
    )

    assert (
        result["signals"]["fii"]["qoq_change"]["signal"]
        == "UNAVAILABLE"
    )

    assert (
        result["signals"]["dii"]["qoq_change"]["signal"]
        == "UNAVAILABLE"
    )

    assert (
        result["signals"]["institutional_direction"]["direction"]
        == "INSUFFICIENT_DATA"
    )

    assert (
        result["signals"]["promoter_pledge"]["signal"]["signal"]
        == "UNAVAILABLE"
    )

    assert result["score"] is None
    assert result["overall_bias"] == "INSUFFICIENT_DATA"


def test_percentage_points_are_not_treated_as_percent_change():
    """
    A change of +0.59 means +0.59 percentage points, not +59%.

    The module must preserve the original unit.
    """

    result = analyze_institutional(
        make_research_result(
            fii_holding_pct=9.07,
            fii_holding_change_qoq=0.59,
        )
    )

    signal = result["signals"]["fii"]["qoq_change"]

    assert signal["change_pp"] == 0.59
    assert signal["unit"] == "PERCENTAGE_POINTS"


def test_provenance_is_preserved():
    result = analyze_institutional(
        make_research_result(
            fii_holding_pct=10.0,
            fii_holding_change_qoq=0.5,
        )
    )

    signal = result["signals"]["fii"]["qoq_change"]

    assert signal["source_status"] == "DERIVED"
    assert signal["provenance"]["source"] == "test"
    assert signal["provenance"]["as_of_date"] == "2026-06-30"


def test_no_claim_of_direct_buying_or_selling():
    result = analyze_institutional(
        make_research_result(
            fii_holding_pct=9.0,
            fii_holding_change_qoq=-0.59,
        )
    )

    limitations = " ".join(
        result["limitations"]
    ).lower()

    assert "do not by themselves prove" in limitations
    assert "buying" in limitations
    assert "selling" in limitations


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

    result = analyze_institutional(
        research_result
    )

    institutional = research_result[
        "institutional"
    ]

    # -----------------------------------------------------------------------
    # Verify canonical values
    # -----------------------------------------------------------------------

    assert (
        institutional["promoter_holding_pct"]["value"]
        == 71.77
    )

    assert (
        institutional["promoter_holding_change_qoq"]["value"]
        == 0.0
    )

    assert (
        institutional["fii_holding_pct"]["value"]
        == 9.07
    )

    assert (
        institutional["fii_holding_change_qoq"]["value"]
        == -0.59
    )

    assert (
        institutional["dii_holding_pct"]["value"]
        == 13.41
    )

    assert (
        institutional["dii_holding_change_qoq"]["value"]
        == 0.07
    )

    assert (
        institutional["promoter_pledge_pct"]["value"]
        is None
    )

    # -----------------------------------------------------------------------
    # Verify intelligence
    # -----------------------------------------------------------------------

    assert (
        result["signals"]["promoter"]["qoq_change"]["signal"]
        == "STABLE"
    )

    assert (
        result["signals"]["fii"]["qoq_change"]["signal"]
        == "DECREASE"
    )

    assert (
        result["signals"]["dii"]["qoq_change"]["signal"]
        == "STABLE"
    )

    assert (
        result["signals"]["institutional_direction"]["direction"]
        == "NET_DECREASE"
    )

    assert (
        result["signals"]["promoter_pledge"]["signal"]["signal"]
        == "UNAVAILABLE"
    )

    assert result["score"] is not None

    assert result["overall_bias"] in {
        "POSITIVE",
        "MIXED",
        "NEGATIVE",
        "INSUFFICIENT_DATA",
    }

    # Derived ownership changes must remain labelled DERIVED.
    assert (
        result["signals"]["fii"]["qoq_change"]["source_status"]
        == "DERIVED"
    )

    assert (
        result["signals"]["dii"]["qoq_change"]["source_status"]
        == "DERIVED"
    )


# ---------------------------------------------------------------------------
# Simple runner
# ---------------------------------------------------------------------------

def run_all_tests():
    """Run tests without requiring pytest."""

    tests = [
        test_strong_institutional_increase,
        test_stable_ownership,
        test_decreasing_institutional_ownership,
        test_promoter_pledge_bands,
        test_unavailable_values_are_not_invented,
        test_percentage_points_are_not_treated_as_percent_change,
        test_provenance_is_preserved,
        test_no_claim_of_direct_buying_or_selling,
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
