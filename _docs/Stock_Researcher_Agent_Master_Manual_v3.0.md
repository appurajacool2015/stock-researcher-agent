# Stock Researcher Agent — Master Manual v3.0
**Unified Architecture, Security Specification, Deployment & Operations Reference**

*Last Updated: 17 October 2026*  
*Status: Production Live & Decoupled (Render: Live; Oracle VM OpenClaw: Verified; 228 Unit Tests Passing)*  
*Repository: `appurajacool2015/stock-researcher-agent` (`main` branch)*  
*Region / Market: Singapore (Host) / NSE & BSE (India, IST, INR)*

---

## 1. System Mission & Core Invariants

The **Stock Researcher Agent** is the deterministic research and financial intelligence engine of the Stock Intelligence System.

### Core Architecture Invariants
1. **The Python pipeline is the sole producer of research facts.** Numerical metrics, indicators, classifications, provenance, and data-quality summaries originate strictly from deterministic code and verifiable external sources.
2. **The LLM (OpenClaw / Requesty) is an explanation and orchestration layer.** It must NEVER calculate, estimate, extrapolate, or fabricate financial indicators (PE, PB, ROCE, ROE, CMP, DMA, RSI, volume, shareholding).
3. **Fail-Closed Security & Provenance Preservation:** Every metric retains its pipeline-assigned provenance tag (`VERIFIED`, `DERIVED`, `UNAVAILABLE`, `STALE`, `CONFLICTING`, `FAILED`). Missing values must be recorded as `UNAVAILABLE` and never silently imputed.
4. **Decoupled Architecture:** OpenClaw on Oracle VM operates as a lightweight client requiring **only `RESEARCH_API_KEY`**. All database caching, baseline history lookups, market scraping, and append-only Supabase persistence are executed on the Render cloud service.

```
User (WhatsApp / Telegram)
  ↓
Oracle Cloud VM (OpenClaw Gateway + Requesty LLM)
  │  └── Client Runner (skills/stock-research/run.py)
  │      Requires ONLY: RESEARCH_API_KEY in ~/.bashrc (Zero DB credentials!)
  ↓ (HTTPS + X-API-Key)
Render Cloud API (Singapore, interfaces/api.py)
  ├── 1. Check 6-Hour Supabase Cache
  │       ├── Cache Hit  → Return cached ResearchResult immediately
  │       └── Cache Miss → Execute Deterministic Pipeline
  │                          ├── Rate Limiter (10 req/min per IP)
  │                          ├── Concurrency Guard (max 2 active)
  │                          ├── Screener.in (Fundamentals)
  │                          ├── Yahoo Finance (Technicals & Volume)
  │                          └── Google News RSS (Sentiment)
  ├── 2. Evaluate Buying Zone & Build 16-Row Key Metrics Table
  └── 3. Async/Non-Blocking Audit Persistence (Supabase PostgreSQL)
          ├── research_snapshots (JSONB payload)
          └── investment_recommendations (Verdict & R:R)
```

---

## 2. Component Topology & Verified Live Status

### Component Directory
| Component | Host / Environment | Role | Operational State |
| :--- | :--- | :--- | :--- |
| **Render Web Service** | Render (Singapore) | FastAPI REST API (`interfaces/api.py`) | **Live & Healthy** (`https://stock-researcher-agent.onrender.com/health`). Protected by `X-API-Key`. |
| **Oracle Cloud VM** | Oracle Cloud (`129.225.120.74`) | Chat interface & tool orchestration | **Active & Verified** (User `ubuntu`). Configured via `~/.bashrc` with `RESEARCH_API_KEY`. |
| **OpenClaw Skill** | Oracle Cloud VM | Skill wrapper (`skills/stock-research/run.py`) | **Live-Verified** against Render production API for TCS. |
| **Supabase Cloud DB** | Supabase PostgreSQL | Append-only audit store & 6-hr cache | **Schema Applied**. Requires `SUPABASE_SERVICE_ROLE_KEY` on Render to satisfy PostgreSQL RLS. |
| **Local Antigravity** | macOS (Local Workstation) | Development, testing, and git control | **Clean** (228 automated unit tests passing in ~2.5s). |

---

## 3. REST API Specification & Security (`interfaces/api.py`)

### 3.1 Authentication & Authorization
- **Header:** `X-API-Key`
- **Server Environment Variable:** `RESEARCH_API_KEY`
- **Protected Endpoints:** `POST /research` and `GET /research/{symbol}`
- **Public Endpoint:** `GET /health` (never requires authentication)
- **Fail-Closed Principle:** If `RESEARCH_API_KEY` is not set on the server, the server logs an internal error and returns HTTP 500 (`"Internal server error."`) without leaking configuration details.
- **Timing-Safe Comparison:** Uses `secrets.compare_digest` to prevent side-channel timing attacks.

### 3.2 Thread-Safe, Bounded Sliding-Window Rate Limiting
- **Default Limit:** 10 requests per 60-second window per client IP (`RATE_LIMIT_REQUESTS=10`, `RATE_LIMIT_WINDOW_SECONDS=60`).
- **Memory Bounding & Eviction:** Tracks up to 10,000 distinct client IPs (`MAX_TRACKED_IPS=10000`). If capacity is reached, the oldest tracked IP is evicted (LRU policy), preventing memory exhaustion from spoofed IP addresses.
- **Thread Safety:** All timestamp pruning and tracking are guarded by `threading.Lock`.
- **Response on Breach:** HTTP 429 (`"Rate limit exceeded: maximum 10 requests per 60 seconds."`).

### 3.3 Leak-Safe Concurrency Limiting
- **Capacity:** Maximum 2 concurrent research pipelines (`MAX_CONCURRENT_REQUESTS=2`).
- **Saturation Timeout:** 0.2-second non-blocking acquisition window (`CONCURRENCY_TIMEOUT_SECONDS=0.2`). If both pipeline slots are occupied and a new request arrives, it immediately returns HTTP 429 (`"Server busy: maximum 2 concurrent operations active. Please retry shortly."`) rather than accumulating a backlog.
- **Leak-Free Permit Management:** The semaphore permit is released in a strict `finally` block, ensuring permits are returned even if a request raises an exception or the client cancels the HTTP connection.
- **Threadpool Offload:** Synchronous scrapers run via `fastapi.concurrency.run_in_threadpool`, keeping the main async event loop completely unblocked for health checks.

### 3.4 Production API Documentation Security
- **Production Detection:** Enabled when `RENDER=true` (automatically set by Render) or `ENVIRONMENT` / `STOCK_RESEARCH_ENV` is set to `prod` or `production`.
- **Behavior:** In production, `/docs` (Swagger UI), `/redoc`, and `/openapi.json` are completely disabled (`None`). In local development, they remain accessible for developer inspection.

---

## 4. Deterministic Buying Zone & Key Metrics Specification

### 4.1 Deterministic Buying Zone Assessment (`intelligence/investment_assessment.py`)
The buying zone model evaluates structural price action against moving averages and swing extremes to assign one of 5 mutually exclusive statuses:

| Status | Quantitative Criteria | Action Guidance |
| :--- | :--- | :--- |
| **`IN_BUYING_ZONE`** | Price within 3% of rising 50-DMA or 200-DMA, RSI 40–60, Reward-to-Risk ratio ≥ 1.5:1. | Favorable entry conditions. Near-term support provides a defined risk boundary. |
| **`WAIT_FOR_PULLBACK`** | Structural uptrend intact (CMP > 200-DMA), but momentum extended (RSI > 65 or price > 8% above 50-DMA). | Uptrend is intact, but price is short-term extended with elevated near-term pullback risk. |
| **`BREAKOUT_WATCH`** | Price consolidating within 3% of confirmed 20-day swing high on expanding volume. | Monitor for confirmed breakout above swing resistance with volume confirmation. |
| **`AVOID_OR_DISTRIBUTION`** | Price below 200-DMA, or RSI < 35 with accelerating downside, or heavy distribution volume. | Unfavorable trend or active distribution. Capital preservation takes precedence. |
| **`NEUTRAL_CONSOLIDATION`** | Oscillating within moving average band without directional conviction. | Sideways consolidation. Wait for structural resolution. |

#### Risk/Reward Calculation Rules
- **Nearest Support Reference:** Maximum of 20-day swing low, 50-DMA, and 200-DMA located strictly below CMP.
- **Invalidation Reference (Stop):** Placed 2% below the nearest support reference.
- **Target Resistance Reference:** Lowest confirmed resistance reference located strictly above CMP (20-day swing high).
- **Reward-to-Risk Ratio:**
  $$\text{Downside Risk} = \text{CMP} - \text{Stop}$$
  $$\text{Upside Potential} = \text{Target} - \text{CMP}$$
  $$\text{R:R Ratio} = \frac{\text{Upside Potential}}{\text{Downside Risk}} : 1$$

### 4.2 Compact 16-Row Key Metrics Table
The presentation layer formats exactly 16 metrics with provenance status and as-of dates:

| Metric | Source / Method | Status Rules |
| :--- | :--- | :--- |
| **CMP** | Yahoo Finance (Latest Close) | VERIFIED / STALE |
| **P/E** | Screener.in Summary Card | VERIFIED / UNAVAILABLE |
| **ROCE** | Screener.in Summary Card | VERIFIED / UNAVAILABLE |
| **ROE** | Screener.in Summary Card | VERIFIED / UNAVAILABLE |
| **3Y Sales Growth** | Screener.in Compounded Sales Growth | VERIFIED / UNAVAILABLE |
| **3Y Profit Growth** | Screener.in Compounded Profit Growth | VERIFIED / UNAVAILABLE |
| **50 DMA** | Python Rolling Mean (50 sessions) | VERIFIED / DERIVED |
| **200 DMA** | Python Rolling Mean (200 sessions) | VERIFIED / DERIVED |
| **RSI (14)** | Wilder's Smoothed RSI (14 sessions) | VERIFIED / DERIVED |
| **Debt-to-Equity** | Screener.in (Flagged UNAVAILABLE if omitted) | VERIFIED / UNAVAILABLE |
| **Promoter Pledge** | Screener.in (Flagged UNAVAILABLE if omitted) | VERIFIED / UNAVAILABLE |
| **PEG** | Screener.in (Flagged UNAVAILABLE - not calculated) | UNAVAILABLE |
| **Trading Volume (Latest)** | Yahoo Finance Latest Daily Volume | VERIFIED / UNAVAILABLE |
| **20-Day Avg Volume** | Python Rolling Mean (20 volume sessions) | DERIVED |
| **Relative Volume** | Ratio: $\frac{\text{Latest Volume}}{\text{20D Avg Volume}}$ | DERIVED |
| **OBV Trend (14d)** | On-Balance Volume 14-session linear slope | DERIVED (Positive / Neutral / Negative) |

---

## 5. Supabase Persistence Architecture (`services/supabase_repo.py`)

### 5.1 Tables & Schema
- **`research_snapshots`:** Raw research result payloads (`JSONB`), symbol, exchange, data quality counts, and created timestamp.
- **`investment_recommendations`:** Evaluated investment action, buying zone status, confidence score, and rationale.
- **Foreign Key Guard:** `investment_recommendations.snapshot_id` references `research_snapshots.id` with `ON DELETE RESTRICT` to protect audit trails.
- **PostgreSQL Immutability Trigger:** Enforces append-only rules; any `UPDATE` or `DELETE` statement raises an explicit PostgreSQL exception.

### 5.2 Row-Level Security (RLS) & Error 42501 Resolution
When PostgreSQL Row-Level Security (RLS) is enabled on Supabase tables:
- **Root Cause of Error `42501`:** If Render's environment variable `SUPABASE_SERVICE_ROLE_KEY` contains the public `anon` key instead of the secret `service_role` key, Supabase rejects the `INSERT` with:
  `HTTP 401 ({"code":"42501","message":"new row violates row-level security policy for table \"research_snapshots\""})`.
- **Resolution:**
  1. Open **Supabase Dashboard** -> **Project Settings** -> **API**.
  2. Copy the secret **`service_role`** key (not the `anon` public key).
  3. Open **Render Dashboard** -> `stock-researcher-agent` -> **Environment**.
  4. Paste into `SUPABASE_SERVICE_ROLE_KEY` and save.
- **Fail-Safe Non-Blocking Design:** If Supabase persistence fails for any reason (e.g. invalid key or network timeout), the research pipeline **does not crash**. Render successfully returns the full research report to the client, appending a clear persistence notice at the bottom.

---

## 6. Verification & Test Suite Reference

The project includes an offline-executable unit test suite with zero external network dependencies:

```bash
# Run all 228 unit tests
.venv-market/bin/python -m unittest discover tests
```

### Test Coverage Breakdown (228 Passing Tests)
| Test Module | Tests | Coverage & Verification Areas |
| :--- | :--- | :--- |
| `tests/test_api.py` | 27 | Public `/health`, API key auth, 401/500 fail-closed behavior, rate limiting sliding window & LRU eviction, concurrency saturation, and docs disabling. |
| `tests/test_research_client.py` | 7 | Schema compliance, transient 502/503 retries, 75s timeouts, missing key validation, and fallback enforcement. |
| `tests/test_skill_run.py` | 15 | DEV/PROD environment resolution, 6-hr cache evaluation, Supabase bypass in DEV, and output formatting. |
| `tests/test_investment_assessment.py` | 40 | 5 investment actions, buying zone evaluations (5 statuses), support/stop/resistance math, R:R calculation, and 16-row Key Metrics building. |
| `tests/test_explainer.py` | 17 | 16-row Markdown table formatting, Buying Zone card presentation, synchronized Key Levels, and audit persistence notices. |
| `tests/test_fundamentals.py` | 25 | PE, PB, ROCE, ROE, debt-to-equity, sales/profit growth calculations, and boundary checks. |
| `tests/test_technicals.py` | 67 | 50 DMA, 200 DMA, Golden Cross, RSI 14, 20-day volume average, relative volume, and OBV trend calculation. |
| `tests/test_institutional.py` | 15 | FII/DII shareholding changes, quarterly deltas, and promoter pledge risk checks. |
| `tests/test_news.py` | 12 | Google News RSS parsing, sentiment scoring, and deduplication. |
| `tests/test_market_data.py` | 8 | Yahoo Finance historical quotes, 20-day swing extremes, and data normalization. |

---

## 7. Operational Runbook & Oracle VM Deployment

### 7.1 Oracle VM OpenClaw Setup (Client Machine)
On the Oracle VM (`/home/ubuntu/openclaw/stock-intelligence/stock-researcher`):
1. **Configure Environment in `~/.bashrc`:**
   ```bash
   echo 'export RESEARCH_API_KEY="your-secret-api-key"' >> ~/.bashrc
   source ~/.bashrc
   ```
2. **Verify Configuration:**
   ```bash
   echo $RESEARCH_API_KEY
   ```
3. **Execute Production Research:**
   ```bash
   .venv-market/bin/python -m skills.stock-research.run TCS --env prod
   ```
   *Expected outcome:* Connects to Render, evaluates buying zone and key metrics, and prints the complete report with zero local database configuration.

### 7.2 Render Environment Variables (Server Machine)
On Render Dashboard (`https://dashboard.render.com`):
- `RESEARCH_API_KEY`: Secret string matching client's key.
- `SUPABASE_URL`: `https://<your-project-id>.supabase.co`
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase secret `service_role` key (required for RLS bypass).
- `RENDER`: `true`
- `MAX_CONCURRENT_REQUESTS`: `2`
- `RATE_LIMIT_REQUESTS`: `10`
- `RATE_LIMIT_WINDOW_SECONDS`: `60`

---

## 8. Operational Troubleshooting Matrix

| Symptom | Probable Cause | Resolution |
| :--- | :--- | :--- |
| **HTTP 500 on all research calls** | `RESEARCH_API_KEY` is not set in Render environment. | Add `RESEARCH_API_KEY` to Render Dashboard Environment variables. |
| **HTTP 401 Unauthorized** | Missing or mismatching `X-API-Key` header. | Verify key matches the value stored in Render Dashboard. |
| **HTTP 429 Rate limit exceeded** | Client exceeded 10 requests within 60 seconds. | Wait for the sliding window to reset; increase `RATE_LIMIT_REQUESTS` if needed. |
| **HTTP 429 Concurrency limit exceeded** | 2 research pipelines are actively processing. | Retry after a few seconds; scraper will release permit upon completion. |
| **Request timeout (>50s)** | Render free tier container spinning up from idle. | Allow up to 75 seconds for cold start; issue a warm-up `GET /health` call first. |
| **HTTP 404 on `/docs`** | Production documentation disabling is active. | This is intentional in production; inspect endpoints locally in development mode. |
| **Supabase Error `42501` on Render** | Render has `anon` key instead of `service_role` key. | Copy `service_role` secret key from Supabase Dashboard -> API and save in Render. |
| **PEG / Debt-to-Equity `UNAVAILABLE`** | Screener omits the metric or entity is zero-debt. | Expected behavior. Deterministic engine strictly refuses to hallucinate financial metrics. |
