# Stock Researcher Agent 📈

A reliable, factual stock-research engine for Indian listed companies (NSE & BSE).

---

## 1. What is this project? (In Plain English)

When people invest in stocks, they need accurate facts: P/E ratio, profit growth, debt levels, moving averages, volume trends, and recent news.

Normally, AI chatbots like ChatGPT or Gemini might "hallucinate" (make up believable-sounding numbers that are actually wrong). 

**The Stock Researcher Agent solves this problem:**
- It **never invents numbers**.
- It collects real, verifiable facts directly from financial data sources (Screener.in and Yahoo Finance).
- It runs strict mathematical calculations in Python code, not in an AI's imagination.
- If a number is missing or cannot be verified, it flags it as `UNAVAILABLE` rather than guessing.
- It provides a rule-based **Buying Zone Assessment** with defined support, resistance, invalidation stops, and reward-to-risk ratios.
- It displays a compact **16-row Key Metrics table** with data-quality provenance tags (`VERIFIED`, `DERIVED`, `UNAVAILABLE`) and as-of dates.

---

## 2. First-Time Setup: Installing From Scratch

If you are setting this up on a new computer or fresh workstation, follow these steps:

### 1. Clone the repository
```bash
git clone https://github.com/appurajacool2015/stock-researcher-agent.git
cd stock-researcher-agent
```

### 2. Create the Python virtual environment
We use a dedicated local environment named `.venv-market`:
```bash
python3 -m venv .venv-market
```

### 3. Install required software packages
```bash
.venv-market/bin/pip install -r requirements.txt
```

### 4. Set up your local `.env` configuration file
Copy the sample template to create your private `.env` file:
```bash
cp .env.example .env
```
*(Your private `.env` file is git-ignored and stays on your computer. Never paste passwords or commit `.env` to Git!)*

### 5. Verify the installation
Run the built-in quality test suite:
```bash
.venv-market/bin/python -m unittest discover tests
```
> If you see `Ran 228 tests in ... OK`, your local environment is 100% installed and ready!

---

## 3. Quick Start: How to Run in 2 Minutes

You do not need to be a programmer to test this system on your computer or VM.

### Step 1: Open Terminal in the project folder
Ensure you are in the project folder on your computer:
```bash
cd /Users/anand/Developer/AI/experiment/anti-gravity/stock-researcher-agent
```

### Step 2: Test a stock in Development Mode (`--env dev`)
Run this single command to fetch and analyze a stock (for example, **TCS**):
```bash
.venv-market/bin/python -m skills.stock-research.run TCS --env dev
```
> **What this does:** It gathers fresh data for Tata Consultancy Services (TCS) directly on your laptop, calculates indicators, evaluates the buying zone, and prints a clear report in your terminal without requiring any cloud connections or passwords.

### Step 3: Test a stock in Production Mode (`--env prod`)
To fetch data through the live Render cloud API:
```bash
# Set your API key in the shell (or in ~/.bashrc)
export RESEARCH_API_KEY="your-secret-api-key"

.venv-market/bin/python -m skills.stock-research.run TCS --env prod
```
> **What this does:** It calls the live Render production service over HTTPS, which checks the 6-hour Supabase cache, scrapes fresh market data on cache misses, calculates all technicals and buying zones, and saves an audit snapshot.

### Step 4: Run the automatic quality checks
Run the full automated test suite:
```bash
.venv-market/bin/python -m unittest discover tests
```
> **What this does:** It runs all **228 automatic tests** in under 3 seconds to prove that all calculators, buying zone models, security rules, and data scrapers are working perfectly.

---

## 4. Architecture & Key Features

### Complete Service Topology

```
User (WhatsApp / Telegram)
  ↓
[1] Oracle Cloud VM (OpenClaw) ──► Talks to users; handles conversation
  │   └── Client Runner requires ONLY: RESEARCH_API_KEY in ~/.bashrc (Zero DB credentials!)
  ↓ (HTTPS + X-API-Key)
[2] Render Cloud API (Singapore) ──► Secure FastAPI server (interfaces/api.py)
  ├── 6-hr Cache Check (Supabase PostgreSQL)
  ├── Scrapers & Engine (Screener.in, Yahoo Finance, Google News)
  ├── Buying Zone Evaluator & Key Metrics Builder
  └── Append-only Audit Persistence (Supabase PostgreSQL)
  ↓
[3] Supabase Cloud Database ──► Caches results for 6 hours; stores audit snapshots
  ▲
  │ (Auto-deploys on git push)
[4] GitHub Source Repository ──► appurajacool2015/stock-researcher-agent (main)
```

### Zero-Database Client Decoupling (Oracle VM Setup)
On the Oracle VM (or any client machine running OpenClaw):
- The client runner does **not** need PostgreSQL drivers, database URLs, or Supabase service keys.
- It requires only **one environment variable**:
  ```bash
  export RESEARCH_API_KEY="your-secret-key"
  ```
- Adding this to `~/.bashrc` ensures it stays configured permanently even if the virtual machine restarts.
- All database caching, baseline history lookups, and audit persistence are executed securely on the Render cloud server.

### Deterministic Buying Zone Assessment
Every research run evaluates price structure against moving averages and swing extremes to produce one of 5 mutually exclusive statuses:
1. `IN_BUYING_ZONE`: Price pulled back near rising 50/200-DMA with favorable risk-to-reward (≥ 1.5:1).
2. `WAIT_FOR_PULLBACK`: Structural uptrend intact, but momentum is overextended (RSI > 65 or price > 8% above 50-DMA).
3. `BREAKOUT_WATCH`: Consolidating tightly within 3% of confirmed swing resistance on expanding volume.
4. `AVOID_OR_DISTRIBUTION`: Trading below 200-DMA or under heavy institutional/distribution volume.
5. `NEUTRAL_CONSOLIDATION`: Range-bound without a directional edge.

Every evaluation computes:
- **Nearest Support Reference** (20-day swing low or 50/200-DMA)
- **Invalidation Reference / Stop** (risk boundary)
- **Target Resistance Reference** (20-day swing high)
- **Reward-to-Risk Ratio** (`X.XX : 1`)

### Compact 16-Row Key Metrics Table
The report presents 16 core facts formatted in a standardized 4-column Markdown table:

| Metric | Value | Status | As-Of Date |
| :--- | :--- | :--- | :--- |
| CMP | ₹2,465.00 | VERIFIED | 2026-10-16 |
| P/E | 16.30x | VERIFIED | 2026-03-31 |
| ROCE | 63.0% | VERIFIED | 2026-03-31 |
| ROE | 51.8% | VERIFIED | 2026-03-31 |
| 3Y Sales Growth | 6.0% | VERIFIED | 2026-03-31 |
| 3Y Profit Growth | 8.0% | VERIFIED | 2026-03-31 |
| 50 DMA | ₹2,241.62 | VERIFIED | 2026-10-16 |
| 200 DMA | ₹2,465.43 | VERIFIED | 2026-10-16 |
| RSI (14) | 73.5 | VERIFIED | 2026-10-16 |
| Debt-to-Equity | UNAVAILABLE | UNAVAILABLE | — |
| Promoter Pledge | UNAVAILABLE | UNAVAILABLE | — |
| PEG | UNAVAILABLE | UNAVAILABLE | — |
| Trading Volume (Latest) | 12,166,634 | VERIFIED | 2026-10-16 |
| 20-Day Avg Volume | 5,359,695 | DERIVED | 2026-10-16 |
| Relative Volume | 2.27x (+127.0%) | DERIVED | 2026-10-16 |
| OBV Trend (14d) | Positive (+0.67) | DERIVED | 2026-10-16 |

---

## 5. Returning After a Break: 5-Minute Resume Checklist

If you haven't worked on this project in days or weeks, use this 3-step checklist to get up to speed immediately:

1. **Step 1: Check your local code health**
   Run the test suite on your computer:
   ```bash
   .venv-market/bin/python -m unittest discover tests
   ```
   *Expected outcome:* All 228 tests pass (`OK`).

2. **Step 2: Check the live cloud server**
   Verify the public Render website is healthy:
   ```bash
   curl -s https://stock-researcher-agent.onrender.com/health
   ```
   *Expected outcome:* `{"ok":true,"service":"stock-researcher-api","status":"healthy"}`.

3. **Step 3: Check your Git status and ask Antigravity**
   Check your working tree:
   ```bash
   git status
   ```
   Then open Antigravity and say:
   > **"Read @PROGRESS.md and tell me what's next."**
   *Antigravity will give you a 3-line summary of current status, open risks, and the immediate next step.*

---

## 6. How We Work with Antigravity (Daily Rhythm)

When using the Antigravity AI coding assistant to work on this project, follow this simple rhythm:

```
[Start of Chat] ➔ "Read @PROGRESS.md and tell me what's next."
      ↓
[During Chat]   ➔ Plan first, build second. Nothing gets built until you say "go".
      ↓
[End of Chat]   ➔ Type "/wrap-up" (the workflow button).
```

1. **Rules hold the brief and safety rules:**
   - They load automatically in the background of every chat.
   - They protect your private passwords, stop accidental costs, and enforce strict code safety.
2. **`PROGRESS.md` holds the current state:**
   - Always start a new chat by typing:
     > **"Read @PROGRESS.md and tell me what's next."**
   - This immediately gives you a 3-line summary of where we are and what to do next.
3. **Plan first, build second:**
   - Antigravity will always explain what it found, give you options and a recommendation, and wait for your explicit permission.
   - **Nothing gets built, modified, or committed until you say "go".**
4. **End each chat by typing `/wrap-up`:**
   - The slash command `/wrap-up` is our automated workflow button.
   - It runs all tests, cleans up project memory, updates `PROGRESS.md`, and prepares a safe commit message.

---

## 7. Helpful Commands Cheatsheet

| Task | Command |
| :--- | :--- |
| **Run all 228 tests** | `.venv-market/bin/python -m unittest discover tests` |
| **Research stock locally (DEV)** | `.venv-market/bin/python -m skills.stock-research.run INFY --env dev` |
| **Research stock via cloud (PROD)** | `.venv-market/bin/python -m skills.stock-research.run INFY --env prod` |
| **Check cloud API health** | `curl -s https://stock-researcher-agent.onrender.com/health` |
| **Test cloud research with API key** | `curl -s -H "X-API-Key: $RESEARCH_API_KEY" https://stock-researcher-agent.onrender.com/research/TCS` |
| **Check Git status** | `git status` |
| **Check Git history** | `git log --oneline -5` |

---

## 8. Safety & Privacy Guardrails

1. **Private `.env` file is strictly off-limits:**
   - The `.env` file contains private keys and passwords.
   - Antigravity is strictly forbidden from opening, inspecting, or editing `.env`.
   - Never paste private keys into AI chat windows.
   - For templates and variable names, always refer to [`.env.example`](file:///Users/anand/Developer/AI/experiment/anti-gravity/stock-researcher-agent/.env.example).
2. **Supabase Row-Level Security (RLS) on Render:**
   - On the Render dashboard, ensure `SUPABASE_SERVICE_ROLE_KEY` is set using Supabase's secret `service_role` key (found under Project Settings -> API).
   - If the public `anon` key is used, Supabase rejects writes with PostgreSQL error `42501` (violates row-level security policy).
3. **Graceful Fail-Safe Persistence:**
   - Even if the cloud database experiences a write failure or temporary network timeout, Render returns the completed research report to the user without crashing, appending a clear persistence notice.
4. **Scraping is Free ($0):**
   - All stock data is scraped from free sources. AI formatting is optional and kept OFF by default so you never incur unexpected costs.
5. **Not Financial Advice:**
   - This system provides structured facts and rule-based calculations; it does not issue automated trade orders or personal financial advice.

---

## 9. More Detailed Technical Documentation

For in-depth architecture diagrams, security specifications, and deployment runbooks:
- [`PROGRESS.md`](file:///Users/anand/Developer/AI/experiment/anti-gravity/stock-researcher-agent/PROGRESS.md) — Current state, completed milestones, and immediate next steps.
- [`_docs/Stock_Researcher_Agent_Master_Manual_v3.0.md`](file:///Users/anand/Developer/AI/experiment/anti-gravity/stock-researcher-agent/_docs/Stock_Researcher_Agent_Master_Manual_v3.0.md) — Comprehensive technical reference, schema definitions, and Render operations guide.
- [`.agent/rules/project-brief.md`](file:///Users/anand/Developer/AI/experiment/anti-gravity/stock-researcher-agent/.agent/rules/project-brief.md) — Core project rules and boundaries.
