#!/usr/bin/env python3
"""
Supabase Historical Persistence & Cache Repository

Purpose
-------
Provides append-only persistence and auditability for research snapshots and
investment recommendations in Supabase via PostgREST.

Key Capabilities:
1. Append-only persistence (research_snapshots & investment_recommendations).
2. Idempotent insertion: retries do not create duplicate records for identical runs.
3. 6-hour caching with compatibility verification (schema_version, engine_version).
4. Force-refresh bypass.
5. Graceful failure handling: if Supabase is offline or unconfigured, analysis is preserved
   and explicit persistence warnings are issued without crashing.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import requests

from intelligence.investment_assessment import ENGINE_VERSION

DEFAULT_CACHE_TTL_HOURS = 6.0
DEFAULT_TIMEOUT_SECONDS = 30.0


class SupabaseRepositoryError(Exception):
    """Raised when a Supabase operation encounters a network, timeout, or server error."""
    pass


class SupabaseRepository:
    """PostgREST client for append-only stock research audit logs and caching."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.url = (supabase_url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
        # Accept service role key first for persistence, then anon key or generic supabase key
        self.key = (
            supabase_key
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_KEY")
            or os.environ.get("SUPABASE_ANON_KEY")
            or ""
        )
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        """Return True if both URL and Key are provided."""
        return bool(self.url and self.key)

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    # ==========================================================================
    # CACHE LOOKUP
    # ==========================================================================

    def get_cached_assessment(
        self,
        symbol: str,
        ttl_hours: float = DEFAULT_CACHE_TTL_HOURS,
        force_refresh: bool = False,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Check Supabase for a compatible research snapshot and recommendation within TTL.

        Returns:
            (cached_recommendation, cached_snapshot) if valid cache hit, else (None, None).
        """
        if force_refresh:
            return None, None

        if not self.is_configured:
            return None, None

        norm_symbol = symbol.strip().upper()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=ttl_hours)).isoformat()

        # Query latest recommendation for symbol within TTL
        endpoint = f"{self.url}/rest/v1/investment_recommendations"
        params = {
            "symbol": f"eq.{norm_symbol}",
            "created_at": f"gte.{cutoff}",
            "order": "created_at.desc",
            "limit": "1",
        }

        try:
            resp = requests.get(
                endpoint,
                headers=self._headers(),
                params=params,
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return None, None

            records = resp.json()
            if not isinstance(records, list) or not records:
                return None, None

            rec = records[0]

            # Validate engine version compatibility
            if rec.get("engine_version") != ENGINE_VERSION:
                return None, None

            research_run_id = rec.get("research_run_id")
            if not research_run_id:
                return None, None

            # Fetch linked snapshot
            snap_endpoint = f"{self.url}/rest/v1/research_snapshots"
            snap_params = {
                "id": f"eq.{research_run_id}",
                "limit": "1",
            }
            snap_resp = requests.get(
                snap_endpoint,
                headers=self._headers(),
                params=snap_params,
                timeout=self.timeout,
            )
            if snap_resp.status_code != 200:
                return None, None

            snap_records = snap_resp.json()
            if not isinstance(snap_records, list) or not snap_records:
                return None, None

            snap = snap_records[0]

            # Verify schema version compatibility
            if snap.get("schema_version") != "1.0":
                return None, None

            # Enrich recommendation with cache metadata
            rec_result = dict(rec)
            rec_result["is_cached"] = True
            rec_result["cache_metadata"] = {
                "original_created_at": rec.get("created_at"),
                "ttl_hours": ttl_hours,
                "cached_research_run_id": str(research_run_id),
            }

            return rec_result, snap

        except Exception:
            # Network or parsing failure during cache check falls back cleanly to fresh fetch
            return None, None

    # ==========================================================================
    # HISTORICAL BASELINE LOOKUP
    # ==========================================================================

    def get_baseline_assessment(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch the earliest historical investment recommendation baseline for a symbol.

        Requirements:
        1. Selects the earliest record for the symbol (order=created_at.asc).
        2. Requires a reliable timestamp (created_at or assessment_timestamp).
        3. Identifies the earliest valid positive CMP. If the very first record has a
           missing or non-positive CMP, inspects subsequent historical records to find
           the earliest valid positive CMP to serve as the price baseline, while
           preserving the true first research timestamp.
        4. Gracefully handles Supabase HTTP non-200 errors, network failures, timeouts,
           empty responses, and malformed records without raising exceptions.
        5. Does not mutate or delete any historical record.
        """
        if not self.is_configured:
            return None

        norm_symbol = str(symbol).strip().upper()
        if not norm_symbol:
            return None

        endpoint = f"{self.url}/rest/v1/investment_recommendations"
        params = {
            "symbol": f"eq.{norm_symbol}",
            "order": "created_at.asc",
            "limit": "10",
        }

        try:
            resp = requests.get(
                endpoint,
                headers=self._headers(),
                params=params,
                timeout=self.timeout,
            )
        except Exception as exc:
            raise SupabaseRepositoryError(
                f"Failed to query baseline for {norm_symbol} due to connection/timeout error: {exc}"
            ) from exc

        if resp.status_code != 200:
            raise SupabaseRepositoryError(
                f"Supabase baseline query returned HTTP {resp.status_code}: {resp.text}"
            )

        try:
            records = resp.json()
        except Exception as exc:
            raise SupabaseRepositoryError(
                f"Supabase baseline query returned non-JSON response: {exc}"
            ) from exc

        if not isinstance(records, list):
            raise SupabaseRepositoryError(
                f"Supabase baseline query returned invalid payload format for {norm_symbol}"
            )

        if not records:
            # Genuinely no records exist for this symbol in the database
            return None

        first_rec = records[0]
        if not isinstance(first_rec, dict):
            return None

        # Must have a reliable timestamp
        reliable_ts = first_rec.get("created_at") or first_rec.get("assessment_timestamp")
        if not reliable_ts:
            return None

        baseline_result = dict(first_rec)

        # Check if first_rec has a valid positive CMP
        cmp_val = first_rec.get("cmp")
        has_valid_positive_cmp = isinstance(cmp_val, (int, float)) and cmp_val > 0

        # If first record's CMP is missing/non-positive, search subsequent records for earliest valid positive CMP
        if not has_valid_positive_cmp and len(records) > 1:
            for candidate in records[1:]:
                if isinstance(candidate, dict):
                    cand_cmp = candidate.get("cmp")
                    if isinstance(cand_cmp, (int, float)) and cand_cmp > 0:
                        baseline_result["cmp"] = cand_cmp
                        baseline_result["cmp_source_timestamp"] = (
                            candidate.get("created_at") or candidate.get("assessment_timestamp")
                        )
                        break

        return baseline_result

    # ==========================================================================
    # APPEND-ONLY PERSISTENCE
    # ==========================================================================

    def save_research_snapshot(self, research_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Append canonical ResearchResult snapshot to research_snapshots.
        Idempotent: returns existing ID if (symbol, research_id) is already saved.
        """
        if not self.is_configured:
            return {
                "saved": False,
                "id": None,
                "error": "NOT_CONFIGURED",
                "warning": "Supabase persistence skipped: missing SUPABASE_URL or SUPABASE_KEY.",
            }

        symbol = str(research_result.get("symbol", "")).upper()
        research_id = str(research_result.get("research_id", ""))

        # 1. Idempotency check: see if record already exists
        check_endpoint = f"{self.url}/rest/v1/research_snapshots"
        check_params = {
            "symbol": f"eq.{symbol}",
            "research_id": f"eq.{research_id}",
            "limit": "1",
        }
        try:
            check_resp = requests.get(
                check_endpoint,
                headers=self._headers(),
                params=check_params,
                timeout=self.timeout,
            )
            if check_resp.status_code == 200:
                existing = check_resp.json()
                if isinstance(existing, list) and existing:
                    return {
                        "saved": True,
                        "id": existing[0].get("id"),
                        "is_duplicate": True,
                    }
        except Exception:
            pass  # Fall through to insert attempt

        # 2. Insert new record
        market_as_of = (
            research_result.get("technicals", {}).get("provenance", {}).get("as_of_date")
            or research_result.get("fundamentals", {}).get("provenance", {}).get("as_of_date")
        )

        payload = {
            "research_id": research_id,
            "symbol": symbol,
            "exchange": research_result.get("exchange", "NSE"),
            "company_name": research_result.get("company_name", symbol),
            "research_timestamp": research_result.get("completed_at") or datetime.now(timezone.utc).isoformat(),
            "market_data_as_of": market_as_of,
            "overall_status": research_result.get("overall_status", "UNKNOWN"),
            "schema_version": research_result.get("schema_version", "1.0"),
            "data_quality_summary": research_result.get("data_quality_summary", {}),
            "research_data": research_result,
            "provenance": {
                "sources": research_result.get("sources", []),
                "errors": research_result.get("errors", []),
            },
        }

        try:
            resp = requests.post(
                check_endpoint,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code in {200, 201}:
                records = resp.json()
                record_id = records[0].get("id") if isinstance(records, list) and records else None
                return {
                    "saved": True,
                    "id": record_id,
                    "is_duplicate": False,
                }
            return {
                "saved": False,
                "id": None,
                "error": f"HTTP {resp.status_code}: {resp.text}",
                "warning": "Assessment generated successfully but snapshot persistence failed.",
            }
        except Exception as exc:
            return {
                "saved": False,
                "id": None,
                "error": str(exc),
                "warning": "Assessment generated successfully but snapshot persistence failed due to network error.",
            }

    def save_recommendation(
        self,
        recommendation: Dict[str, Any],
        research_snapshot_id: str,
    ) -> Dict[str, Any]:
        """
        Append investment recommendation record linked to research snapshot.
        Idempotent: returns existing ID if (research_run_id, engine_version) already exists.
        """
        if not self.is_configured:
            return {
                "saved": False,
                "id": None,
                "error": "NOT_CONFIGURED",
                "warning": "Supabase persistence skipped: missing SUPABASE_URL or SUPABASE_KEY.",
            }

        endpoint = f"{self.url}/rest/v1/investment_recommendations"
        engine_ver = recommendation.get("engine_version", ENGINE_VERSION)

        # 1. Idempotency check
        check_params = {
            "research_run_id": f"eq.{research_snapshot_id}",
            "engine_version": f"eq.{engine_ver}",
            "limit": "1",
        }
        try:
            check_resp = requests.get(
                endpoint,
                headers=self._headers(),
                params=check_params,
                timeout=self.timeout,
            )
            if check_resp.status_code == 200:
                existing = check_resp.json()
                if isinstance(existing, list) and existing:
                    return {
                        "saved": True,
                        "id": existing[0].get("id"),
                        "is_duplicate": True,
                    }
        except Exception:
            pass

        # 2. Insert record
        payload = {
            "research_run_id": research_snapshot_id,
            "symbol": recommendation.get("symbol"),
            "assessment_timestamp": recommendation.get("assessment_timestamp") or datetime.now(timezone.utc).isoformat(),
            "market_data_as_of": recommendation.get("market_data_as_of"),
            "cmp": recommendation.get("cmp"),
            "currency": recommendation.get("currency", "INR"),
            "technical_classification": recommendation.get("technical_classification"),
            "technical_score": recommendation.get("technical_score"),
            "technical_confidence": recommendation.get("technical_confidence"),
            "investment_action": recommendation.get("investment_action"),
            "investment_score": recommendation.get("investment_score"),
            "investment_confidence": recommendation.get("investment_confidence"),
            "reason_codes": recommendation.get("reason_codes", []),
            "positive_factors": recommendation.get("positive_factors", []),
            "cautionary_factors": recommendation.get("cautionary_factors", []),
            "risk_flags": recommendation.get("risk_flags", []),
            "key_levels": recommendation.get("key_levels", {}),
            "limitations": recommendation.get("limitations", []),
            "engine_version": engine_ver,
            "is_cached": bool(recommendation.get("is_cached", False)),
            "cache_metadata": recommendation.get("cache_metadata", {}),
            "summary_explanation": recommendation.get("summary_explanation"),
        }

        try:
            resp = requests.post(
                endpoint,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code in {200, 201}:
                records = resp.json()
                rec_id = records[0].get("id") if isinstance(records, list) and records else None
                return {
                    "saved": True,
                    "id": rec_id,
                    "is_duplicate": False,
                }
            return {
                "saved": False,
                "id": None,
                "error": f"HTTP {resp.status_code}: {resp.text}",
                "warning": "Assessment generated successfully but recommendation persistence failed.",
            }
        except Exception as exc:
            return {
                "saved": False,
                "id": None,
                "error": str(exc),
                "warning": "Assessment generated successfully but recommendation persistence failed due to network error.",
            }
