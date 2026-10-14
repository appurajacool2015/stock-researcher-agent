# PROGRESS.md — Stock Researcher Agent
*Last Updated: 2026-10-14*

## 1. Purpose
Deterministic stock research and rule-based investment assessment engine for Indian listed equities (NSE/BSE). Collects verifiable factual data, computes indicators, derives audit-grade classifications, and serves them via REST API and CLI.

## 2. Architecture Snapshot
- **Adapters (Local/Render):** Deterministic scraping of Yahoo Finance (`yfinance`), Screener.in (`requests`+`BeautifulSoup`), and Google News RSS (`news.py`).
- **Pipeline & Schemas (Local/Render):** `services/research_pipeline.py` synthesizes adapter payloads into canonical `ResearchResult v1` validated against JSON Schema.
- **REST API (Render Cloud):** FastAPI service (`interfaces/api.py`) hosting `GET /health`, `POST /research`, and `GET /research/{symbol}` with threadpool offloading.
- **Audit Persistence (Supabase Cloud):** Append-only tables `research_snapshots` and `investment_recommendations` guarded by RLS and PostgreSQL immutability triggers.
- **Front-End & Skill (Oracle VM / OpenClaw):** OpenClaw agent invokes `skills/stock-research/run.py` to orchestrate research, 6-hr caching, rule evaluation, and Markdown chat outputs.

## 3. Status

### Implemented & Unit-Tested Locally
- Core deterministic adapters (`market_data.py`, `screener.py`, `news.py`) and schema validation pipeline (`research_pipeline.py`).
- Higher-level deterministic assessment engine (`investment_assessment.py`) and 8-section explainer (`explainer.py`).
- Supabase PostgREST client repository (`services/supabase_repo.py`) with 6-hr caching and error-forwarding logic.
- Client research runner (`services/research_client.py`) with 75s bounded timeout and retries for 502/503/504 errors.
- Deterministic DEV/PROD environment toggle (`skills/stock-research/run.py`) with strict precedence and Supabase bypass in DEV mode.
- Complete unit test suite: 155 tests passing locally across all modules (`tests/`).

### Deployed & Live-Verified
- FastAPI REST service (`interfaces/api.py`) deployed on Render; live `/health` check independently verified returning HTTP 200 OK.
- PostgreSQL schema migration (`001_initial_stock_research_schema.sql`) applied and verified in Supabase SQL Editor.

### Built but Untested / Unresolved
- **Live Supabase End-to-End Persistence (UNRESOLVED):** While unit-tested with mocks, the previous real run's snapshot persistence failed (HTTP 403 / RLS restriction). Live persistence using `SUPABASE_SERVICE_ROLE_KEY` has not been tested or resolved.
- **Live Gemini Explainer:** AI explainer fallback is verified with unit mocks, but live outbound calls depend on active API keys at runtime.

### Not Built
- **API Authentication & Rate Limiting:** Live Render endpoints currently have no auth checks or rate limiting.
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

## 5. Risks and Open Issues
- **Unauthenticated Render Endpoints:** Live `POST /research` and `GET /research/{symbol}` are open to the public without API keys, rate limits, or concurrency guards.
- **Undecided Supabase Write Location:** Determining whether writes stay on client or move to Render impacts where `SUPABASE_SERVICE_ROLE_KEY` must be stored.
- **Single-Source Failure Crash:** If Screener.in or Yahoo Finance blocks requests or errors out, the entire research run raises an unhandled exception instead of outputting partial evidence.

## 6. Next Steps
1. **Lock API authentication** *(Blocker for production use)* — Add API key header check to all endpoints except `/health`, add concurrency limiter (1–2 jobs), and disable public `/docs` in production.
2. **Decide where Supabase writes happen** — Evaluate moving writes inside Render API so `SUPABASE_SERVICE_ROLE_KEY` stays strictly in Render environment variables.
3. **Commit pending files** — Stage and commit verified DEV/PROD toggle changes after explicit approval.
4. **Run an authorized live Supabase write test** — Verify snapshot and recommendation record creation using live credentials.
5. **Connect OpenClaw** — Mount `skills/stock-research/` into OpenClaw workspace on the Oracle VM.
6. **Implement partial reports when a source fails** — Allow pipeline to return partial results marked `UNAVAILABLE` if an individual adapter fails.
7. **Add a daily schedule** — Set up automated cron/heartbeat routines for equity watchlists.
8. **Add the Kite adapter** — Implement Zerodha Kite Connect as the primary market data feed.

## 7. How to Run and Test
```bash
# 1. Run full test suite (offline / mocked)
.venv-market/bin/python -m unittest discover tests

# 2. Run local research in DEV mode (scrapes directly, bypasses Supabase & Render)
.venv-market/bin/python -m skills.stock-research.run TCS --env dev

# 3. Run research via deployed Render API (requires deployed service access)
.venv-market/bin/python -m skills.stock-research.run TCS --env prod

# 4. Check live Render health endpoint (safe read-only GET)
curl -s https://stock-researcher-agent.onrender.com/health

# 5. Check git working tree for formatting issues
git diff --check
```
