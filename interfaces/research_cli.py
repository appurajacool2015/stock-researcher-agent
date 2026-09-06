#!/usr/bin/env python3

"""
OpenClaw-facing interface for the stock research engine.

Purpose
-------
Provide a stable machine-readable interface between OpenClaw and the
existing stock-research pipeline.

Usage
-----
    python -m interfaces.research_cli TCS

or:

    python interfaces/research_cli.py TCS

The interface runs the existing research pipeline and returns the
canonical ResearchResult JSON to stdout.

Important
---------
This file intentionally contains no research logic.

The research engine remains responsible for:
    - Screener data
    - Market data
    - News
    - ResearchResult construction
    - Schema validation
    - Output persistence
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"


def normalize_symbol(value: str) -> str:
    """Normalize and validate a stock symbol."""
    symbol = value.strip().upper()

    if not symbol:
        raise ValueError("Stock symbol cannot be empty.")

    if not symbol.replace(".", "").replace("-", "").isalnum():
        raise ValueError(
            f"Invalid stock symbol: {value!r}. "
            "Only letters, numbers, dots and hyphens are allowed."
        )

    return symbol


def output_path(symbol: str) -> Path:
    """Return the canonical ResearchResult output path."""
    return OUTPUT_DIR / f"{symbol.lower()}-research-result.json"


def run_pipeline(symbol: str) -> None:
    """
    Run the existing research pipeline.

    The pipeline itself remains the source of truth for data collection,
    normalization, validation and persistence.
    """
    command = [
        sys.executable,
        "-m",
        "services.research_pipeline",
        symbol,
    ]

    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    if completed.returncode != 0:
        error_message = completed.stderr.strip() or completed.stdout.strip()

        raise RuntimeError(
            "Research pipeline failed"
            + (f": {error_message}" if error_message else ".")
        )


def load_result(symbol: str) -> dict:
    """Load the canonical ResearchResult produced by the pipeline."""
    path = output_path(symbol)

    if not path.exists():
        raise FileNotFoundError(
            f"ResearchResult was not created: {path}"
        )

    try:
        with path.open("r", encoding="utf-8") as handle:
            result = json.load(handle)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"ResearchResult is not valid JSON: {path}"
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError(
            "ResearchResult root must be a JSON object."
        )

    return result


def main() -> int:
    """CLI entry point."""
    if len(sys.argv) != 2:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "type": "usage_error",
                        "message": (
                            "Usage: python -m interfaces.research_cli SYMBOL"
                        ),
                    },
                },
                ensure_ascii=False,
            )
        )
        return 2

    try:
        symbol = normalize_symbol(sys.argv[1])

        run_pipeline(symbol)

        result = load_result(symbol)

        # Return the canonical research result unchanged.
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            )
        )

        return 0

    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
