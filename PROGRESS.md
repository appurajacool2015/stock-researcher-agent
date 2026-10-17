# PROGRESS.md — Stock Researcher Agent
*Last Updated: 2026-10-17*
*Last Session: 2026-10-17 (Phase 1 Render Persistence, Buying Zone Assessment & Key Metrics Table)*

## 1. Purpose
Deterministic stock research and rule-based investment assessment engine for Indian listed equities (NSE/BSE). Collects verifiable factual data, computes indicators, derives audit-grade classifications, tracks performance against research baselines, and evaluates entry buying zones.

## 2. Architecture Snapshot
- **Adapters (Local/Render):** Deterministic scraping of Yahoo Finance (`yfinance`), Screener.in (`requests`+`BeautifulSoup`), and Google News RSS (`news.py`).
- **Pipeline & Schemas (Local/Render):** `services/research_pipeline.py` synthesizes adapter payloads into canonical `ResearchResult v1` validated against JSON Schema.
- **REST API & Persistence (Render Cloud):** FastAPI service (`interfaces/api.py`) hosting `GET /health` (public) and protected `POST /research` & `GET /research/{symbol}` with `X-API-Key` auth, rate limiting, 6-hr caching, and append-only Supabase persistence directly from the cloud.
- **Track Record & Buying Zone (Supabase & Intelligence):** Multi-day baseline tracking against immutable records (`intelligence/track_record.py`) and entry risk-to-reward evaluation (`intelligence/buying_zone.py`).
- **Front-End & Skill (Oracle VM / OpenClaw):** OpenClaw agent invokes `skills/stock-research/run.py` to query Render API using only `RESEARCH_API_KEY` (zero database keys on client).

## 3. Status

### Implemented & Unit-Tested Locally
- **Server-Side Persistence (Phase 1):** Moved 6-hour cache checks and Supabase writes into Render API (`interfaces/api.py`). Client runner requires zero database keys.
- **Buying Zone Assessment (Phase 1):** Deterministic 5-label entry evaluator (`intelligence/buying_zone.py`) computing invalidation levels, targets, and reward-to-risk ratios.
- **Key Metrics & Fundamentals Enhancement:** Added Balance Sheet fallback in `adapters/screener.py` for Debt-to-Equity (borrowings/equity calculation and 0.00x zero-debt resolution) and deterministic PEG calculation in `intelligence/investment_assessment.py`.
- **Unit Test Suite:** **237 tests passing locally** with `git diff --check` clean.

### Deployed & Live-Verified
- **Render Live Security & Persistence Deployment:** Deployed commit `5f0c886` on Render. Verified:
  - `GET /health` returns HTTP 200 without credentials.
  - Render environment configured with `RESEARCH_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_URL`.
  - Client runner (`skills/stock-research/run.py`) functions with only `RESEARCH_API_KEY`.
- **Live Supabase Multi-Day Track Record:** Verified baseline for `TCS` established Oct 15 (₹2,350.00) vs Oct 16 run (₹2,465.00, +4.89% price return) across 2 rows in each table.

### Remaining Work
1. **OpenClaw Skill Integration:** Mount `skills/stock-research/` into OpenClaw workspace on the Oracle VM.
2. **Partial Failure Resilience:** Allow pipeline to return partial verified data when Screener or Yahoo Finance fails.
3. **Automated Daily Sweeps:** Set up recurring cron/heartbeat routines for equity watchlists.
4. **Kite Connect Adapter:** Implement Zerodha Kite Connect as an optional primary market data feed.

## 4. Decisions
- **2026-10-10:** Adopted FastAPI with threadpool worker offloading (`interfaces/api.py`) to prevent scraping from blocking event loops.
- **2026-10-12:** Established append-only immutability in Supabase via PostgreSQL triggers (`BEFORE UPDATE OR DELETE RAISE EXCEPTION`).
- **2026-10-14:** Implemented zero-dependency API security (`interfaces/api.py`) using native FastAPI `X-API-Key` auth.
- **2026-10-15:** Implemented Watchlist & Track Record engine using existing immutable Supabase tables.
- **2026-10-16:** Completed Phase B multi-day live verification (+4.89% return for TCS).
- **2026-10-17:** Completed Phase 1 by moving Supabase persistence and caching behind Render API (`85cac7c`). Client runners now require zero database credentials.
- **2026-10-17:** Implemented deterministic Buying Zone Assessment (`intelligence/buying_zone.py`) with 5 mutually exclusive labels and risk-to-reward calculation (`5f0c886`).
- **2026-10-17:** Implemented 16-row 4-column Key Metrics presentation table with volume metrics and status preservation (`eda17f5`).
- **2026-10-17:** Documented Buying Zone, 16-row Key Metrics, decoupled Oracle VM architecture, and Supabase RLS resolution in README.md and Master Manual v3.0 (`36bfa7e`).
- **2026-10-17:** Implemented Balance Sheet fallback for Debt-to-Equity (0.10x for TCS) and deterministic PEG ratio (2.04 for TCS) in Key Metrics table; added dedicated `test_screener.py` (237 tests).

## 5. Risks and Open Issues
- **Single-Source Failure Crash:** If Screener.in or Yahoo Finance blocks requests, the pipeline raises an unhandled exception instead of outputting partial evidence.
- **Upcoming Earnings Calendar:** Public feeds currently lack forward quarterly results calendar; event risk remains unmodeled.

## 6. Next Steps
1. **Connect OpenClaw on Oracle VM** — Mount `skills/stock-research/` into OpenClaw workspace; configure `RESEARCH_API_KEY`.
2. **Implement partial failure resilience** — Return partial results marked `UNAVAILABLE` if an individual adapter fails.
3. **Add automated daily monitoring** — Recurring watchlist sweeps and Telegram alerts for verdict changes.

## 7. How to Run and Test
```bash
# 1. Run full test suite (offline / mocked)
.venv-market/bin/python -m unittest discover tests

# 2. Run local research in DEV mode (bypasses Supabase & Render)
.venv-market/bin/python -m skills.stock-research.run TCS --env dev

# 3. Run production research via deployed Render API (requires RESEARCH_API_KEY only)
.venv-market/bin/python -m skills.stock-research.run TCS --env prod

# 4. Check live Render health endpoint (public GET)
curl -s https://stock-researcher-agent.onrender.com/health

# 5. Check git working tree for formatting issues
git diff --check
```
