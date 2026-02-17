# PagerDuty

Incident Copilot can receive PagerDuty incident events via webhook and (optionally) connect via OAuth for richer context.

## Webhook (Events → Incident Copilot)

### 1) Create a webhook in PagerDuty

1. PagerDuty → **Integrations** → **Generic Webhooks** (or Webhooks v3)
2. Create a webhook pointing to your public URL:

```
https://<your-app>/webhooks/pagerduty
```

3. Enable signing / secret (if available).

### 2) Configure environment variables

```bash
PAGERDUTY_WEBHOOK_SECRET=...
# Optional (API key for additional data fetches)
PAGERDUTY_API_KEY=...
```

!!! note
    Endpoint paths can differ by deployment. If your instance uses a different route, update the webhook target accordingly.

### 3) Test

Trigger a PagerDuty test incident and confirm a Slack/Teams context card arrives.

## OAuth (Connect PagerDuty)

If you want an in-app “Connect PagerDuty” flow, configure the OAuth client.

### 1) Create an OAuth app

In PagerDuty Developer Portal:

- Create an OAuth app
- Add redirect URL(s), e.g.:

```
https://<your-app>/auth/pagerduty/callback
```

### 2) Set env vars

```bash
PAGERDUTY_OAUTH_CLIENT_ID=...
PAGERDUTY_OAUTH_CLIENT_SECRET=...
APP_URL=https://<your-app>
```

### 3) Permissions

Grant minimum scopes required for reading incident details and on-call schedule information.

---

## Troubleshooting

- **401/403**: verify `PAGERDUTY_API_KEY` permissions.
- **Signature errors**: verify `PAGERDUTY_WEBHOOK_SECRET` and ensure requests are not being re-encoded by a proxy.
