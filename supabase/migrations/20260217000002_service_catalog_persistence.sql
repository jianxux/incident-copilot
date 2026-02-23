-- Persistent topology and service catalog upgrade
-- Adds durable catalog metadata, environment footprints, and dependency metrics.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- -----------------------------------------------------------------------------
-- Services table enrichment
-- -----------------------------------------------------------------------------

ALTER TABLE IF EXISTS public.services
    ADD COLUMN IF NOT EXISTS service_key text,
    ADD COLUMN IF NOT EXISTS owner_email text,
    ADD COLUMN IF NOT EXISTS repo_url text,
    ADD COLUMN IF NOT EXISTS dashboard_url text,
    ADD COLUMN IF NOT EXISTS runbook_url text,
    ADD COLUMN IF NOT EXISTS health text DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS tags text[] NOT NULL DEFAULT '{}'::text[],
    ADD COLUMN IF NOT EXISTS critical_user_journey boolean NOT NULL DEFAULT false;

CREATE UNIQUE INDEX IF NOT EXISTS idx_services_tenant_service_key
    ON public.services(tenant_id, service_key)
    WHERE service_key IS NOT NULL;

-- -----------------------------------------------------------------------------
-- Service dependencies normalization + metrics
-- -----------------------------------------------------------------------------

ALTER TABLE IF EXISTS public.service_dependencies
    ADD COLUMN IF NOT EXISTS upstream_service_id uuid,
    ADD COLUMN IF NOT EXISTS downstream_service_id uuid,
    ADD COLUMN IF NOT EXISTS is_critical boolean NOT NULL DEFAULT false,
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_service_dependencies_tenant_up_down
    ON public.service_dependencies(tenant_id, upstream_service_id, downstream_service_id)
    WHERE upstream_service_id IS NOT NULL AND downstream_service_id IS NOT NULL;

-- -----------------------------------------------------------------------------
-- Service environments (environment/region/cluster/version footprint)
-- -----------------------------------------------------------------------------

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
CREATE INDEX IF NOT EXISTS idx_service_environments_env_region
    ON public.service_environments(environment, region);

ALTER TABLE public.service_environments ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'set_updated_at') THEN
    IF NOT EXISTS (
      SELECT 1 FROM pg_trigger WHERE tgname = 'trg_service_environments_updated_at'
    ) THEN
      CREATE TRIGGER trg_service_environments_updated_at
      BEFORE UPDATE ON public.service_environments
      FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    END IF;
  END IF;
END $$;

-- Service role unrestricted access for backend automation
DROP POLICY IF EXISTS service_environments_service_role ON public.service_environments;
CREATE POLICY service_environments_service_role
  ON public.service_environments
  FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- Tenant isolation policy (when helper exists)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'current_tenant_id') THEN
    BEGIN
      DROP POLICY IF EXISTS service_environments_tenant_isolation ON public.service_environments;
      CREATE POLICY service_environments_tenant_isolation
        ON public.service_environments
        FOR ALL
        USING (
          EXISTS (
            SELECT 1
            FROM public.services s
            WHERE s.id = service_environments.service_id
              AND s.tenant_id = public.current_tenant_id()
          )
        )
        WITH CHECK (
          EXISTS (
            SELECT 1
            FROM public.services s
            WHERE s.id = service_environments.service_id
              AND s.tenant_id = public.current_tenant_id()
          )
        );
    EXCEPTION WHEN undefined_function THEN
      -- Ignore if helper is not available in this deployment flavor.
      NULL;
    END;
  END IF;
END $$;
