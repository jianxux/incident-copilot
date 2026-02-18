-- Service catalog schema bootstrap for runtime initialization.
-- Mirrors supabase migration so local Postgres runs without migration tooling.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

ALTER TABLE IF EXISTS public.services
    ADD COLUMN IF NOT EXISTS service_key text,
    ADD COLUMN IF NOT EXISTS owner_email text,
    ADD COLUMN IF NOT EXISTS repo_url text,
    ADD COLUMN IF NOT EXISTS dashboard_url text,
    ADD COLUMN IF NOT EXISTS runbook_url text,
    ADD COLUMN IF NOT EXISTS health text DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS tags text[] DEFAULT '{}'::text[],
    ADD COLUMN IF NOT EXISTS critical_user_journey boolean DEFAULT false;

CREATE UNIQUE INDEX IF NOT EXISTS idx_services_tenant_service_key
    ON public.services(tenant_id, service_key)
    WHERE service_key IS NOT NULL;

ALTER TABLE IF EXISTS public.service_dependencies
    ADD COLUMN IF NOT EXISTS upstream_service_id uuid,
    ADD COLUMN IF NOT EXISTS downstream_service_id uuid,
    ADD COLUMN IF NOT EXISTS is_critical boolean DEFAULT false,
    ADD COLUMN IF NOT EXISTS latency_p99_ms double precision,
    ADD COLUMN IF NOT EXISTS error_rate double precision,
    ADD COLUMN IF NOT EXISTS requests_per_min double precision,
    ADD COLUMN IF NOT EXISTS health text DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS discovered_from text,
    ADD COLUMN IF NOT EXISTS discovered_at timestamptz DEFAULT now(),
    ADD COLUMN IF NOT EXISTS last_seen_at timestamptz DEFAULT now();

DO $$
BEGIN
  IF EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'service_dependencies' AND column_name = 'from_service_id'
  ) THEN
    EXECUTE '
      UPDATE public.service_dependencies
      SET upstream_service_id = COALESCE(upstream_service_id, from_service_id)
      WHERE upstream_service_id IS NULL
    ';
  END IF;

  IF EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'service_dependencies' AND column_name = 'to_service_id'
  ) THEN
    EXECUTE '
      UPDATE public.service_dependencies
      SET downstream_service_id = COALESCE(downstream_service_id, to_service_id)
      WHERE downstream_service_id IS NULL
    ';
  END IF;
END$$;

CREATE TABLE IF NOT EXISTS public.service_environments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id uuid NOT NULL REFERENCES public.services(id) ON DELETE CASCADE,
    environment text NOT NULL DEFAULT 'production',
    region text,
    cluster text,
    namespace text,
    version text,
    is_primary boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    last_seen_at timestamptz DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(service_id, environment, region, cluster, namespace)
);

CREATE INDEX IF NOT EXISTS idx_service_environments_service_id
    ON public.service_environments(service_id);

CREATE INDEX IF NOT EXISTS idx_service_dependencies_unique
    ON public.service_dependencies(tenant_id, upstream_service_id, downstream_service_id);
