# TOOLS.md — Stock Researcher

## Purpose

This file documents the research sources and tooling used by the Stock Researcher.

Secrets must never be stored here.

---

# Research Sources

## Kite Connect

Source identifier:

`kite`

Preferred structured source for technical market data.

Potential data:

- Current market price
- Historical OHLC
- Volume
- Average volume
- Data required for 50 DMA
- Data required for 200 DMA
- Data required for RSI(14)
- 52-week high
- 52-week low

Derived indicators must be marked `DERIVED`.

Kite may only be used when valid credentials and API access are configured.

---

## Screener

Source identifier:

`screener`

Primary candidate source for:

- P/E
- P/B
- ROCE
- ROE
- Debt-to-equity
- Sales growth
- Profit growth
- Market capitalization
- Shareholding

Use only when access is available and permitted.

---

## Moneycontrol

Source identifier:

`moneycontrol`

Secondary/fallback source for:

- Current price
- Technical information
- Historical market information
- Company information
- Supporting fundamental information

---

## Economic Times

Source identifier:

`economic_times`

Candidate source for:

- Company news
- Corporate developments
- Material announcements

News must remain factual.

---

## NSE / BSE

Source identifiers:

`nse`

`bse`

Potential uses:

- Company identity
- Exchange information
- Corporate announcements
- Market information

---

# Browser Automation

Potential implementation:

- Playwright
- Chromium

Source identifier:

`browser_fallback`

Browser automation is a fallback capability.

Do not use browser automation simply because it is available.

Respect source access rules, rate limits, and applicable terms.

---

# Source Priority

Technical data:

`kite → moneycontrol → browser_fallback`

Fundamentals/shareholding:

`screener → moneycontrol → browser_fallback`

News:

`economic_times → moneycontrol`

If falling back, record the reason in the ResearchResult.

---

# Data Handling

Important values should capture:

- value
- status
- source
- retrieval timestamp
- underlying/as-of date
- notes for derivations or conversions

Contract:

`~/openclaw/stock-intelligence/schemas/research-result.v1.schema.json`

Schema:

`1.0`

---

# Secrets

Never store:

- API keys
- passwords
- Telegram tokens
- WhatsApp credentials
- session cookies
- authentication tokens

in this workspace.

---

# Future Integrations

Potential additions:

- structured market-data APIs
- NSE/BSE data feeds
- financial data providers
- news APIs
- browser automation

Document new sources before using them in production.
