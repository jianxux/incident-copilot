# Installation (Python)

Run Incident Copilot directly on your machine (no Docker), useful for development.

## Prerequisites

- Python **3.11**
- PostgreSQL (or Supabase Postgres)
- Redis

## 1) Create a virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

## 2) Install dependencies

```bash
pip install -r requirements.txt
```

If the repo uses `pyproject.toml`, you can typically do:

```bash
pip install -e .
```

## 3) Configure `.env`

Incident Copilot uses **Pydantic Settings** and reads from `.env` by default.

Create `.env` in the repo root:

```bash
touch .env
```

At minimum, set:

```bash
SECRET_KEY=change-me-in-production
APP_URL=http://localhost:8000
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/incident_copilot
REDIS_URL=redis://localhost:6379/0
```

Then add your integrations (PagerDuty/Opsgenie, Slack, logs, AI). See:

- [Configuration](../configuration.md)

## 4) Run database + redis

Use Docker for just the backing services:

```bash
docker compose up -d postgres redis
```

## 5) Start the API

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

## 6) Sanity check

```bash
curl -s http://localhost:8000/health || true
```

---

## Common issues

### Asyncpg / Postgres connection errors

- Confirm `DATABASE_URL` points to a reachable Postgres instance.
- Confirm your database exists and credentials are correct.

### Slack signature verification failures

- Ensure `SLACK_SIGNING_SECRET` matches your Slack app's Signing Secret.
- Ensure your dev server receives the raw request body (reverse proxies can break this).
