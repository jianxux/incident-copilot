-- Incident Copilot - Core multi-tenant schema for Supabase Postgres
--
-- This migration adds first-class multi-tenant tables that integrate with Supabase Auth
-- (auth.users) and persist Incident Copilot entities.
--
-- Notes:
-- - We keep older tables (e.g., public.users) for backwards compatibility, but new code
--   should use public.profiles which is keyed by auth.users.id.
-- - Tenant isolation is enforced with RLS using the authenticated user's profile. 

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- -----------------------------------------------------------------------------
-- Helper functions
-- -----------------------------------------------------------------------------

-- Current tenant id for the authenticated user (from profiles)
CREATE OR REPLACE FUNCTION public.current_tenant_id()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT tenant_id FROM public.profiles WHERE id = auth.uid();
$$;

-- -----------------------------------------------------------------------------
-- Tenants
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.tenants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  slug text UNIQUE NOT NULL,
  plan text NOT NULL DEFAULT 'free' CHECK (plan IN ('free','starter','pro','enterprise')),
  stripe_customer_id text,
  stripe_subscription_id text,
  settings jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenants_slug ON public.tenants(slug);

-- -----------------------------------------------------------------------------
-- Profiles (links to auth.users)
-- -----------------------------------------------------------------------------

-- A profile represents an authenticated Supabase user within a single tenant.
CREATE TABLE IF NOT EXISTS public.profiles (
  id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  email text,
  name text,
  avatar_url text,
  role text NOT NULL DEFAULT 'member' CHECK (role IN ('owner','admin','member','viewer')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, email)
);

CREATE INDEX IF NOT EXISTS idx_profiles_tenant_id ON public.profiles(tenant_id);

-- -----------------------------------------------------------------------------
-- Services & dependencies
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.services (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  name text NOT NULL,
  description text,
  repo text,
  team text,
  criticality text DEFAULT 'unknown',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE INDEX IF NOT EXISTS idx_services_tenant_id ON public.services(tenant_id);

CREATE TABLE IF NOT EXISTS public.service_dependencies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  from_service_id uuid NOT NULL REFERENCES public.services(id) ON DELETE CASCADE,
  to_service_id uuid NOT NULL REFERENCES public.services(id) ON DELETE CASCADE,
  dependency_type text NOT NULL DEFAULT 'upstream' CHECK (dependency_type IN ('upstream','downstream')),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, from_service_id, to_service_id, dependency_type)
);

CREATE INDEX IF NOT EXISTS idx_service_dependencies_tenant_id ON public.service_dependencies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_service_dependencies_from ON public.service_dependencies(from_service_id);
CREATE INDEX IF NOT EXISTS idx_service_dependencies_to ON public.service_dependencies(to_service_id);

-- -----------------------------------------------------------------------------
-- On-call schedules
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.on_call_schedules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  service_id uuid REFERENCES public.services(id) ON DELETE SET NULL,
  provider text NOT NULL DEFAULT 'unknown', -- pagerduty | opsgenie | unknown
  external_schedule_id text,
  name text,
  schedule_url text,
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_active boolean NOT NULL DEFAULT true,
  last_fetched_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, provider, external_schedule_id)
);

CREATE INDEX IF NOT EXISTS idx_on_call_schedules_tenant_id ON public.on_call_schedules(tenant_id);

-- -----------------------------------------------------------------------------
-- Integration configs
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.integration_configs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  type text NOT NULL, -- pagerduty | slack | github | datadog | ...
  name text NOT NULL,
  config jsonb NOT NULL DEFAULT '{}'::jsonb, -- encrypted in app layer when needed
  is_active boolean NOT NULL DEFAULT true,
  last_synced_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, type, name)
);

CREATE INDEX IF NOT EXISTS idx_integration_configs_tenant_id ON public.integration_configs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_integration_configs_type ON public.integration_configs(type);

-- -----------------------------------------------------------------------------
-- Incidents (processing + record)
-- -----------------------------------------------------------------------------

-- Ensure incidents table exists and can represent the dashboard processing states.
CREATE TABLE IF NOT EXISTS public.incidents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  source text NOT NULL DEFAULT 'manual',
  title text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Backfill/upgrade columns if an older schema is present.
ALTER TABLE public.incidents ADD COLUMN IF NOT EXISTS source_id text;
ALTER TABLE public.incidents ADD COLUMN IF NOT EXISTS source_url text;
ALTER TABLE public.incidents ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE public.incidents ADD COLUMN IF NOT EXISTS service text;
ALTER TABLE public.incidents ADD COLUMN IF NOT EXISTS severity text NOT NULL DEFAULT 'medium';
ALTER TABLE public.incidents ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'processing';
ALTER TABLE public.incidents ADD COLUMN IF NOT EXISTS triggered_at timestamptz;
ALTER TABLE public.incidents ADD COLUMN IF NOT EXISTS processed_at timestamptz;
ALTER TABLE public.incidents ADD COLUMN IF NOT EXISTS error_message text;
ALTER TABLE public.incidents ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

-- Relax/expand any older status CHECK constraint.
ALTER TABLE public.incidents DROP CONSTRAINT IF EXISTS incidents_status_check;
ALTER TABLE public.incidents ADD CONSTRAINT incidents_status_check
  CHECK (status IN ('processing','completed','error','triggered','acknowledged','resolved'));

CREATE INDEX IF NOT EXISTS idx_incidents_tenant_id ON public.incidents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON public.incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_created_at ON public.incidents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_service ON public.incidents(service);

-- Timeline / event stream for incidents
CREATE TABLE IF NOT EXISTS public.incident_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  incident_id uuid NOT NULL REFERENCES public.incidents(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  message text,
  data jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_incident_events_incident_id ON public.incident_events(incident_id);
CREATE INDEX IF NOT EXISTS idx_incident_events_tenant_id ON public.incident_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_incident_events_created_at ON public.incident_events(created_at DESC);

-- Context cards (latest version linked to an incident)
CREATE TABLE IF NOT EXISTS public.context_cards (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id uuid NOT NULL REFERENCES public.incidents(id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  data jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.context_cards ADD COLUMN IF NOT EXISTS assembly_time_ms integer;

CREATE INDEX IF NOT EXISTS idx_context_cards_incident_id ON public.context_cards(incident_id);
CREATE INDEX IF NOT EXISTS idx_context_cards_tenant_id ON public.context_cards(tenant_id);

-- -----------------------------------------------------------------------------
-- updated_at trigger
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_tenants_updated_at') THEN
    CREATE TRIGGER trg_tenants_updated_at BEFORE UPDATE ON public.tenants
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_profiles_updated_at') THEN
    CREATE TRIGGER trg_profiles_updated_at BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_services_updated_at') THEN
    CREATE TRIGGER trg_services_updated_at BEFORE UPDATE ON public.services
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_on_call_schedules_updated_at') THEN
    CREATE TRIGGER trg_on_call_schedules_updated_at BEFORE UPDATE ON public.on_call_schedules
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_integration_configs_updated_at') THEN
    CREATE TRIGGER trg_integration_configs_updated_at BEFORE UPDATE ON public.integration_configs
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_incidents_updated_at') THEN
    CREATE TRIGGER trg_incidents_updated_at BEFORE UPDATE ON public.incidents
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
  END IF;
END $$;

-- -----------------------------------------------------------------------------
-- RLS policies
-- -----------------------------------------------------------------------------

ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.services ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.service_dependencies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.on_call_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.integration_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.incident_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.context_cards ENABLE ROW LEVEL SECURITY;

-- Service role: full access
DO $$
DECLARE
  t record;
BEGIN
  FOR t IN SELECT schemaname, tablename FROM pg_tables WHERE schemaname='public' AND tablename IN (
    'tenants','profiles','services','service_dependencies','on_call_schedules','integration_configs','incidents','incident_events','context_cards'
  )
  LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies p
      WHERE p.schemaname = 'public'
        AND p.tablename = t.tablename
        AND p.policyname = format('%s_service_role_all', t.tablename)
    ) THEN
      EXECUTE format('CREATE POLICY "%s_service_role_all" ON public.%I FOR ALL USING (auth.role() = ''service_role'') WITH CHECK (auth.role() = ''service_role'');', t.tablename, t.tablename);
    END IF;
  END LOOP;
END $$;

-- Tenants: users can read their tenant
CREATE POLICY tenants_select_own
  ON public.tenants FOR SELECT
  USING (id = public.current_tenant_id());

-- Profiles: users can read/update their own profile; tenant admins can read all profiles in tenant
CREATE POLICY profiles_select_tenant
  ON public.profiles FOR SELECT
  USING (tenant_id = public.current_tenant_id());

CREATE POLICY profiles_update_self
  ON public.profiles FOR UPDATE
  USING (id = auth.uid())
  WITH CHECK (id = auth.uid());

-- Generic tenant isolation for tenant-scoped tables
CREATE POLICY services_tenant_isolation
  ON public.services FOR ALL
  USING (tenant_id = public.current_tenant_id())
  WITH CHECK (tenant_id = public.current_tenant_id());

CREATE POLICY service_dependencies_tenant_isolation
  ON public.service_dependencies FOR ALL
  USING (tenant_id = public.current_tenant_id())
  WITH CHECK (tenant_id = public.current_tenant_id());

CREATE POLICY on_call_schedules_tenant_isolation
  ON public.on_call_schedules FOR ALL
  USING (tenant_id = public.current_tenant_id())
  WITH CHECK (tenant_id = public.current_tenant_id());

CREATE POLICY integration_configs_tenant_isolation
  ON public.integration_configs FOR ALL
  USING (tenant_id = public.current_tenant_id())
  WITH CHECK (tenant_id = public.current_tenant_id());

CREATE POLICY incidents_tenant_isolation
  ON public.incidents FOR ALL
  USING (tenant_id = public.current_tenant_id())
  WITH CHECK (tenant_id = public.current_tenant_id());

CREATE POLICY incident_events_tenant_isolation
  ON public.incident_events FOR ALL
  USING (tenant_id = public.current_tenant_id())
  WITH CHECK (tenant_id = public.current_tenant_id());

CREATE POLICY context_cards_tenant_isolation
  ON public.context_cards FOR ALL
  USING (tenant_id = public.current_tenant_id())
  WITH CHECK (tenant_id = public.current_tenant_id());
