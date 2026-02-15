# Supabase migrations

Incident Copilot stores Supabase migrations in `supabase/migrations/`.

## Apply migrations with Supabase CLI

Prereqs:
- Install `supabase` CLI: https://supabase.com/docs/guides/cli
- Logged in: `supabase login`

### 1) Link your project

From the repo root:

```bash
supabase link --project-ref <your_project_ref>
```

### 2) Push migrations

```bash
supabase db push
```

This applies all SQL files in `supabase/migrations/` in timestamp order.

## Apply migrations via Supabase Dashboard

If you prefer the UI:

1. Open **SQL Editor** in your Supabase project
2. Run the files in timestamp order from `supabase/migrations/`

## Notes on local development

You can also run a local Supabase stack (Docker-based) with the CLI. Once started,
`supabase db push` will apply migrations locally.

## Required env vars

To enable Supabase DB persistence in the app:

```bash
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_DB_ENABLED=true
```

If you also want Supabase Auth:

```bash
SUPABASE_AUTH_ENABLED=true
```
