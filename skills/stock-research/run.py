#!/usr/bin/env python3
"""
OpenClaw Stock Research Skill Execution Runner

Purpose
-------
Integrates the complete Phase 4 stock research workflow for OpenClaw agents:
1. Symbol validation and normalization.
2. 6-hour Supabase cache check with engine compatibility checks.
3. Force-refresh bypass capability.
4. Render REST API research client query (with bounded timeouts and schema validation).
5. Higher-level deterministic investment assessment derivation.
6. Append-only Supabase persistence for audit snapshots and recommendations.
7. Concise 8-section Markdown chat response output.

Usage:
    python -m skills.stock-research.run SYMBOL [--force-refresh] [--allow-local-fallback] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from intelligence.explainer import explain_assessment
from intelligence.investment_assessment import evaluate_investment_assessment
from intelligence.track_record import calculate_track_record
from interfaces.research_cli import normalize_symbol
from services.research_client import ResearchClient
from services.research_pipeline import run_pipeline

VALID_ENVIRONMENTS = {"dev", "prod"}
DEFAULT_ENVIRONMENT = "prod"


def resolve_execution_env(cli_env: Optional[str] = None) -> str:
    """
    Resolve execution environment with strict precedence:
    1. Explicit CLI argument (--env)
    2. Environment variable (STOCK_RESEARCH_ENV)
    3. Default ('prod')

    Rejects invalid values case-insensitively with a clean ValueError.
    """
    if cli_env is not None:
        raw_val = str(cli_env).strip()
        norm_val = raw_val.lower()
        if norm_val in VALID_ENVIRONMENTS:
            return norm_val
        raise ValueError(f"Invalid environment '{cli_env}'. Must be 'dev' or 'prod'.")

    env_var = os.environ.get("STOCK_RESEARCH_ENV")
    if env_var is not None:
        raw_val = env_var.strip()
        norm_val = raw_val.lower()
        if norm_val in VALID_ENVIRONMENTS:
            return norm_val
        raise ValueError(
            f"Invalid environment '{env_var}' in STOCK_RESEARCH_ENV. Must be 'dev' or 'prod'."
        )

    return DEFAULT_ENVIRONMENT


def _execute_local_pipeline(symbol: str) -> Dict[str, Any]:
    """Execute local research pipeline in DEV mode."""
    return run_pipeline(symbol=symbol)


def execute_stock_research(
    raw_symbol: str,
    force_refresh: bool = False,
    allow_local_fallback: bool = False,
    use_gemini: bool = True,
    env: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute full Phase 4 stock research and investment assessment workflow.

    Parameters
    ----------
    raw_symbol : str
        Stock ticker symbol.
    force_refresh : bool
        If True, bypasses 6-hour Supabase cache.
    allow_local_fallback : bool
        Whether to allow local fallback if Render API fails (strictly False in PROD mode).
    use_gemini : bool
        Whether to format chat response using Gemini.
    env : Optional[str]
        Execution environment ('dev' or 'prod'). Precedence: CLI/param -> STOCK_RESEARCH_ENV -> prod.

    Returns
    -------
    Dictionary containing recommendation, snapshot, markdown response, and persistence status.
    """
    # Preserve backward compatibility if a string was passed as force_refresh positionally
    if isinstance(force_refresh, str) and env is None:
        env = force_refresh
        force_refresh = False

    symbol = normalize_symbol(raw_symbol)
    resolved_env = resolve_execution_env(env)

    # ----------------------------------------------------
    # DEV Mode: Local pipeline execution, bypass Supabase
    # ----------------------------------------------------
    if resolved_env == "dev":
        research_result = _execute_local_pipeline(symbol)
        recommendation = evaluate_investment_assessment(research_result)
        persistence_status = {
            "saved": False,
            "warning": "Supabase persistence skipped in DEV mode",
        }
        track_record = {
            "status": "UNAVAILABLE",
            "note": "Track record disabled in local DEV mode (Supabase bypassed).",
        }
        recommendation["track_record"] = track_record
        explanation = explain_assessment(recommendation, track_record=track_record, use_gemini=use_gemini)
        if persistence_status.get("warning"):
            explanation += f"\n\n> ⚠️ *Audit Persistence Notice: {persistence_status['warning']}*"

        return {
            "ok": True,
            "symbol": symbol,
            "is_cached": False,
            "execution_env": "dev",
            "data_source": "local_pipeline",
            "recommendation": recommendation,
            "snapshot": research_result,
            "track_record": track_record,
            "markdown_response": explanation,
            "persistence_status": persistence_status,
        }

    # ----------------------------------------------------
    # PROD Mode: Render REST API (server handles persistence)
    # ----------------------------------------------------
    client = ResearchClient()

    # 1. Fresh Fetch via Render API
    #    The Render server handles: cache check, baseline lookup, Supabase writes.
    #    The response includes a `_persistence` block with snapshot_id,
    #    recommendation_id, track_record, and is_cached.
    fetch_kwargs = {
        "raw_symbol": symbol,
        "allow_local_fallback": False,
    }
    if force_refresh:
        fetch_kwargs["force_refresh"] = True

    research_result = client.fetch_research(**fetch_kwargs)

    # 2. Read persistence metadata from server response
    persistence_block = research_result.pop("_persistence", {})
    is_cached = persistence_block.get("is_cached", False)
    track_record = persistence_block.get("track_record") or {
        "status": "UNAVAILABLE",
        "note": "Track record not returned by server.",
    }

    # 3. Deterministic Investment Assessment (always re-derived locally for chat output)
    recommendation = evaluate_investment_assessment(research_result)
    recommendation["track_record"] = track_record

    # Restore IDs from server persistence block if available
    if persistence_block.get("recommendation_id"):
        recommendation["id"] = persistence_block["recommendation_id"]

    # 4. Persistence status for display
    persistence_status: Dict[str, Any] = {
        "saved": persistence_block.get("saved", False),
        "id": persistence_block.get("recommendation_id"),
        "snapshot_id": persistence_block.get("snapshot_id"),
        "is_cached": is_cached,
        "is_duplicate": persistence_block.get("is_duplicate", False),
        "warning": persistence_block.get("warning"),
    }

    # 5. Format Chat Response
    explanation = explain_assessment(recommendation, track_record=track_record, use_gemini=use_gemini)
    if persistence_status.get("warning"):
        explanation += f"\n\n> ⚠️ *Audit Persistence Notice: {persistence_status['warning']}*"

    return {
        "ok": True,
        "symbol": symbol,
        "is_cached": is_cached,
        "execution_env": "prod",
        "data_source": "render_api",
        "recommendation": recommendation,
        "snapshot": research_result,
        "track_record": track_record,
        "markdown_response": explanation,
        "persistence_status": persistence_status,
    }


def main(argv: Optional[List[str]] = None) -> int:
    """CLI interface for OpenClaw skill execution."""
    parser = argparse.ArgumentParser(
        description="Execute deterministic stock research and investment assessment."
    )
    parser.add_argument("symbol", help="Stock ticker symbol (e.g. TCS, INFY)")
    parser.add_argument(
        "--env",
        dest="env",
        default=None,
        metavar="{dev,prod}",
        help="Execution environment ('dev' or 'prod'). Precedence: CLI --env -> STOCK_RESEARCH_ENV -> prod.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Bypass the 6-hour cache and fetch fresh research from Render API.",
    )
    parser.add_argument(
        "--allow-local-fallback",
        action="store_true",
        help="Allow local execution fallback if Render API fails (disabled in PROD mode).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted markdown.",
    )
    parser.add_argument(
        "--no-gemini",
        action="store_true",
        help="Disable Gemini formatting and use deterministic template exclusively.",
    )

    args = parser.parse_args(argv)

    try:
        result = execute_stock_research(
            raw_symbol=args.symbol,
            force_refresh=args.force_refresh,
            allow_local_fallback=args.allow_local_fallback,
            use_gemini=not args.no_gemini,
            env=args.env,
        )

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(result["markdown_response"])

        return 0

    except Exception as exc:
        err_payload = {
            "ok": False,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
        if args.json:
            print(json.dumps(err_payload, indent=2, ensure_ascii=False))
        else:
            print(f"❌ Stock Research Execution Failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
