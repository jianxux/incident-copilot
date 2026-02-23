-- Incident Memory Phase 4 - local embeddings, correlations, and health support

-- Allow incident_memory embeddings to support provider-specific dimensions.
ALTER TABLE IF EXISTS incident_memory
    ALTER COLUMN embedding TYPE vector USING embedding::vector;

ALTER TABLE IF EXISTS incident_memory
    ADD COLUMN IF NOT EXISTS embedding_provider TEXT NOT NULL DEFAULT 'openai',
    ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER NOT NULL DEFAULT 1536;

DROP INDEX IF EXISTS idx_incident_memory_embedding;
-- ivfflat requires fixed dimensions; use HNSW which supports variable-dimension vectors,
-- or skip the index when the column has no fixed dimension constraint.
-- For local dev, we use a basic btree on the id instead and rely on sequential scan
-- for small datasets. Production should use pgvector with fixed dimensions.
CREATE INDEX IF NOT EXISTS idx_incident_memory_id_lookup
    ON incident_memory (id);

-- Materialized storage for pairwise service correlations.
CREATE TABLE IF NOT EXISTS service_correlations (
    service_a TEXT NOT NULL,
    service_b TEXT NOT NULL,
    co_incident_count INTEGER NOT NULL,
    service_a_incident_count INTEGER NOT NULL,
    service_b_incident_count INTEGER NOT NULL,
    correlation_score DOUBLE PRECISION NOT NULL,
    lookback_days INTEGER NOT NULL DEFAULT 90,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (service_a, service_b, lookback_days)
);

CREATE INDEX IF NOT EXISTS idx_service_correlations_score
    ON service_correlations (lookback_days, correlation_score DESC);

CREATE INDEX IF NOT EXISTS idx_service_correlations_updated_at
    ON service_correlations (updated_at DESC);

COMMENT ON TABLE service_correlations IS 'Phase 4 pairwise service correlation scores from incident memory';
