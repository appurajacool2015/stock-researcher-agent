# Stock Research Skill (Phase 4 Integrated)

## Purpose

This skill defines how OpenClaw executes stock research by integrating:
1. The **Render Research REST API** (`https://stock-researcher-agent.onrender.com/research/{symbol}`).
2. The **Deterministic Investment Assessment Engine** (`intelligence/investment_assessment.py`).
3. The **Supabase Append-Only Audit & Cache Repository** (`services/supabase_repo.py`).
4. The **Deterministic 8-Section Explainer** (`intelligence/explainer.py`).

The Stock Researcher Agent is an **execution and orchestration agent**, not an independent stock fact generator.

---

# 1. Canonical Execution Path

The execution entry point is:

```bash
.venv-market/bin/python -m skills.stock-research.run SYMBOL
```

Options:
- `--force-refresh`: Bypass the 6-hour Supabase cache to fetch fresh data from Render.
- `--allow-local-fallback`: Allow local pipeline execution if the Render API is unreachable.
- `--json`: Output full structured JSON payload (recommendation + snapshot + audit IDs).

Example:
```bash
.venv-market/bin/python -m skills.stock-research.run TCS
```

---

# 2. Workflow & Cache Rules

1. **Symbol Normalization:** Convert input to valid uppercase alphanumeric ticker (e.g. `TCS`, `INFY`).
2. **6-Hour Cache Lookup:**
   - Queries `investment_recommendations` and `research_snapshots` in Supabase.
   - Verifies `schema_version == "1.0"` and `engine_version == "1.0.0"`.
   - If found and not expired, returns cached result with `is_cached = True`.
3. **Fresh Fetch via Render REST API:**
   - On cache miss or `--force-refresh`, requests `GET https://stock-researcher-agent.onrender.com/research/{symbol}`.
   - Bounded 75-second timeout absorbs Render free-tier cold starts.
   - Retries transient 502/503 errors up to 2 times.
   - Strict validation of JSON structure and schema.
4. **Deterministic Investment Assessment:**
   - Derives one of 5 mutually exclusive actions:
     `INSUFFICIENT_DATA`, `REDUCE_SELL_REVIEW`, `AVOID_NEW_ENTRY`, `BUY_CANDIDATE`, `HOLD_REVIEW`.
   - Strictly enforces fundamental and valuation requirements for `BUY_CANDIDATE`.
   - Applies the Debt-to-Equity applicability guard for Banks/NBFCs and debt-free companies.
5. **Append-Only Supabase Audit Persistence:**
   - Persists raw snapshot into `research_snapshots`.
   - Persists recommendation verdict into `investment_recommendations`.
   - Foreign key uses `ON DELETE RESTRICT` (NO CASCADE) to protect historical audit trail.
   - Idempotent unique indexes prevent duplicate records during retries.
6. **Chat Response Generation:**
   - Formats concise output strictly conforming to the 8 required sections.

---

# 3. Decision Boundary & Non-Negotiable Rules

1. **No Invented Facts:** Never invent PE, PB, ROCE, ROE, CMP, DMA, volume, or shareholding.
2. **No Classification Overrides:** Never alter or override the deterministic `technical_classification` or higher-level `investment_action`.
3. **Missing/Stale Evidence:** Unavailable, stale, or conflicting metrics must be represented as `UNAVAILABLE` or listed as limitations. They must never be treated as positive evidence or converted to zero.
4. **No Financial Guarantees:** Do not claim a recommendation guarantees profit or eliminates capital-loss risk. Always include the standard disclaimer.
