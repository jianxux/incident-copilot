-- Fix Supabase Security Advisor errors:
-- 1. RLS Disabled in Public: service_environments
-- 2. RLS Disabled in Public: integration_tokens
-- 3. RLS Disabled in Public: incident_memory
-- 4. Sensitive Columns Exposed: integration_tokens (access_token, refresh_token)
--
-- Root cause: migrations may not have been applied, or RLS was enabled but
-- Supabase still flags tables without authenticated-user policies.
-- This migration is idempotent and ensures all fixes are applied.

-- ==================== 1. Enable RLS (idempotent) ====================

ALTER TABLE public.service_environments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.integration_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.incident_memory ENABLE ROW LEVEL SECURITY;

-- ==================== 2. RLS Policies ====================

-- service_environments: tenant isolation via parent service
DROP POLICY IF EXISTS service_environments_tenant_isolation ON public.service_environments;
CREATE POLICY service_environments_tenant_isolation
  ON public.service_environments FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.services s
      WHERE s.id = service_environments.service_id
        AND s.tenant_id = public.current_tenant_id()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.services s
      WHERE s.id = service_environments.service_id
        AND s.tenant_id = public.current_tenant_id()
    )
  );

-- service_environments: service role bypass
DROP POLICY IF EXISTS service_environments_service_role ON public.service_environments;
CREATE POLICY service_environments_service_role
  ON public.service_environments FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- integration_tokens: tenant isolation
DROP POLICY IF EXISTS integration_tokens_tenant_isolation ON public.integration_tokens;
CREATE POLICY integration_tokens_tenant_isolation
  ON public.integration_tokens FOR ALL
  USING (tenant_id = public.current_tenant_id())
  WITH CHECK (tenant_id = public.current_tenant_id());

-- integration_tokens: service role bypass
DROP POLICY IF EXISTS "Service role has full access to integration_tokens" ON public.integration_tokens;
CREATE POLICY "Service role has full access to integration_tokens"
  ON public.integration_tokens FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- incident_memory: restrict to service_role only (no tenant_id column exists,
-- and this table is only accessed by the AI backend, never directly by users).
-- Force-deny all authenticated user access via PostgREST.
DROP POLICY IF EXISTS incident_memory_service_role ON public.incident_memory;
CREATE POLICY incident_memory_service_role
  ON public.incident_memory FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- ==================== 3. Revoke sensitive column access ====================
-- Remove direct API access to token columns from anon/authenticated roles.
-- The service_role (used by the backend) retains full access.

REVOKE ALL ON public.integration_tokens FROM anon;
REVOKE ALL ON public.integration_tokens FROM authenticated;

-- Re-grant SELECT on non-sensitive columns only
GRANT SELECT (id, tenant_id, provider, token_expiry, scopes, created_at, updated_at)
  ON public.integration_tokens TO authenticated;

-- ==================== 4. Force RLS for table owners ====================
-- Ensures RLS applies even when accessed by the table owner role.

ALTER TABLE public.service_environments FORCE ROW LEVEL SECURITY;
ALTER TABLE public.integration_tokens FORCE ROW LEVEL SECURITY;
ALTER TABLE public.incident_memory FORCE ROW LEVEL SECURITY;
