# Self-hosting

Incident Copilot is Docker-first and runs well on a VM, Kubernetes, or PaaS.

## Docker (recommended)

### Configure

- Create `.env` (see [Configuration](configuration.md))
- Ensure Postgres + Redis are available

### Run

```bash
docker compose up -d --build
```

### Reverse proxy

Expose the service publicly for webhooks:

- Nginx / Caddy / Traefik
- Set `APP_URL=https://incident.yourcompany.com`

!!! tip
    Webhooks require a stable HTTPS URL. For local testing, use a tunnel (ngrok / cloudflared).

## Railway

A common setup:

1. Create a new Railway project
2. Add a **PostgreSQL** plugin
3. Add a **Redis** plugin
4. Deploy the Docker image / GitHub repo

Set environment variables in Railway:

- `APP_URL` to your Railway public domain
- `DATABASE_URL` from the Postgres plugin
- `REDIS_URL` from the Redis plugin
- integration credentials (Slack, PagerDuty/Opsgenie, logs, AI)

### Notes

- Railway typically handles TLS termination for you.
- Ensure your webhook endpoints are reachable from PagerDuty/Opsgenie.

## Hardening checklist

- Rotate secrets regularly
- Use least-privilege tokens
- Set `SECRET_KEY` to a strong random value
- Restrict inbound webhooks by IP allowlists where possible
- Turn on audit logging (`AUDIT_ENABLED=true`)
