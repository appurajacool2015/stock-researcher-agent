-- ==============================================================================
-- Migration: 001_initial_stock_research_schema.sql
-- Stock Intelligence Audit Persistence Schema (Supabase / PostgreSQL)
-- ==============================================================================
-- Safeguards:
-- 1. Append-only audit history for research snapshots and recommendations.
-- 2. Foreign keys use ON DELETE RESTRICT to protect audit history (NO CASCADE).
-- 3. Idempotent unique indexes to prevent duplicate records during retries.
-- ==============================================================================

-- 1. Table: research_snapshots
-- Stores the complete canonical ResearchResult v1 payload and provenance.
CREATE TABLE IF NOT EXISTS research_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(10) NOT NULL DEFAULT 'NSE',
    company_name TEXT NOT NULL,
    research_timestamp TIMESTAMPTZ NOT NULL,
    market_data_as_of DATE,
    overall_status VARCHAR(20) NOT NULL,
    schema_version VARCHAR(20) NOT NULL DEFAULT '1.0',
    data_quality_summary JSONB NOT NULL,
    research_data JSONB NOT NULL,
    provenance JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Fast lookup by symbol and creation date for cache checks
CREATE INDEX IF NOT EXISTS idx_research_snapshots_symbol_created
    ON research_snapshots (symbol, created_at DESC);

-- Unique index to guarantee idempotency per research run ID and symbol
CREATE UNIQUE INDEX IF NOT EXISTS uq_research_snapshots_symbol_run
    ON research_snapshots (symbol, research_id);


-- 2. Table: investment_recommendations
-- Stores historical higher-level investment assessments linked to research snapshots.
CREATE TABLE IF NOT EXISTS investment_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_run_id UUID NOT NULL REFERENCES research_snapshots(id) ON DELETE RESTRICT,
    symbol VARCHAR(20) NOT NULL,
    assessment_timestamp TIMESTAMPTZ NOT NULL,
    market_data_as_of DATE,
    cmp NUMERIC(12, 2),
    currency VARCHAR(10) DEFAULT 'INR',
    technical_classification VARCHAR(30) NOT NULL,
    technical_score NUMERIC(5, 2),
    technical_confidence VARCHAR(20),
    investment_action VARCHAR(30) NOT NULL,
    investment_score NUMERIC(5, 2),
    investment_confidence NUMERIC(4, 2) NOT NULL,
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    positive_factors JSONB NOT NULL DEFAULT '[]'::jsonb,
    cautionary_factors JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    key_levels JSONB NOT NULL DEFAULT '{}'::jsonb,
    limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
    engine_version VARCHAR(20) NOT NULL,
    is_cached BOOLEAN NOT NULL DEFAULT FALSE,
    cache_metadata JSONB DEFAULT '{}'::jsonb,
    summary_explanation TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Fast lookup by symbol and creation date for recommendation cache checks
CREATE INDEX IF NOT EXISTS idx_recommendations_symbol_created
    ON investment_recommendations (symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendations_action
    ON investment_recommendations (investment_action);

-- Idempotency: Prevent duplicate recommendation for the exact same research run and engine version
CREATE UNIQUE INDEX IF NOT EXISTS uq_recommendations_run_engine
    ON investment_recommendations (research_run_id, engine_version);
