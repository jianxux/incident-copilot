-- Fix Supabase Security Advisor errors:
-- 1. RLS Disabled on public.service_environments
-- 2. RLS Disabled on public.integration_tokens
-- 3. RLS Disabled on public.incident_memory
-- 4. Sensitive Columns Exposed on public.integration_tokens
--
-- All comparisons use ::text casts to avoid type mismatches between
-- text and uuid columns in the live database.

-- Ensure helper function exists
CREATE OR REPLACE FUNCTION public.current_tenant_id()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT tenant_id FROM public.profiles WHERE id::text = auth.uid()::text;
$$;

-- ==================== 1. service_environments ====================
ALTER TABLE public.service_environments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.service_environments FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS service_environments_tenant_isolation ON public.service_environments;
CREATE POLICY service_environments_tenant_isolation
  ON public.service_environments FOR ALL
  USING (
    auth.role() = 'service_role'
    OR EXISTS (
      SELECT 1 FROM public.services s
      WHERE s.id::text = service_environments.service_id::text
        AND s.tenant_id::text = public.current_tenant_id()::text
    )
  )
  WITH CHECK (
    auth.role() = 'service_role'
    OR EXISTS (
      SELECT 1 FROM public.services s
      WHERE s.id::text = service_environments.service_id::text
        AND s.tenant_id::text = public.current_tenant_id()::text
    )
  );

-- ==================== 2. integration_tokens ====================
ALTER TABLE public.integration_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.integration_tokens FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS integration_tokens_tenant_isolation ON public.integration_tokens;
CREATE POLICY integration_tokens_tenant_isolation
  ON public.integration_tokens FOR SELECT
  USING (
    auth.role() = 'service_role'
    OR tenant_id::text = public.current_tenant_id()::text
  );

-- ==================== 3. incident_memory ====================
ALTER TABLE public.incident_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.incident_memory FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS incident_memory_service_role ON public.incident_memory;
CREATE POLICY incident_memory_service_role
  ON public.incident_memory FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- ==================== 4. Sensitive columns on integration_tokens ====================
REVOKE SELECT (access_token, refresh_token) ON public.integration_tokens FROM anon;
REVOKE SELECT (access_token, refresh_token) ON public.integration_tokens FROM authenticated;

GRANT SELECT (id, tenant_id, provider, token_expiry, scopes, created_at, updated_at)
  ON public.integration_tokens TO authenticated;
