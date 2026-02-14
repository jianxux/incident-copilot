-- Incident Memory Phase 1 - Core Memory

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Core incident memory store with embeddings
CREATE TABLE IF NOT EXISTS incident_memory (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    duration_minutes INTEGER,
    severity TEXT,
    services_affected TEXT[] NOT NULL DEFAULT '{}',
    root_cause_category TEXT,
    root_cause_summary TEXT,
    error_signatures TEXT[] NOT NULL DEFAULT '{}',
    metric_anomalies TEXT[] NOT NULL DEFAULT '{}',
    deploy_involved BOOLEAN NOT NULL DEFAULT FALSE,
    deploy_sha TEXT,
    resolution_steps TEXT[] NOT NULL DEFAULT '{}',
    resolution_summary TEXT,
    time_to_diagnose_minutes INTEGER,
    time_to_fix_minutes INTEGER,
    was_rollback BOOLEAN,
    runbook_used TEXT,
    what_helped TEXT,
    what_was_missing TEXT,
    tags TEXT[] NOT NULL DEFAULT '{}',
    embedding vector(1536) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Vector index for ANN cosine similarity search
CREATE INDEX IF NOT EXISTS idx_incident_memory_embedding
    ON incident_memory USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Structured filter indexes
CREATE INDEX IF NOT EXISTS idx_incident_memory_services_affected
    ON incident_memory USING gin(services_affected);
CREATE INDEX IF NOT EXISTS idx_incident_memory_tags
    ON incident_memory USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_incident_memory_error_signatures
    ON incident_memory USING gin(error_signatures);

-- Time/severity lookup indexes
CREATE INDEX IF NOT EXISTS idx_incident_memory_created_at
    ON incident_memory(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incident_memory_severity
    ON incident_memory(severity);

COMMENT ON TABLE incident_memory IS 'Phase 1 incident memory records with semantic embeddings';
COMMENT ON COLUMN incident_memory.embedding IS 'text-embedding-3-small vector(1536) for recall';
