"""Webhook auto-registration and health monitoring.

Roadmap goal: after OAuth connects, automatically register required webhooks and
monitor them for health, self-healing if stale/broken.

Today we implement:
- PagerDuty webhook subscription registration (best-effort)
- A lightweight in-memory health monitor

In production:
- Persist health state (DB)
- Run periodic checks (Celery/cron/async scheduler)
- Support more providers (GitHub, etc.)
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from ..config import get_settings
from ..security import decrypt_json

logger = structlog.get_logger()


@dataclass
class WebhookHealth:
    provider: str
    tenant_id: str
    last_ok_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error: str | None = None


class WebhookManager:
    """Manages external webhook registrations for a tenant."""

    def __init__(self):
        self._health: dict[tuple[str, str], WebhookHealth] = {}

    def get_health(self, tenant_id: str) -> list[WebhookHealth]:
        """Return webhook health records for a tenant."""
        return [h for (tid, _provider), h in self._health.items() if tid == tenant_id]

    async def ensure_pagerduty_webhook(self, tenant_integrations: dict) -> dict:
        """Ensure a PagerDuty webhook subscription exists.

        Returns an updated (decrypted) integration record.
        """

        settings = get_settings()
        pd = tenant_integrations.get("pagerduty") or {}
        encrypted = pd.get("encrypted")
        if not encrypted:
            raise ValueError("PagerDuty integration not connected")

        record = decrypt_json(encrypted)
        oauth = (record.get("oauth") or {})
        access_token = oauth.get("access_token")
        if not access_token:
            raise ValueError("PagerDuty OAuth token missing")

        webhook = record.get("webhook") or {}
        subscription_id = webhook.get("subscription_id")

        if subscription_id:
            # Best-effort: assume ok; PagerDuty API to GET subscription exists,
            # but we avoid extra calls here.
            return record

        webhook_url = f"{settings.app_url}/webhooks/pagerduty"
        signing_secret = webhook.get("signing_secret") or secrets.token_urlsafe(32)

        subscription_id = await self._create_pagerduty_subscription(
            access_token=access_token,
            webhook_url=webhook_url,
            signing_secret=signing_secret,
        )

        record.setdefault("webhook", {})
        record["webhook"].update(
            {
                "url": webhook_url,
                "subscription_id": subscription_id,
                "signing_secret": signing_secret,
            }
        )
        return record

    async def _create_pagerduty_subscription(
        self, access_token: str, webhook_url: str, signing_secret: str
    ) -> str | None:
        api_url = "https://api.pagerduty.com/webhook_subscriptions"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Content-Type": "application/json",
        }
        payload = {
            "webhook_subscription": {
                "type": "webhook_subscription",
                "description": "Incident Copilot webhook subscription",
                "delivery_method": {
                    "type": "http_delivery_method",
                    "url": webhook_url,
                },
                "events": ["incident.triggered"],
                "filter": {"type": "account_reference"},
                "signing_secret": signing_secret,
            }
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(api_url, headers=headers, json=payload)
            if resp.status_code not in (200, 201):
                logger.error(
                    "pagerduty_webhook_create_failed",
                    status=resp.status_code,
                    body=resp.text,
                )
                return None

            data = resp.json()
            ws = data.get("webhook_subscription") or {}
            return ws.get("id")

    async def record_delivery_result(
        self,
        tenant_id: str,
        provider: str,
        ok: bool,
        error: str | None = None,
    ) -> None:
        key = (tenant_id, provider)
        health = self._health.get(key) or WebhookHealth(provider=provider, tenant_id=tenant_id)
        now = datetime.now(UTC)
        if ok:
            health.last_ok_at = now
            health.last_error = None
        else:
            health.last_error_at = now
            health.last_error = error
        self._health[key] = health

    def is_stale(self, tenant_id: str, provider: str, *, max_age: timedelta) -> bool:
        health = self._health.get((tenant_id, provider))
        if not health or not health.last_ok_at:
            return True
        return datetime.now(UTC) - health.last_ok_at > max_age


webhook_manager = WebhookManager()
