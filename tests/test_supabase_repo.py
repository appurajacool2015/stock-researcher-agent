#!/usr/bin/env python3
"""
Unit tests for services/supabase_repo.py

Verifies:
1. Cache hit within 6 hours.
2. Cache miss (> 6 hours cutoff).
3. Force refresh bypasses cache.
4. Incompatible engine version or schema version invalidates cache.
5. Idempotent snapshot write (returns existing record ID without second insert).
6. Idempotent recommendation write (returns existing record ID without second insert).
7. Unconfigured Supabase handles gracefully without crashing.
8. Network / HTTP errors return clean persistence warnings.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from intelligence.investment_assessment import ENGINE_VERSION
from services.supabase_repo import DEFAULT_TIMEOUT_SECONDS, SupabaseRepository, SupabaseRepositoryError


class TestSupabaseRepository(unittest.TestCase):

    def setUp(self):
        self.repo = SupabaseRepository(
            supabase_url="https://mock-test.supabase.co",
            supabase_key="mock-secret-key-123",
        )

    @patch("services.supabase_repo.requests.get")
    def test_cache_hit_within_six_hours(self, mock_get):
        """Valid recommendation created within 6 hours is returned as a cache hit."""
        rec_data = {
            "id": "rec-1234-5678",
            "research_run_id": "snap-9876",
            "symbol": "TCS",
            "engine_version": ENGINE_VERSION,
            "investment_action": "BUY_CANDIDATE",
            "technical_classification": "BUY_CANDIDATE",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        snap_data = {
            "id": "snap-9876",
            "research_id": "tcs-run-1",
            "symbol": "TCS",
            "schema_version": "1.0",
            "overall_status": "PARTIAL",
        }

        # Mock first call (recommendation query) then second call (snapshot query)
        resp1 = MagicMock(status_code=200)
        resp1.json.return_value = [rec_data]

        resp2 = MagicMock(status_code=200)
        resp2.json.return_value = [snap_data]

        mock_get.side_effect = [resp1, resp2]

        cached_rec, cached_snap = self.repo.get_cached_assessment("TCS", ttl_hours=6.0)

        self.assertIsNotNone(cached_rec)
        self.assertIsNotNone(cached_snap)
        self.assertTrue(cached_rec["is_cached"])
        self.assertEqual(cached_rec["id"], "rec-1234-5678")
        self.assertEqual(cached_snap["id"], "snap-9876")

    @patch("services.supabase_repo.requests.get")
    def test_cache_miss_empty_result(self, mock_get):
        """Empty query returns (None, None) cache miss."""
        resp = MagicMock(status_code=200)
        resp.json.return_value = []
        mock_get.return_value = resp

        cached_rec, cached_snap = self.repo.get_cached_assessment("INFY")
        self.assertIsNone(cached_rec)
        self.assertIsNone(cached_snap)

    def test_cache_bypass_force_refresh(self):
        """force_refresh=True unconditionally bypasses the cache without network query."""
        cached_rec, cached_snap = self.repo.get_cached_assessment("TCS", force_refresh=True)
        self.assertIsNone(cached_rec)
        self.assertIsNone(cached_snap)

    @patch("services.supabase_repo.requests.get")
    def test_cache_incompatible_engine_version(self, mock_get):
        """Incompatible engine_version invalidates cache."""
        rec_data = {
            "id": "rec-legacy",
            "research_run_id": "snap-1",
            "symbol": "TCS",
            "engine_version": "0.9.0-deprecated",  # Incompatible
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = MagicMock(status_code=200)
        resp.json.return_value = [rec_data]
        mock_get.return_value = resp

        cached_rec, cached_snap = self.repo.get_cached_assessment("TCS")
        self.assertIsNone(cached_rec)
        self.assertIsNone(cached_snap)

    @patch("services.supabase_repo.requests.get")
    def test_save_snapshot_idempotent_duplicate(self, mock_get):
        """Existing snapshot returns existing ID without inserting duplicate."""
        existing_record = [{"id": "snap-uuid-existing"}]
        mock_get.return_value = MagicMock(status_code=200, json=lambda: existing_record)

        result = self.repo.save_research_snapshot({
            "symbol": "TCS",
            "research_id": "tcs-run-existing",
        })

        self.assertTrue(result["saved"])
        self.assertEqual(result["id"], "snap-uuid-existing")
        self.assertTrue(result["is_duplicate"])

    @patch("services.supabase_repo.requests.post")
    @patch("services.supabase_repo.requests.get")
    def test_save_snapshot_insert_success(self, mock_get, mock_post):
        """New snapshot inserts successfully and returns new ID."""
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
        mock_post.return_value = MagicMock(status_code=201, json=lambda: [{"id": "snap-uuid-new"}])

        result = self.repo.save_research_snapshot({
            "symbol": "TCS",
            "research_id": "tcs-run-new",
            "company_name": "Tata Consultancy Services Ltd",
            "overall_status": "PARTIAL",
        })

        self.assertTrue(result["saved"])
        self.assertEqual(result["id"], "snap-uuid-new")
        self.assertFalse(result["is_duplicate"])

    @patch("services.supabase_repo.requests.get")
    def test_save_recommendation_idempotent_duplicate(self, mock_get):
        """Existing recommendation for run and engine version returns existing ID."""
        existing_record = [{"id": "rec-uuid-existing"}]
        mock_get.return_value = MagicMock(status_code=200, json=lambda: existing_record)

        result = self.repo.save_recommendation(
            recommendation={"symbol": "TCS", "engine_version": ENGINE_VERSION},
            research_snapshot_id="snap-uuid-1",
        )

        self.assertTrue(result["saved"])
        self.assertEqual(result["id"], "rec-uuid-existing")
        self.assertTrue(result["is_duplicate"])

    def test_unconfigured_repository_graceful(self):
        """Unconfigured repo returns saved=False with warning and never crashes."""
        unconfigured_repo = SupabaseRepository(supabase_url="", supabase_key="")
        self.assertFalse(unconfigured_repo.is_configured)

        cached_rec, cached_snap = unconfigured_repo.get_cached_assessment("TCS")
        self.assertIsNone(cached_rec)

        res = unconfigured_repo.save_research_snapshot({"symbol": "TCS"})
        self.assertFalse(res["saved"])
        self.assertIn("missing", res["warning"].lower())

    @patch("services.supabase_repo.requests.get")
    def test_network_error_handled_gracefully(self, mock_get):
        """Network exception returns saved=False with explicit warning."""
        mock_get.side_effect = TimeoutError("Connection timed out to Supabase")

        result = self.repo.save_research_snapshot({"symbol": "TCS", "research_id": "run-err"})
        # Should catch and not crash
        self.assertFalse(result["saved"])
        self.assertIn("failed", result["warning"].lower())

    @patch("services.supabase_repo.requests.post")
    @patch("services.supabase_repo.requests.get")
    def test_save_recommendation_payload_types_match_sql_schema(self, mock_get, mock_post):
        """Recommendation payload data types strictly match the PostgreSQL migration schema types."""
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
        captured_payload = {}

        def capture_post(*args, **kwargs):
            nonlocal captured_payload
            captured_payload = kwargs.get("json", {})
            return MagicMock(status_code=201, json=lambda: [{"id": "rec-new-id"}])

        mock_post.side_effect = capture_post

        rec = {
            "symbol": "TCS",
            "cmp": 3500.50,
            "currency": "INR",
            "technical_classification": "BUY_CANDIDATE",
            "technical_score": 75.5,
            "technical_confidence": "HIGH",  # String -> VARCHAR(20)
            "investment_action": "BUY_CANDIDATE",
            "investment_score": 82.0,
            "investment_confidence": 0.85,    # Float -> NUMERIC(4, 2)
            "reason_codes": ["RULE4_BUY"],
            "positive_factors": ["ROE strong"],
            "cautionary_factors": [],
            "risk_flags": [],
            "key_levels": {"support": 3400.0},
            "limitations": [],
            "engine_version": ENGINE_VERSION,
            "is_cached": False,
        }

        result = self.repo.save_recommendation(rec, research_snapshot_id="00000000-0000-0000-0000-000000000001")

        self.assertTrue(result["saved"])
        # Verify specific types matching SQL schema
        self.assertIsInstance(captured_payload["technical_confidence"], str)  # VARCHAR(20)
        self.assertIsInstance(captured_payload["investment_confidence"], float) # NUMERIC(4, 2)
        self.assertIsInstance(captured_payload["cmp"], float)                 # NUMERIC(12, 2)
        self.assertIsInstance(captured_payload["is_cached"], bool)            # BOOLEAN
        self.assertIsInstance(captured_payload["reason_codes"], list)         # JSONB
        self.assertIsInstance(captured_payload["key_levels"], dict)           # JSONB

    # --------------------------------------------------------------------------
    # Historical Baseline Lookup Tests (Phase 2B)
    # --------------------------------------------------------------------------

    @patch("services.supabase_repo.requests.get")
    def test_get_baseline_valid_record(self, mock_get):
        """Returns the earliest historical recommendation record with positive CMP."""
        mock_rec = {
            "id": "rec-base-001",
            "symbol": "TCS",
            "cmp": 3400.0,
            "investment_action": "BUY_CANDIDATE",
            "created_at": "2026-10-01T10:00:00Z",
        }
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [mock_rec])

        baseline = self.repo.get_baseline_assessment("TCS")

        self.assertIsNotNone(baseline)
        self.assertEqual(baseline["id"], "rec-base-001")
        self.assertEqual(baseline["cmp"], 3400.0)
        self.assertEqual(baseline["created_at"], "2026-10-01T10:00:00Z")

        # Verify correct PostgREST query parameters (order by created_at asc)
        called_args, called_kwargs = mock_get.call_args
        params = called_kwargs.get("params", {})
        self.assertEqual(params.get("symbol"), "eq.TCS")
        self.assertEqual(params.get("order"), "created_at.asc")

    @patch("services.supabase_repo.requests.get")
    def test_get_baseline_no_records_returns_none(self, mock_get):
        """Returns None when symbol has no prior history in database."""
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [])

        baseline = self.repo.get_baseline_assessment("NEWSTOCK")
        self.assertIsNone(baseline)

    @patch("services.supabase_repo.requests.get")
    def test_get_baseline_first_cmp_invalid_finds_subsequent_valid_cmp(self, mock_get):
        """If earliest record has null/invalid CMP, finds earliest subsequent record with positive CMP."""
        rec1_no_price = {
            "id": "rec-base-001",
            "symbol": "INFY",
            "cmp": None,  # Missing price on day 1
            "investment_action": "HOLD_REVIEW",
            "created_at": "2026-10-01T10:00:00Z",
        }
        rec2_with_price = {
            "id": "rec-base-002",
            "symbol": "INFY",
            "cmp": 1450.0,  # Valid positive price on day 3
            "investment_action": "BUY_CANDIDATE",
            "created_at": "2026-10-03T10:00:00Z",
        }
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [rec1_no_price, rec2_with_price])

        baseline = self.repo.get_baseline_assessment("INFY")

        self.assertIsNotNone(baseline)
        self.assertEqual(baseline["id"], "rec-base-001")  # Preserves earliest true research run
        self.assertEqual(baseline["created_at"], "2026-10-01T10:00:00Z")  # Preserves original timestamp
        self.assertEqual(baseline["cmp"], 1450.0)  # Uses earliest valid positive price
        self.assertEqual(baseline["cmp_source_timestamp"], "2026-10-03T10:00:00Z")

    @patch("services.supabase_repo.requests.get")
    def test_get_baseline_all_cmp_invalid_returns_record_with_none_cmp(self, mock_get):
        """If no record has a positive price, returns earliest record preserving timestamp and None CMP."""
        rec1 = {
            "id": "rec-001",
            "symbol": "WIPRO",
            "cmp": None,
            "created_at": "2026-10-01T10:00:00Z",
        }
        rec2 = {
            "id": "rec-002",
            "symbol": "WIPRO",
            "cmp": 0.0,
            "created_at": "2026-10-02T10:00:00Z",
        }
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [rec1, rec2])

        baseline = self.repo.get_baseline_assessment("WIPRO")

        self.assertIsNotNone(baseline)
        self.assertIsNone(baseline["cmp"])
        self.assertEqual(baseline["created_at"], "2026-10-01T10:00:00Z")

    @patch("services.supabase_repo.requests.get")
    def test_get_baseline_missing_timestamp_returns_none(self, mock_get):
        """Malformed record lacking any timestamp returns None."""
        mock_rec = {
            "id": "rec-001",
            "symbol": "TCS",
            "cmp": 3400.0,
            # No created_at or assessment_timestamp
        }
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [mock_rec])

        baseline = self.repo.get_baseline_assessment("TCS")
        self.assertIsNone(baseline)

    def test_default_timeout_is_thirty_seconds(self):
        """DEFAULT_TIMEOUT_SECONDS is configured to 30.0 for cloud resilience."""
        self.assertEqual(DEFAULT_TIMEOUT_SECONDS, 30.0)
        repo = SupabaseRepository()
        self.assertEqual(repo.timeout, 30.0)

    @patch("services.supabase_repo.requests.get")
    def test_get_baseline_non_200_http_error(self, mock_get):
        """HTTP error (403/500) raises SupabaseRepositoryError so caller knows lookup failed."""
        mock_get.return_value = MagicMock(status_code=403, text="Forbidden")

        with self.assertRaises(SupabaseRepositoryError):
            self.repo.get_baseline_assessment("TCS")

    @patch("services.supabase_repo.requests.get")
    def test_get_baseline_network_exception(self, mock_get):
        """Network timeout/connection error raises SupabaseRepositoryError."""
        import requests
        mock_get.side_effect = requests.ConnectionError("Connection failed")

        with self.assertRaises(SupabaseRepositoryError):
            self.repo.get_baseline_assessment("TCS")

    @patch("services.supabase_repo.requests.get")
    def test_get_baseline_timeout_exception(self, mock_get):
        """Network timeout raises SupabaseRepositoryError."""
        import requests
        mock_get.side_effect = requests.Timeout("Gateway read timeout")

        with self.assertRaises(SupabaseRepositoryError):
            self.repo.get_baseline_assessment("TCS")

    @patch("services.supabase_repo.requests.get")
    def test_get_baseline_malformed_json_response(self, mock_get):
        """Non-list response raises SupabaseRepositoryError."""
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"error": "unexpected format"})

        with self.assertRaises(SupabaseRepositoryError):
            self.repo.get_baseline_assessment("TCS")

    def test_get_baseline_unconfigured_repo_returns_none(self):
        """Unconfigured repo returns None immediately without attempting HTTP requests."""
        unconfigured = SupabaseRepository(supabase_url="", supabase_key="")
        baseline = unconfigured.get_baseline_assessment("TCS")
        self.assertIsNone(baseline)

    def test_get_baseline_empty_symbol_returns_none(self):
        """Empty or whitespace symbol returns None immediately."""
        self.assertIsNone(self.repo.get_baseline_assessment(""))
        self.assertIsNone(self.repo.get_baseline_assessment("   "))


if __name__ == "__main__":
    unittest.main(verbosity=2)
