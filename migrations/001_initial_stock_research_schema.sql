-- ==============================================================================
-- Migration: 001_initial_stock_research_schema.sql
-- Stock Intelligence Audit Persistence Schema (Supabase / PostgreSQL)
-- ==============================================================================
-- Safeguards:
-- 1. Append-only audit history for research snapshots and recommendations.
-- 2. Foreign keys use ON DELETE RESTRICT to protect audit history (NO CASCADE).
-- 3. Idempotent unique indexes to prevent duplicate records during retries.
-- 4. Native DEFAULT now() for timezone-safe UTC timestamps.
-- 5. Row Level Security (RLS) enabled for least-privilege private access.
-- 6. Database triggers enforcing append-only immutability (prohibiting UPDATE/DELETE).
-- ==============================================================================
-- Migration Rerun Behavior & Prerequisites:
-- - Existing tables: This migration assumes target tables do not already exist,
--   or that existing tables have definitions compatible with this migration.
--   CREATE TABLE IF NOT EXISTS does not modify or reconcile an existing table's
--   columns or data types.
-- - Indexes: CREATE INDEX IF NOT EXISTS avoids recreating an index with the same
--   name, but does not verify that its definition matches the intended index.
--   Existing indexes must be checked for structural compatibility.
-- - Triggers: The migration uses DROP TRIGGER IF EXISTS followed by CREATE TRIGGER,
--   so named triggers are safely recreated when the migration is rerun.
-- - Conflicting environments: Existing incompatible tables or database objects
--   require a separately reviewed ALTER migration or an explicit, approved
--   remediation plan. Do not automatically drop tables or data.
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Fast lookup by symbol and creation date for recommendation cache checks
CREATE INDEX IF NOT EXISTS idx_recommendations_symbol_created
    ON investment_recommendations (symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendations_action
    ON investment_recommendations (investment_action);

-- Idempotency: Prevent duplicate recommendation for the exact same research run and engine version
CREATE UNIQUE INDEX IF NOT EXISTS uq_recommendations_run_engine
    ON investment_recommendations (research_run_id, engine_version);


-- ==============================================================================
-- 3. Security & Access Control (Row Level Security)
-- ==============================================================================
-- Enable RLS on both audit tables.
-- When accessed via backend service_role key, RLS is bypassed.
-- When accessed via public/anon key, access is completely blocked by default.
ALTER TABLE research_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE investment_recommendations ENABLE ROW LEVEL SECURITY;

-- Explicitly revoke mutation privileges from public/anon and authenticated roles
REVOKE UPDATE, DELETE ON research_snapshots FROM anon, authenticated;
REVOKE UPDATE, DELETE ON investment_recommendations FROM anon, authenticated;


-- ==============================================================================
-- 4. Audit Immutability Enforcement (Append-Only Triggers)
-- ==============================================================================
-- Enforces append-only immutability against standard application and user queries.
-- Note: Superusers or database owners retain administrative capability to alter
-- or disable triggers if needed for authorized maintenance operations.
CREATE OR REPLACE FUNCTION prevent_audit_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit records are append-only. Mutation (UPDATE) or deletion (DELETE) is prohibited on table "%"', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_immutable_research_snapshots ON research_snapshots;
CREATE TRIGGER trg_immutable_research_snapshots
    BEFORE UPDATE OR DELETE ON research_snapshots
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_mutation();

DROP TRIGGER IF EXISTS trg_immutable_investment_recommendations ON investment_recommendations;
CREATE TRIGGER trg_immutable_investment_recommendations
    BEFORE UPDATE OR DELETE ON investment_recommendations
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_mutation();
