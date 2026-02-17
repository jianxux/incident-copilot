-- OAuth integration token storage

CREATE TABLE IF NOT EXISTS public.integration_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  provider text NOT NULL,
  access_token text NOT NULL,
  refresh_token text,
  token_expiry timestamptz,
  scopes jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_integration_tokens_tenant_provider
  ON public.integration_tokens(tenant_id, provider);

CREATE INDEX IF NOT EXISTS idx_integration_tokens_expiry
  ON public.integration_tokens(token_expiry);

ALTER TABLE public.integration_tokens ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'set_updated_at') THEN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_integration_tokens_updated_at') THEN
      CREATE TRIGGER trg_integration_tokens_updated_at
      BEFORE UPDATE ON public.integration_tokens
      FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    END IF;
  END IF;
END $$;

DROP POLICY IF EXISTS "Service role has full access to integration_tokens" ON public.integration_tokens;
CREATE POLICY "Service role has full access to integration_tokens"
  ON public.integration_tokens FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
