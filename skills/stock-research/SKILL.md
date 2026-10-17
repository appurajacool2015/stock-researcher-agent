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
- `--env {dev,prod}`: Execution mode (default: `prod`).
  - `dev`: Scrapes directly via local Python pipeline; completely bypasses Render API and Supabase persistence.
  - `prod`: Queries Render REST API with 6-hr Supabase caching and audit persistence.
- `--force-refresh`: Bypass the 6-hour Supabase cache to fetch fresh data from Render.
- `--allow-local-fallback`: Allow local pipeline execution if the Render API is unreachable.
- `--json`: Output full structured JSON payload (recommendation + snapshot + audit IDs).

Example:
```bash
# Run in dev mode (direct local scraping, no Render/Supabase required)
.venv-market/bin/python -m skills.stock-research.run TCS --env dev

# Run in prod mode (queries Render API and Supabase cache)
.venv-market/bin/python -m skills.stock-research.run TCS --env prod
```

---

# 2. Workflow & Cache Rules

1. **Symbol Normalization:** Convert input to valid uppercase alphanumeric ticker (e.g. `TCS`, `INFY`).
2. **Environment & Security Architecture:**
   - In `dev` mode: Bypasses Render API and executes the local Python scraping pipeline directly.
   - In `prod` mode: Communicates with Render REST API (`https://stock-researcher-agent.onrender.com`).
   - The client runner requires **only `RESEARCH_API_KEY`**. No database credentials (`SUPABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY`) are stored or required on the client VM.
3. **Server-Side Cache & Persistence (Render Cloud):**
   - **Client Pre-Flight Check:** Verifies `RESEARCH_API_KEY` is present in environment; fails locally before sending unauthenticated network requests.
   - Requests `GET /research/{symbol}` with `X-API-Key` header. Bounded 75-second timeout absorbs cold starts; retries transient 502/503/504 errors up to 2 times.
   - Render server inspects 6-hour cache in Supabase. On cache miss or `--force-refresh`, executes research, fetches multi-day baseline history, and appends immutable records to Supabase.
   - Render returns the verified `ResearchResult v1` along with a `_persistence` metadata block containing snapshot ID, recommendation ID, track record, and cache status.
4. **Deterministic Investment Assessment & Buying Zone:**
   - Client runner re-evaluates assessment rules locally to generate one of 5 actions:
     `INSUFFICIENT_DATA`, `REDUCE_SELL_REVIEW`, `AVOID_NEW_ENTRY`, `BUY_CANDIDATE`, `HOLD_REVIEW`.
   - Evaluates deterministic entry Buying Zone:
     `BUYING_ZONE`, `WAIT_FOR_PULLBACK`, `WAIT_FOR_CONFIRMATION`, `NOT_IN_BUYING_ZONE`, `INSUFFICIENT_DATA`.
   - Calculates nearest support reference, invalidation stop level, upside target, and reward-to-risk ratio.
5. **Chat Response Generation:**
   - Formats the 16-metric 4-column Key Metrics table (`Metric`, `Value`, `Status`, `As-Of Date`).
   - Renders concise output strictly conforming to the 8 required sections with historical track record baseline and disclaimer.

---

# 3. Decision Boundary & Non-Negotiable Rules

1. **No Invented Facts:** Never invent PE, PB, ROCE, ROE, CMP, DMA, volume, or shareholding.
2. **No Classification Overrides:** Never alter or override the deterministic `technical_classification` or higher-level `investment_action`.
3. **Missing/Stale Evidence:** Unavailable, stale, or conflicting metrics must be represented as `UNAVAILABLE` or listed as limitations. They must never be treated as positive evidence or converted to zero.
4. **No Financial Guarantees:** Do not claim a recommendation guarantees profit or eliminates capital-loss risk. Always include the standard disclaimer.
