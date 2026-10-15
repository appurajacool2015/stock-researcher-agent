#!/usr/bin/env python3
"""
Unit tests for intelligence/track_record.py

Verifies mathematical calculations, edge cases, and safety rules:
1. Positive price gains (returns correctly calculated).
2. Negative price losses (losses correctly calculated).
3. Missing or non-positive baseline prices (graceful degradation without error).
4. Missing or non-positive current prices (graceful degradation).
5. First-time research (baseline established, no prior return).
6. Elapsed time and duration formatting across days/hours.
7. Verdict continuity vs. verdict shift detection.
8. Required safety disclaimers and non-guarantee notices.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from intelligence.track_record import (
    _parse_timestamp,
    calculate_elapsed_time,
    calculate_price_return,
    calculate_track_record,
)


class TestTrackRecordCalculator(unittest.TestCase):

    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.ten_days_ago = self.now - timedelta(days=10)

    # --------------------------------------------------------------------------
    # 1. Price Return Calculations
    # --------------------------------------------------------------------------

    def test_positive_gain_calculation(self):
        change, return_pct, note = calculate_price_return(3500.0, 3800.0)
        self.assertEqual(change, 300.0)
        self.assertEqual(return_pct, 8.57)
        self.assertIsNone(note)

    def test_negative_loss_calculation(self):
        change, return_pct, note = calculate_price_return(1000.0, 850.0)
        self.assertEqual(change, -150.0)
        self.assertEqual(return_pct, -15.0)
        self.assertIsNone(note)

    def test_flat_price_calculation(self):
        change, return_pct, note = calculate_price_return(2500.0, 2500.0)
        self.assertEqual(change, 0.0)
        self.assertEqual(return_pct, 0.0)
        self.assertIsNone(note)

    def test_missing_baseline_price_returns_graceful_note(self):
        for invalid_base in [None, 0, -100.0, "invalid"]:
            change, return_pct, note = calculate_price_return(invalid_base, 3500.0)
            self.assertIsNone(change)
            self.assertIsNone(return_pct)
            self.assertIn("baseline research price is missing or invalid", note)

    def test_missing_current_price_returns_graceful_note(self):
        for invalid_curr in [None, 0, -50.0, "invalid"]:
            change, return_pct, note = calculate_price_return(3500.0, invalid_curr)
            self.assertIsNone(change)
            self.assertIsNone(return_pct)
            self.assertIn("current market price is missing or invalid", note)

    # --------------------------------------------------------------------------
    # 2. Elapsed Time & Timestamp Parsing
    # --------------------------------------------------------------------------

    def test_parse_timestamp_formats(self):
        # Valid ISO with Z
        dt_z = _parse_timestamp("2026-10-01T10:30:00Z")
        self.assertIsNotNone(dt_z)
        self.assertEqual(dt_z.year, 2026)

        # Valid ISO with timezone offset
        dt_offset = _parse_timestamp("2026-10-01T16:00:00+05:30")
        self.assertIsNotNone(dt_offset)

        # Invalid timestamp returns None
        self.assertIsNone(_parse_timestamp("invalid-date"))
        self.assertIsNone(_parse_timestamp(None))

    def test_calculate_elapsed_time(self):
        # 10 days ago
        days, desc = calculate_elapsed_time(self.ten_days_ago, self.now)
        self.assertEqual(days, 10)
        self.assertEqual(desc, "10 days ago")

        # 1 day ago
        yesterday = self.now - timedelta(days=1, hours=2)
        days, desc = calculate_elapsed_time(yesterday, self.now)
        self.assertEqual(days, 1)
        self.assertEqual(desc, "1 day ago")

        # Same day (< 1 hour)
        just_now = self.now - timedelta(minutes=15)
        days, desc = calculate_elapsed_time(just_now, self.now)
        self.assertEqual(days, 0)
        self.assertEqual(desc, "Earlier today")

        # None baseline
        days, desc = calculate_elapsed_time(None, self.now)
        self.assertEqual(days, 0)
        self.assertEqual(desc, "Unknown duration")

    # --------------------------------------------------------------------------
    # 3. Full Track Record Integration
    # --------------------------------------------------------------------------

    def test_first_time_research_establishes_baseline(self):
        current_assessment = {
            "symbol": "TCS",
            "cmp": 3500.0,
            "investment_action": "BUY_CANDIDATE",
            "assessment_timestamp": self.now.isoformat(),
        }

        # Case: baseline is None
        record = calculate_track_record(current_assessment, baseline_assessment=None)
        self.assertEqual(record["status"], "BASELINE_ESTABLISHED")
        self.assertFalse(record["has_prior_history"])
        self.assertEqual(record["first_researched_price"], 3500.0)
        self.assertEqual(record["initial_verdict"], "BUY_CANDIDATE")
        self.assertIsNone(record["price_change"])
        self.assertIsNone(record["price_return_pct"])
        self.assertIn("Initial research baseline established", record["note"])
        self.assertIn("disclaimer", record)

    def test_same_record_treated_as_baseline_established(self):
        assessment = {
            "id": "rec-123",
            "symbol": "INFY",
            "cmp": 1500.0,
            "investment_action": "HOLD_REVIEW",
            "created_at": self.now.isoformat(),
        }
        # When baseline has identical ID and timestamp as current, no prior history exists
        record = calculate_track_record(assessment, baseline_assessment=assessment)
        self.assertEqual(record["status"], "BASELINE_ESTABLISHED")
        self.assertFalse(record["has_prior_history"])

    def test_subsequent_run_calculates_gain_and_verdict_continuity(self):
        baseline = {
            "id": "rec-001",
            "symbol": "TCS",
            "cmp": 3500.0,
            "investment_action": "BUY_CANDIDATE",
            "created_at": self.ten_days_ago.isoformat(),
        }
        current = {
            "id": "rec-002",
            "symbol": "TCS",
            "cmp": 3800.0,
            "investment_action": "BUY_CANDIDATE",
            "created_at": self.now.isoformat(),
        }

        record = calculate_track_record(current, baseline_assessment=baseline)
        self.assertEqual(record["status"], "TRACK_RECORD_AVAILABLE")
        self.assertTrue(record["has_prior_history"])
        self.assertEqual(record["first_researched_price"], 3500.0)
        self.assertEqual(record["latest_price"], 3800.0)
        self.assertEqual(record["price_change"], 300.0)
        self.assertEqual(record["price_return_pct"], 8.57)
        self.assertEqual(record["days_elapsed"], 10)
        self.assertFalse(record["verdict_changed"])
        self.assertIn("BUY_CANDIDATE (Unchanged)", record["verdict_transition"])
        self.assertIn("causality_disclaimer", record)

    def test_subsequent_run_detects_verdict_shift(self):
        baseline = {
            "id": "rec-001",
            "symbol": "RELIANCE",
            "cmp": 2900.0,
            "investment_action": "BUY_CANDIDATE",
            "created_at": self.ten_days_ago.isoformat(),
        }
        current = {
            "id": "rec-002",
            "symbol": "RELIANCE",
            "cmp": 2750.0,
            "investment_action": "REDUCE_SELL_REVIEW",
            "created_at": self.now.isoformat(),
        }

        record = calculate_track_record(current, baseline_assessment=baseline)
        self.assertTrue(record["verdict_changed"])
        self.assertEqual(record["verdict_transition"], "BUY_CANDIDATE ➔ REDUCE_SELL_REVIEW")
        self.assertEqual(record["price_change"], -150.0)
        self.assertEqual(record["price_return_pct"], -5.17)

    def test_subsequent_run_with_missing_baseline_price(self):
        baseline = {
            "id": "rec-001",
            "symbol": "WIPRO",
            "cmp": None,  # Missing baseline price
            "investment_action": "HOLD_REVIEW",
            "created_at": self.ten_days_ago.isoformat(),
        }
        current = {
            "id": "rec-002",
            "symbol": "WIPRO",
            "cmp": 480.0,
            "investment_action": "HOLD_REVIEW",
            "created_at": self.now.isoformat(),
        }

        record = calculate_track_record(current, baseline_assessment=baseline)
        self.assertTrue(record["has_prior_history"])
        self.assertIsNone(record["price_change"])
        self.assertIsNone(record["price_return_pct"])
        self.assertIn("baseline research price is missing or invalid", record["price_return_note"])


if __name__ == "__main__":
    unittest.main()
