-- Add missing tenant columns expected by src/auth/models.py
-- Safe to run multiple times.

ALTER TABLE IF EXISTS public.tenants
    ADD COLUMN IF NOT EXISTS integrations JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE IF EXISTS public.tenants
    ADD COLUMN IF NOT EXISTS max_incidents_per_month INTEGER NOT NULL DEFAULT 50;

ALTER TABLE IF EXISTS public.tenants
    ADD COLUMN IF NOT EXISTS max_users INTEGER NOT NULL DEFAULT 5;

ALTER TABLE IF EXISTS public.tenants
    ADD COLUMN IF NOT EXISTS max_integrations INTEGER NOT NULL DEFAULT 3;

ALTER TABLE IF EXISTS public.tenants
    ADD COLUMN IF NOT EXISTS incidents_this_month INTEGER NOT NULL DEFAULT 0;

ALTER TABLE IF EXISTS public.tenants
    ADD COLUMN IF NOT EXISTS billing_cycle_start TIMESTAMPTZ NOT NULL DEFAULT NOW();
