# Supabase Database Setup

## Overview

Incident Copilot can persist data to Supabase PostgreSQL instead of using in-memory storage. When `SUPABASE_DB_ENABLED=true`, the app writes incidents, context cards, postmortems, tags, and other entities to Supabase while maintaining the in-memory SSE fanout for real-time dashboard updates.

## Prerequisites

- A Supabase project (free tier works for development)
- Supabase URL, anon key, and service role key

## Environment Variables

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SUPABASE_DB_ENABLED=true
SUPABASE_AUTH_ENABLED=true  # optional, for auth
```

## Running Migrations

### Option 1: Supabase CLI (recommended)

```bash
# Install Supabase CLI
brew install supabase/tap/supabase

# Link to your project
supabase link --project-ref your-project-ref

# Run all migrations
supabase db push
```

### Option 2: SQL Editor

Run each migration file in order via the Supabase Dashboard SQL Editor:

1. `supabase/migrations/20250207000001_initial_schema.sql` — Core tables (tenants, users, sessions, incidents, context_cards, runbooks, integrations, audit_logs) + RLS
2. `supabase/migrations/20260213000002_incident_memory_phase1.sql` — Incident memory with pgvector
3. `supabase/migrations/20260214000001_incident_memory_phase4.sql` — Local embeddings & service correlations
4. `supabase/migrations/20260215000001_extended_schema.sql` — Extended tables (incident_events, postmortems, tags, services, on-call, costs, comments, insights) + RLS

### Option 3: Direct psql

```bash
# Get your database URL from Supabase Dashboard > Settings > Database
psql "postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres" \
  -f supabase/migrations/20250207000001_initial_schema.sql \
  -f supabase/migrations/20260213000002_incident_memory_phase1.sql \
  -f supabase/migrations/20260214000001_incident_memory_phase4.sql \
  -f supabase/migrations/20260215000001_extended_schema.sql
```

## Schema Overview

### Core Tables (initial migration)
| Table | Description |
|-------|-------------|
| `tenants` | Organizations/teams |
| `users` | Users within tenants |
| `sessions` | Auth sessions |
| `incidents` | Incident records |
| `context_cards` | AI-generated context |
| `runbooks` | Runbook library |
| `integrations` | Third-party configs |
| `audit_logs` | Audit trail |

### Extended Tables (this migration)
| Table | Description |
|-------|-------------|
| `incident_events` | Timeline events per incident |
| `postmortems` | Postmortem documents |
| `tags` | Incident categorization tags |
| `incident_tags` | Many-to-many incidents↔tags |
| `auto_tag_rules` | Automatic tagging rules |
| `services` | Service catalog |
| `service_dependencies` | Service dependency graph |
| `on_call_schedules` | On-call schedule configs |
| `on_call_persons` | Current on-call roster |
| `cost_entries` | Cost tracking per incident |
| `incident_comments` | Collaboration comments |
| `incident_watchers` | Incident watchers |
| `insights` | AI-detected patterns |

### Memory Tables (separate migrations)
| Table | Description |
|-------|-------------|
| `incident_memory` | Incident records with vector embeddings |
| `service_correlations` | Pairwise service correlation scores |

## Row Level Security (RLS)

All tables have RLS enabled with:
- **Service role bypass** — server-side operations via service role key have full access
- **Tenant isolation** — authenticated users can only see data in their own tenant
- **Insert/Update/Delete policies** — scoped to user's tenant

The `get_user_tenant_id()` helper function resolves the current user's tenant from `auth.uid()`.

## Architecture

```
Routes/Services
    │
    ├── supabase_db_enabled=True  → SupabaseDB (PostgREST API)
    │                                    │
    │                                    └── Supabase PostgreSQL
    │
    └── supabase_db_enabled=False → In-memory stores (dicts/lists)
```

The `SupabaseIncidentStore` adapter inherits from the in-memory `IncidentStore` so SSE subscribers continue to work regardless of backend. DB writes happen alongside in-memory updates.

## Usage in Code

```python
from src.db import get_db, get_incident_store

# Direct DB access
db = get_db(use_admin=True)
incidents = await db.list_incidents(tenant_id="...")

# Store adapter (auto-selects backend)
store = get_incident_store(tenant_id="...")
await store.add_incident(...)
```
