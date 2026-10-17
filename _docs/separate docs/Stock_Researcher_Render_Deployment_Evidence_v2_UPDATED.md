# Stock Researcher --- Render Deployment Evidence and OpenClaw Integration

**Updated:** 11 October 2026\
**Repository:** `appurajacool2015/stock-researcher-agent`\
**Render service:** `stock-researcher-agent`\
**Status:** Render dashboard showed **Deploy succeeded / Live**.

> This document records observed evidence. A live REST API does not
> automatically mean OpenClaw has been configured to call it; verify the
> skill/tool implementation.

## 1. Account identifiers

-   **Requesty model/API account:** `ajjw2025@gmail.com`
-   **Render deployment account:** `ajjw2025@gmail.com`

These emails are account identifiers only, not passwords or API keys. Do
not record passwords, recovery codes, or secret values here.

## 2. Render deployment

-   Service type: Web Service
-   Branch: `main`
-   Runtime: Python 3
-   Region: Singapore
-   Root directory: blank (repository root)
-   Instance: Free
-   Deployment label: `added rest api`
-   Source commit displayed: `7ef7c63`
-   Dashboard deployment time: 11 October 2026, 3:08:17 AM IST
-   Startup command shown in logs:

``` bash
uvicorn interfaces.api:app --host 0.0.0.0 --port $PORT
```

The screenshot showed Uvicorn listening on `0.0.0.0:10000`. Keep `$PORT`
in the command rather than hard-coding a port. The exact Build Command
was not visible in the supplied screenshot; verify it in Render Settings
before recreating or changing the service.

## 3. Verified health check

``` bash
curl -i https://stock-researcher-agent.onrender.com/health
```

Observed response:

``` json
{"ok":true,"service":"stock-researcher-api","status":"healthy"}
```

## 4. Verified research endpoint

### Historical baseline (Commit `7ef7c63`, unauthenticated):
``` bash
curl -i https://stock-researcher-agent.onrender.com/research/TCS
```

The observed response was a ResearchResult JSON with
`schema_version: "1.0"`, symbol `TCS`, company name
`Tata Consultancy Services Ltd`, `symbol_match_confidence: "EXACT"`, and
`overall_status: "PARTIAL"`.

### Security Upgrade (Commit `942df85`, awaiting deployment):
Following commit `942df85`, all `/research` routes are protected with `X-API-Key`.
Calling without the key returns `401 Unauthorized` (or `500 Internal Server Error` if `RESEARCH_API_KEY` is unset on the server).
The authenticated verification command is:
``` bash
curl -i -H "X-API-Key: $RESEARCH_API_KEY" https://stock-researcher-agent.onrender.com/research/TCS
```

Observed data quality summary: 25 verified, 4 derived, 2 unavailable, 0
stale, 0 conflicting and 0 failed. This is a dated sample, not a
guarantee that market or fundamental values remain current. Read
field-level provenance and `as_of_date`. `PARTIAL` can still be a valid
research result; do not automatically classify it as a pipeline failure.

## 5. Requesty model API and OpenClaw

-   Requesty account: `ajjw2025@gmail.com`
-   Base URL: `https://router.requesty.ai/v1`
-   Model ID: `google/gemma-4-31b-it`
-   API-key environment variable: `REQUESTY_API_KEY`
-   Secret storage: `~/.openclaw/.env`
-   OpenClaw configuration: `~/.openclaw/openclaw.json`

Previously verified inference test:

``` bash
openclaw agent --agent main --message "Reply with exactly: Requesty connection OK." --timeout 60
```

Never print or commit the API key or `.env` contents.

## 6. How the services fit together

-   **Requesty** provides the LLM inference API used by OpenClaw.
-   **Render** hosts the deterministic stock research REST API.
-   OpenClaw must have a stock-research skill/tool that explicitly calls
    the Render HTTPS endpoint, parses the response, preserves evidence
    and handles HTTP errors. The API being live does not itself prove
    automatic integration. Do not duplicate deterministic research
    calculations in the LLM layer.

## 7. Recovery checklist

1.  Sign in to Render using `ajjw2025@gmail.com`; verify service status
    and logs.
2.  Verify `RESEARCH_API_KEY` is configured in Render Environment variables.
3.  Run `/health` (public, should return 200 OK without key).
4.  Run one known-symbol request with key, e.g.
    `curl -fsS -H "X-API-Key: $RESEARCH_API_KEY" https://stock-researcher-agent.onrender.com/research/TCS`.
5.  Review `overall_status`, `data_quality_summary`, field statuses and
    provenance.
6.  Verify OpenClaw gateway and Requesty separately.
7.  Verify the stock-research skill actually calls Render with the key.
8.  Record the deployed commit hash and test outcome.

Free instances can spin down after inactivity, causing cold-start
delays. A `HEAD /` or `GET /` 404 is not the health endpoint; use
`/health`.

## 8. Legacy Bedrock notes

Previously supplied Bedrock documents describe an older setup in which
Nova models returned `NOT_AUTHORIZED` / `Operation not allowed`. They
are superseded as current setup instructions. Do not reinstall or switch
back to Bedrock during routine recovery unless that change is
deliberately approved.

## 9. Security

-   Never print `~/.openclaw/.env` or share API-key values.
-   Keep credentials out of Git, logs, screenshots and documentation.
-   Account email addresses are identifiers only; never add passwords or
    recovery codes.
-   Do not invent API routes, environment variable names or test
    results.
-   Re-verify Render settings before changing deployment configuration.


## Current development framework and account directory

### Account identifiers
- **Oracle Cloud VM account label:** `ajjw2025` (Root user, as supplied). VM: `129.225.120.74`. The documented SSH login remains Linux user `ubuntu`.
- **Render account:** `ajjw2025@gmail.com`
- **Requesty API account:** `ajjw2025@gmail.com`
- **GitHub account:** `appurajacool2015@gmail.com`
- **Repository:** `appurajacool2015/stock-researcher-agent`

Account identifiers are not passwords or API keys. Do not document or expose secrets.

### Setup discussion references
- **ChatGPT:** https://chatgpt.com/share/6acb63bd-5eb0-83ec-8f20-d573edb9ace1
- **Gemini:** https://gemini.google.com/app/a4890209f82bbe83

### Development and runtime flow
1. Develop and validate code locally in **Antigravity**.
2. Push approved source code to the GitHub repository.
3. Render deploys the production REST API from the repository.
4. A user asks for stock research through **Telegram or WhatsApp**.
5. **OpenClaw** on the Oracle Cloud VM handles the conversation, uses **Requesty** for LLM inference, and calls the **Render REST API** through the stock-research skill/tool.
6. OpenClaw formats the deterministic `ResearchResult` payload and returns the response to the user.

**Architecture note:** GitHub is the source-code/version-control and deployment source, not the live market-data API. The current documented live research endpoint is Render. A separate GitHub Pages (`github.io`) data endpoint is not evidenced in the supplied operational records and should only be added to the runtime path if it is separately configured and verified.
