# Project Brief — Stock Researcher Agent

**PROJECT:** `stock-researcher-agent`, part of the Stock Intelligence system. Indian stocks (NSE/BSE), INR, IST. Python + FastAPI on Render, Supabase, optional Gemini explainer, OpenClaw on an Oracle VM as the chat front-end. OpenClaw uses Requesty for its own LLM calls; this repository does not.

## ANTIGRAVITY WORKING RHYTHM
- **Rules hold the brief and safety rules:** They load automatically in every chat.
- **PROGRESS.md holds the current state:** Start each chat with: *"Read @PROGRESS.md and tell me what's next."*
- **End each chat with `/wrap-up`:** The `/` is the workflow button; typing `/wrap-up` replaces remembering to ask for updates.
- **Plan first, build second:** Nothing gets built, modified, or committed until you say "go".

## START OF EVERY NEW CHAT
Before doing anything else, read the root `PROGRESS.md` and `AGENTS.md`. Then give me a three-line summary of the current state and next steps. Wait for my instruction before starting work.

## ALWAYS RULES
- **Plan first, build second:** Present two options and a recommendation. Wait for my approval before changing files or taking action. Nothing gets built until I say "go".
- **Explain in simple English:** Work in small steps and tell me how to test each step.
- **Strict facts & deterministic rules:** Numbers must come from code and data sources, never from an LLM. Classifications must come only from deterministic rules. Never place trades. Research output is not financial advice.
- **Scraping preferred; AI optional:** Scraping is free and preferred. AI calls are optional and OFF by default. Explain any cost before proposing a paid call.
- **API security rule:** Every endpoint except `/health` requires an API key. Treat this as a required security rule and verify implementation separately; do not assume it is already implemented.
- **Credential safety:** Never inspect, read, check, or edit `.env` at any cost unless explicitly instructed in that specific message. If verifying environment variables, inspect `.env.example` only. Never print, log, or commit secrets. Use environment variable names only. Keep `.env` git-ignored.
- **Protected governance files:** Do not edit `AGENTS.md` or `TOOLS.md` unless I explicitly approve the exact change.
- **Controlled git operations:** Make small, clear Git commits only when authorized. Never push without asking.
- **Scope discipline:** Do not change files outside the approved scope.
- **Safe execution:** Never run live network requests, database writes, deployments, or VM operations without explicit authorization.
- **Respect working tree:** Inspect existing user changes before editing. Never overwrite unrelated work.
