# PROGRESS.md — Stock Researcher Agent
*Last Updated: 2026-10-16*
*Last Session: 2026-10-16 (Render Live Security Deployment & TCS Phase B Multi-Day Track Record Verification)*

## 1. Purpose
Deterministic stock research and rule-based investment assessment engine for Indian listed equities (NSE/BSE). Collects verifiable factual data, computes indicators, derives audit-grade classifications, tracks performance against research baselines, and serves them via REST API and CLI.

## 2. Architecture Snapshot
- **Adapters (Local/Render):** Deterministic scraping of Yahoo Finance (`yfinance`), Screener.in (`requests`+`BeautifulSoup`), and Google News RSS (`news.py`).
- **Pipeline & Schemas (Local/Render):** `services/research_pipeline.py` synthesizes adapter payloads into canonical `ResearchResult v1` validated against JSON Schema.
- **REST API (Render Cloud):** FastAPI service (`interfaces/api.py`) hosting `GET /health` (public) and protected `POST /research` & `GET /research/{symbol}` with `X-API-Key` auth, rate limiting, and concurrency guards. Live on commit `65db6a2`.
- **Audit Persistence & Track Record (Supabase Cloud):** Append-only tables `research_snapshots` and `investment_recommendations` guarded by RLS and PostgreSQL immutability triggers. Earliest record acts as immutable baseline; subsequent runs track price return and verdict evolution.
- **Front-End & Skill (Oracle VM / OpenClaw):** OpenClaw agent invokes `skills/stock-research/run.py` to orchestrate research, 6-hr caching, baseline comparisons, rule evaluation, and Markdown chat outputs.

## 3. Status

### Implemented & Unit-Tested Locally
- Complete API security suite (`interfaces/api.py`): Fail-closed `X-API-Key` auth, public `/health`, rate limiting, and concurrency guards.
- Personal Watchlist & Track Record engine (`intelligence/track_record.py`, `services/supabase_repo.py`, `skills/stock-research/run.py`).
- Supabase resilience: `DEFAULT_TIMEOUT_SECONDS` increased from 10 to 30; baseline lookup raises `SupabaseRepositoryError` on network/HTTP errors to prevent treating network dropouts as missing baselines.
- Unit test suite: **204 tests passing locally** with `git diff --check` clean.

### Deployed & Live-Verified
- **Render Live Security Deployment:** Deployed commit `65db6a2` on Render. Verified:
  - `GET /health` returns HTTP 200 without credentials.
  - `GET /research/TCS` returns HTTP 401 Unauthorized without API key and with invalid key.
  - `GET /docs` returns HTTP 404 in production mode.
  - Authenticated request via `ResearchClient` returns HTTP 200 (`_research_source: RENDER_LIVE_API`).
- **Live Supabase Baseline Immutability:** Verified baseline for `TCS` established on Oct 15 remains 100% untouched:
  - Baseline Snapshot ID: `60e704e0-3c45-4e12-8ced-2214f159ad5b`
  - Baseline Recommendation ID: `5b1478e1-ac04-4b9c-bc40-8ca1ebea7aac` (₹2,350.00, `HOLD_REVIEW`).
- **Live 6-Hour Cache & Duplicate Prevention:** Confirmed repeated request within cache window creates 0 new rows.
- **Live Multi-Day Track Record Verification (Phase B Complete):**
  - October 16 fresh run (after 22h cache expiry): Snapshot `0956e0ef-2f29-4c2b-a122-0dfc8f7b96cf` and Recommendation `e0c33d54-df96-4fe3-8902-72bc801953d4` (₹2,465.00, `AVOID_NEW_ENTRY`).
  - Verified Price Return: **+₹115.00 (+4.89%)** over ~1 day, excluding dividends, fees, and taxes.
  - Verified Foreign Key Link: Recommendation correctly linked to snapshot `0956e0ef...`.
  - Verified Supabase Row Counts: Exactly **2 rows in `research_snapshots`** and **2 rows in `investment_recommendations`**.

### Remaining Work
1. **Move Supabase Writes Behind Render API:** Currently, the client runner writes to Supabase using `SUPABASE_SERVICE_ROLE_KEY`. Move persistence inside Render API so service keys stay strictly on the server.
2. **OpenClaw Skill Integration:** Mount `skills/stock-research/` into OpenClaw workspace on the Oracle VM.
3. **Partial Failure Resilience:** Pipeline crashes if Screener or Yahoo Finance fails rather than returning partial verified data.
4. **Automated Daily Sweeps:** Set up recurring cron/heartbeat routines for equity watchlists.
5. **Kite Connect Adapter:** Implement Zerodha Kite Connect as primary market data feed.

## 4. Decisions
- **2026-10-10:** Adopted FastAPI with threadpool worker offloading (`interfaces/api.py`) to prevent scraping from blocking event loops.
- **2026-10-11:** Deployed REST API as a web service on Render Singapore region to provide a stable public endpoint for OpenClaw.
- **2026-10-12:** Established append-only immutability in Supabase via PostgreSQL triggers (`BEFORE UPDATE OR DELETE RAISE EXCEPTION`) to preserve audit history.
- **2026-10-14:** Implemented zero-dependency API security (`interfaces/api.py`) using native FastAPI `X-API-Key` auth, fail-closed generic 500 error, bounded in-memory rate limiting, and leak-safe concurrency control.
- **2026-10-15:** Implemented Watchlist & Track Record feature using existing immutable Supabase tables. Designed baseline query to run before new record persistence to prevent self-comparison.
- **2026-10-16:** Published 5 commits (`8b4d0d4`..`65db6a2`) to GitHub `main` and verified live Render security deployment.
- **2026-10-16:** Completed Phase B live verification across distinct dates for TCS. Increased Supabase timeout to 30.0s and updated `get_baseline_assessment` to raise `SupabaseRepositoryError` on network failures, preventing transient network dropouts from falsely establishing new baselines. Reconstructed and persisted recommendation `e0c33d54...` linked to snapshot `0956e0ef...` without duplicate snapshots.

## 5. Risks and Open Issues
- **Client-Side Supabase Keys:** Client runner requires `SUPABASE_SERVICE_ROLE_KEY` until persistence is moved behind the authenticated Render API.
- **Single-Source Failure Crash:** If Screener.in or Yahoo Finance blocks requests, the pipeline raises an unhandled exception instead of outputting partial evidence.

## 6. Next Steps
1. **Move Supabase persistence behind Render API** — Proxy persistence through Render so client runners only need `RESEARCH_API_KEY`.
2. **Connect OpenClaw** — Mount `skills/stock-research/` into OpenClaw workspace on the Oracle VM.
3. **Implement partial reports when a source fails** — Allow pipeline to return partial results marked `UNAVAILABLE` if an individual adapter fails.
4. **Add a daily schedule** — Set up automated cron/heartbeat routines for equity watchlists.

## 7. How to Run and Test
```bash
# 1. Run full test suite (offline / mocked)
.venv-market/bin/python -m unittest discover tests

# 2. Run local research in DEV mode (bypasses Supabase & Render)
.venv-market/bin/python -m skills.stock-research.run TCS --env dev

# 3. Run production research via deployed Render API and Supabase
.venv-market/bin/python -m skills.stock-research.run TCS --env prod

# 4. Check live Render health endpoint (public GET)
curl -s https://stock-researcher-agent.onrender.com/health

# 5. Check git working tree for formatting issues
git diff --check
```
