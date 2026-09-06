---
name: stock-research
description: Research Indian listed stocks using the deterministic research pipeline. Use when asked to research, investigate, or check fundamentals, technicals, valuation, institutional holdings, shareholding, or recent company news for an Indian equity such as TCS, INFY, RELIANCE, HDFCBANK, BHEL, or another listed stock.
metadata: {"openclaw":{"requires":{"bins":["python3"]}}}
---

# Stock Research Skill

## Purpose

Use this skill whenever the user asks for factual research on an Indian listed company or stock.

The deterministic research engine is:

interfaces/research_cli.py

Do not recreate research logic in the agent.

Do not manually substitute values from model memory when the deterministic research engine can retrieve the data.

The deterministic Python research engine is the source of truth for collected and normalized research evidence.

## Research command

Run from the stock-researcher workspace:

.venv-market/bin/python -m interfaces.research_cli SYMBOL

Example:

.venv-market/bin/python -m interfaces.research_cli TCS

The project virtual environment is required because the research engine has its Python dependencies installed there.

Before execution, verify that the expected interpreter exists:

test -x .venv-market/bin/python

If the interpreter is unavailable, report the execution failure rather than silently using system Python.

## Required workflow

1. Identify the requested stock symbol.

2. If the user provides a clear Indian listed company or symbol, normalize the symbol to uppercase.

3. If the company or symbol is ambiguous, do not silently choose one.

4. Verify that the deterministic research interface is available.

5. Verify that .venv-market/bin/python exists and is executable.

6. Run the deterministic research interface.

7. Capture the complete stdout JSON returned by interfaces.research_cli before summarization.

8. Treat the returned ResearchResult as the source of truth.

9. Check:
   - symbol
   - company_name
   - exchange
   - symbol_match_confidence
   - overall_status
   - errors
   - data_quality_summary

10. Preserve field statuses:
    - VERIFIED
    - DERIVED
    - UNAVAILABLE
    - STALE
    - CONFLICTING
    - FAILED

11. Do not invent missing values.

12. Do not replace unavailable values with model memory.

13. Do not silently rewrite or reconstruct the ResearchResult JSON.

14. Do not turn factual research into a BUY/SELL recommendation.

15. Stock Analyst owns final investment interpretation.

## ResearchResult handling

The ResearchResult contains:

- company identity
- fundamentals
- technicals
- institutional/shareholding data
- news
- provenance
- errors
- data-quality summary

Treat the returned ResearchResult as canonical evidence.

The complete stdout JSON returned by interfaces.research_cli must be captured before summarization.

Do not rely on a prose interpretation when the raw ResearchResult is available.

When downstream processing requires structured data, pass the canonical JSON payload rather than a rewritten version.

Retain the complete JSON evidence payload when handing the result to downstream agents.

Summarize only from the returned JSON.

## Failure handling

If the interface returns:

ok=false

report the returned error.

If the research command fails, times out, or returns invalid JSON:

1. Do not fabricate a ResearchResult.
2. Report the execution failure.
3. Preserve the command failure information.
4. Do not continue as if research succeeded.

If overall_status is PARTIAL, do not treat that alone as a pipeline failure.

Inspect:

- data_quality_summary
- errors
- individual field statuses

and explain what is unavailable, stale, conflicting, or failed.

## Provenance

Preserve:

- source
- source_url
- retrieved_at
- as_of_date

Never fabricate provenance.

Do not remove provenance when summarizing or passing evidence downstream.

## Data freshness

Distinguish between:

- research retrieval time
- underlying market-data date
- underlying fundamental-data date
- news publication date

Do not describe old as-of data as current simply because the research was retrieved today.

When presenting a value, use the underlying as-of date when available.

## Fundamentals

Use the deterministic pipeline for factual values including:

- P/E
- P/B
- ROCE
- ROE
- debt-to-equity
- 3-year sales growth
- 3-year profit growth
- market capitalization

Do not manually substitute unavailable fundamental values.

Only describe a value as derived when the ResearchResult marks it DERIVED.

Do not convert unavailable values into estimates unless a separate downstream analysis explicitly requests estimation.

## Technicals

Use the deterministic pipeline for:

- current market price
- 50 DMA
- 200 DMA
- price relative to DMA
- RSI
- volume
- average volume
- 52-week high
- 52-week low

Preserve DERIVED status for calculated indicators.

Do not replace missing technical values with remembered or externally assumed values.

## Institutional data

Use the deterministic pipeline for:

- promoter holding
- promoter holding change
- FII holding
- FII holding change
- DII holding
- DII holding change
- promoter pledge

Do not describe ownership changes as proof of buying or selling unless the underlying evidence explicitly supports that conclusion.

A change in reported ownership is evidence of a change in reported holdings, not by itself proof of the reason for that change.

## News

Use the deterministic news intelligence output.

Treat news as evidence, not recommendation.

Do not invent events from headlines.

Do not assume every headline has equal materiality or relevance.

Preserve:

- source
- source_url
- publication date
- retrieval date
- event classification
- materiality
- relevance

when those fields are available in the ResearchResult.

Do not present generic price-page content as a material company event unless the ResearchResult classifies it as such.

## Identity verification

Before presenting research as belonging to a company, verify:

- requested symbol
- returned symbol
- company name
- exchange
- symbol match confidence

If identity is ambiguous or confidence is insufficient, do not silently continue with a different company.

## Quality discipline

A PARTIAL ResearchResult can still be valid research.

Do not convert PARTIAL into FAILED unless the pipeline itself failed.

Explain which fields are:

- verified
- derived
- unavailable
- stale
- conflicting
- failed

The absence of a value is itself important research information and must not be hidden.

## Output discipline

Python owns:

- data collection
- normalization
- provenance
- validation
- schema compliance
- deterministic calculations

The Stock Researcher agent owns:

- understanding the user's request
- identifying the requested stock
- invoking the deterministic interface
- checking the returned ResearchResult
- explaining the evidence
- handing the complete ResearchResult to downstream analysis

The agent must not recreate Python's data collection or calculation logic.

The agent must not modify the ResearchResult schema during a normal research request.

The agent must not fabricate missing financial, market, ownership, or news information.

The agent must not issue final investment recommendations.

## Downstream handoff

When handing research to Stock Analyst:

1. Preserve the complete ResearchResult JSON.
2. Do not replace field values with prose interpretations.
3. Preserve all field statuses.
4. Preserve provenance.
5. Preserve errors and data-quality information.
6. Clearly distinguish retrieved facts from derived values.
7. Do not add BUY/SELL decisions to the ResearchResult.

Stock Analyst is responsible for higher-level interpretation and investment analysis.

## Example

User asks:

Research TCS

Run:

.venv-market/bin/python -m interfaces.research_cli TCS

Then:

1. Capture the complete JSON.
2. Validate that the returned symbol and company identity match the request.
3. Inspect overall_status.
4. Inspect data_quality_summary.
5. Inspect errors.
6. Review the fundamental, technical, institutional, and news evidence.
7. Return a factual research response based only on the ResearchResult.

For downstream Stock Analyst processing, preserve the complete ResearchResult JSON.
