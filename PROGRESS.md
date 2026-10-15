# PROGRESS.md — Stock Researcher Agent
*Last Updated: 2026-10-15*
*Last Session: 2026-10-15 (Watchlist & Track Record Phases 2A–2E & Live Supabase Verification)*

## 1. Purpose
Deterministic stock research and rule-based investment assessment engine for Indian listed equities (NSE/BSE). Collects verifiable factual data, computes indicators, derives audit-grade classifications, tracks performance against research baselines, and serves them via REST API and CLI.

## 2. Architecture Snapshot
- **Adapters (Local/Render):** Deterministic scraping of Yahoo Finance (`yfinance`), Screener.in (`requests`+`BeautifulSoup`), and Google News RSS (`news.py`).
- **Pipeline & Schemas (Local/Render):** `services/research_pipeline.py` synthesizes adapter payloads into canonical `ResearchResult v1` validated against JSON Schema.
- **REST API (Render Cloud):** FastAPI service (`interfaces/api.py`) hosting `GET /health` (public) and protected `POST /research` & `GET /research/{symbol}` with `X-API-Key` auth, rate limiting, and concurrency guards.
- **Audit Persistence & Track Record (Supabase Cloud):** Append-only tables `research_snapshots` and `investment_recommendations` guarded by RLS and PostgreSQL immutability triggers. Earliest record acts as immutable baseline; subsequent runs track price return and verdict evolution.
- **Front-End & Skill (Oracle VM / OpenClaw):** OpenClaw agent invokes `skills/stock-research/run.py` to orchestrate research, 6-hr caching, baseline comparisons, rule evaluation, and Markdown chat outputs.

## 3. Status

### Implemented & Unit-Tested Locally
- Personal Watchlist & Track Record engine (Phases 2A–2E completed):
  - Pure track-record calculator (`intelligence/track_record.py`): price delta, percentage return, elapsed time, verdict shift, and guardrail notes.
  - Baseline query (`services/supabase_repo.py`: `get_baseline_assessment`): queries earliest positive CMP with fail-safe error handling.
  - Explainer Section 8 integration (`intelligence/explainer.py`): formats research baseline and performance metrics cleanly.
  - Research runner orchestration (`skills/stock-research/run.py`): queries baseline before persistence (preventing self-comparison), preserves history, attaches track record, prevents duplicate inserts on 6-hr cache hits, and handles DB failures gracefully.
- Core deterministic adapters (`market_data.py`, `screener.py`, `news.py`) and schema validation pipeline (`research_pipeline.py`).
- Higher-level deterministic assessment engine (`investment_assessment.py`).
- Complete API security suite (`interfaces/api.py`): Fail-closed `X-API-Key` auth, public `/health`, rate limiting, and concurrency guards.
- Complete unit test suite: **202 tests passing locally** across all modules (`tests/`).

### Deployed & Live-Verified
- **Live Supabase Read Access:** Verified HTTP 200 OK for `research_snapshots` and `investment_recommendations`.
- **Live Supabase Baseline Write & Read-Back:** Initial baseline research for `TCS` successfully written to `research_snapshots` (`60e704e0-3c45-4e12-8ced-2214f159ad5b`) and `investment_recommendations` (`5b1478e1-ac04-4b9c-bc40-8ca1ebea7aac`) with verified foreign key linking (`research_run_id`).
- **Live 6-Hour Cache & Duplicate Prevention:** Repeated `TCS` request served from cache (`is_cached: true`), preserving the original baseline with **0 new snapshots and 0 new recommendations** created in Supabase.
- **FastAPI REST Service:** Deployed on Render; `/health` check independently verified returning HTTP 200 OK.
- **PostgreSQL Schema:** Migration `001_initial_stock_research_schema.sql` applied and active in Supabase.

### Built but Untested / Unresolved (Remaining Work)
- **Fresh Research After Cache Expiry:** Live research run after the 6-hour TTL has expired has not yet been verified live.
- **Multi-Day Historical Price Return:** Price-return calculations across two genuinely distinct live calendar dates have been tested locally via mocks (12 tests passing), but not yet verified live in Supabase.
- **Live Render API Security (UNRESOLVED):** Security implementation is tested locally, but not yet deployed to Render or verified with live `RESEARCH_API_KEY`.
- **Live Gemini Explainer:** AI explainer fallback is verified with unit mocks, but live outbound calls depend on active API keys at runtime.

### Not Built
- **Zerodha Kite Connect Adapter:** Mentioned in `TOOLS.md` as preferred primary market source, but no adapter implementation exists yet.
- **Partial Failure Resilience:** Pipeline crashes if Screener or Yahoo Finance fails rather than returning partial verified data.
- **Automated Scheduled Watchlist Sweeps:** No recurring cron/heartbeat jobs scheduled yet.
- **Downstream Consumer Agents:** Stock Analyst, WhatsApp Formatter, and WhatsApp Publisher.

## 4. Decisions
- **2026-10-10:** Adopted FastAPI with threadpool worker offloading (`interfaces/api.py`) to prevent scraping from blocking event loops.
- **2026-10-11:** Deployed REST API as a web service on Render Singapore region to provide a stable public endpoint for OpenClaw.
- **2026-10-12:** Established append-only immutability in Supabase via PostgreSQL triggers (`BEFORE UPDATE OR DELETE RAISE EXCEPTION`) to preserve audit history.
- **2026-10-13:** Forwarded sanitized repository errors into `persistence_status` without leaking credentials or full payloads.
- **2026-10-14:** Implemented `--env {dev,prod}` toggle with strict precedence: CLI option → `STOCK_RESEARCH_ENV` → `prod`.
- **2026-10-14:** Confirmed Requesty is OpenClaw's own LLM router on Oracle VM and is completely unused in this repository.
- **2026-10-14:** Mandated that web scraping is preferred and free, while AI formatting must remain OFF by default.
- **2026-10-14:** Implemented zero-dependency API security (`interfaces/api.py`) using native FastAPI `X-API-Key` auth, fail-closed generic 500 error, bounded in-memory rate limiting, and leak-safe concurrency control.
- **2026-10-14:** Added client-side missing-credential validation in `services/research_client.py` to fail locally before sending unauthenticated network requests.
- **2026-10-15:** Authored `Master_Manual_v3.0.md` in Markdown to provide a version-controlled technical reference superseding static PDFs.
- **2026-10-15:** Enforced strict `.env` isolation in global rules and project brief, forbidding inspection or editing unless explicitly requested.
- **2026-10-15:** Implemented Watchlist & Track Record feature (Option 1) using existing immutable Supabase tables (`research_snapshots` and `investment_recommendations`) without schema changes. Designed baseline query to run before new record persistence to prevent self-comparison, and guarded cache hits to prevent duplicate database inserts.
- **2026-10-15:** Resolved Supabase write permission by configuring the legacy JWT `service_role` key in `SUPABASE_SERVICE_ROLE_KEY`. Confirmed that PostgREST direct HTTP headers expect a JWT to bypass RLS, whereas publishable keys (`sb_pub...`) are rejected with code `42501`.

## 5. Risks and Open Issues
- **Pending Render Deployment of API Security:** Local API code is secured, but the live Render deployment remains open until deployed with `RESEARCH_API_KEY` configured in Render environment variables.
- **Single-Source Failure Crash:** If Screener.in or Yahoo Finance blocks requests or errors out, the entire research run raises an unhandled exception instead of outputting partial evidence.

## 6. Next Steps
1. **Verify Fresh Research After Cache Expiry** — Run research for `TCS` after the 6-hour cache window expires to verify append-only snapshot creation and return calculation against the existing baseline.
2. **Configure Render environment & deploy API security** — Set `RESEARCH_API_KEY` in Render Dashboard environment variables, push `main` branch to GitHub, and verify live endpoints return 401 (unauthorized) and 200 (with key).
3. **Decide where Supabase writes happen** — Evaluate moving writes inside Render API so `SUPABASE_SERVICE_ROLE_KEY` stays strictly in Render environment variables.
4. **Connect OpenClaw** — Mount `skills/stock-research/` into OpenClaw workspace on the Oracle VM.
5. **Implement partial reports when a source fails** — Allow pipeline to return partial results marked `UNAVAILABLE` if an individual adapter fails.
6. **Add a daily schedule** — Set up automated cron/heartbeat routines for equity watchlists.
7. **Add the Kite adapter** — Implement Zerodha Kite Connect as the primary market data feed.

## 7. How to Run and Test
```bash
# 1. Run full test suite (offline / mocked)
.venv-market/bin/python -m unittest discover tests

# 2. Run local research in DEV mode (scrapes directly, bypasses Supabase & Render)
.venv-market/bin/python -m skills.stock-research.run TCS --env dev

# 3. Run research via deployed Render API (requires deployed service access & RESEARCH_API_KEY)
.venv-market/bin/python -m skills.stock-research.run TCS --env prod

# 4. Check live Render health endpoint (safe read-only GET)
curl -s https://stock-researcher-agent.onrender.com/health

# 5. Check git working tree for formatting issues
git diff --check
```
