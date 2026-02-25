-- Fix Supabase Security Advisor errors:
-- 1. RLS Disabled on public.service_environments (re-enable + tenant policy)
-- 2. RLS Disabled on public.integration_tokens (re-enable + tenant policy)
-- 3. RLS Disabled on public.incident_memory (enable + service_role policy)
-- 4. Sensitive Columns Exposed on public.integration_tokens (revoke anon/authenticated access to token columns)

-- ==================== 1. service_environments ====================
-- Ensure RLS is enabled (idempotent)
ALTER TABLE public.service_environments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.service_environments FORCE ROW LEVEL SECURITY;

-- Tenant isolation for authenticated users
DROP POLICY IF EXISTS service_environments_tenant_isolation ON public.service_environments;
CREATE POLICY service_environments_tenant_isolation
  ON public.service_environments FOR ALL
  USING (
    auth.role() = 'service_role'
    OR EXISTS (
      SELECT 1 FROM public.services s
      WHERE s.id = service_environments.service_id
        AND s.tenant_id = public.current_tenant_id()
    )
  )
  WITH CHECK (
    auth.role() = 'service_role'
    OR EXISTS (
      SELECT 1 FROM public.services s
      WHERE s.id = service_environments.service_id
        AND s.tenant_id = public.current_tenant_id()
    )
  );

-- ==================== 2. integration_tokens ====================
-- Ensure RLS is enabled (idempotent)
ALTER TABLE public.integration_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.integration_tokens FORCE ROW LEVEL SECURITY;

-- Tenant isolation for authenticated users (read-only, no direct token access)
DROP POLICY IF EXISTS integration_tokens_tenant_isolation ON public.integration_tokens;
CREATE POLICY integration_tokens_tenant_isolation
  ON public.integration_tokens FOR SELECT
  USING (
    auth.role() = 'service_role'
    OR tenant_id = public.current_tenant_id()
  );

-- ==================== 3. incident_memory ====================
ALTER TABLE public.incident_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.incident_memory FORCE ROW LEVEL SECURITY;

-- incident_memory has no tenant_id — restrict to service_role only
DROP POLICY IF EXISTS incident_memory_service_role ON public.incident_memory;
CREATE POLICY incident_memory_service_role
  ON public.incident_memory FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- ==================== 4. Sensitive columns on integration_tokens ====================
-- Revoke direct column access from anon and authenticated roles.
-- The backend uses service_role which bypasses these grants.
REVOKE SELECT (access_token, refresh_token) ON public.integration_tokens FROM anon;
REVOKE SELECT (access_token, refresh_token) ON public.integration_tokens FROM authenticated;

-- Grant access only to non-sensitive columns for authenticated users
GRANT SELECT (id, tenant_id, provider, token_expiry, scopes, created_at, updated_at)
  ON public.integration_tokens TO authenticated;
