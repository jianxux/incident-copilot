# Supabase Setup Guide

This guide explains how to set up Supabase as the backend for Incident Copilot, including Google SSO authentication.

## Prerequisites

1. A Supabase account (free tier works for development)
2. Your Incident Copilot instance running

## Step 1: Create a Supabase Project

1. Go to [supabase.com](https://supabase.com) and sign in
2. Click "New Project"
3. Enter a name (e.g., "incident-copilot")
4. Choose a database password (save this!)
5. Select a region closest to your users
6. Click "Create new project"

## Step 2: Get Your API Keys

Once your project is created:

1. Go to **Project Settings** (gear icon) → **API**
2. Copy these values:
   - **Project URL** → `SUPABASE_URL`
   - **anon/public** key → `SUPABASE_ANON_KEY`
   - **service_role** key → `SUPABASE_SERVICE_ROLE_KEY`

## Step 3: Run Database Migrations

1. Go to **SQL Editor** in your Supabase dashboard
2. Open the migration file: `supabase/migrations/20250207000001_initial_schema.sql`
3. Copy the contents and paste into the SQL Editor
4. Click "Run" to execute the migration

This creates all required tables with Row Level Security (RLS) enabled.

## Step 4: Configure Google OAuth

To enable "Sign in with Google":

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select an existing one
3. Go to **APIs & Services** → **Credentials**
4. Click **Create Credentials** → **OAuth client ID**
5. Select "Web application"
6. Add authorized redirect URIs:
   ```
   https://YOUR_SUPABASE_PROJECT.supabase.co/auth/v1/callback
   ```
7. Copy the **Client ID** and **Client Secret**

Now configure Supabase:

1. In Supabase, go to **Authentication** → **Providers**
2. Find **Google** and click to enable
3. Paste your Client ID and Client Secret
4. Save

## Step 5: Configure Environment Variables

Add these to your `.env` file:

```bash
# Supabase Configuration
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Enable Supabase features
SUPABASE_AUTH_ENABLED=true
SUPABASE_DB_ENABLED=true

# Your app URL (for OAuth redirects)
APP_URL=http://localhost:8000
```

## Step 6: Test the Integration

1. Start your Incident Copilot server:
   ```bash
   cd incident-copilot
   source .venv/bin/activate
   uvicorn src.main:app --reload
   ```

2. Open http://localhost:8000/login
3. You should see "Continue with Google" button
4. Click it and sign in with your Google account

## Architecture

When Supabase is enabled:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│  FastAPI    │────▶│  Supabase   │
│             │     │  Backend    │     │  (Auth+DB)  │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Google     │
                    │  OAuth      │
                    └─────────────┘
```

### Authentication Flow

1. User clicks "Sign in with Google"
2. Redirected to `/api/auth/supabase/oauth/google`
3. Supabase redirects to Google OAuth
4. User authenticates with Google
5. Google redirects back to Supabase
6. Supabase creates/updates user and session
7. Supabase redirects to your app with tokens
8. App stores tokens and redirects to dashboard

### Database Operations

When `SUPABASE_DB_ENABLED=true`:

- All CRUD operations use Supabase's PostgREST API
- Row Level Security enforces tenant isolation
- Real-time subscriptions available (not yet implemented)

## Security Notes

1. **Never expose `SUPABASE_SERVICE_ROLE_KEY`** - it bypasses RLS
2. Use the service role key only for server-side operations
3. The anon key is safe for client-side use (RLS protects data)
4. All tables have RLS enabled by default

## Troubleshooting

### "Supabase Auth is not enabled"

Make sure `SUPABASE_AUTH_ENABLED=true` in your `.env` file.

### "OAuth provider not configured"

Check that you've enabled Google in Supabase Authentication → Providers.

### "Invalid redirect URI"

Ensure your Google OAuth credentials include the exact redirect URI:
```
https://YOUR_PROJECT_ID.supabase.co/auth/v1/callback
```

### Database connection errors

1. Check your `SUPABASE_URL` is correct
2. Verify your API keys are valid
3. Ensure RLS policies allow the operation

## Optional: Direct Database Connection

For advanced use cases, you can connect directly to PostgreSQL:

1. Go to **Project Settings** → **Database**
2. Copy the connection string
3. Use it as `DATABASE_URL` in your `.env`

Note: This bypasses Supabase's PostgREST API but still uses the same database.
