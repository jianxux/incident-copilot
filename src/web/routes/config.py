"""Dashboard settings page route."""

import os

import structlog
from fastapi import Depends, Request
from fastapi.responses import HTMLResponse

from ...config import get_settings
from ...integrations.oauth_tokens import oauth_token_store
from .common import require_dashboard_auth, router, templates

logger = structlog.get_logger()


@router.get("/config", response_class=HTMLResponse)
async def config_page(
    request: Request,
    auth_data: dict[str, str] = Depends(require_dashboard_auth),
):
    """Settings page showing integration status and platform info."""
    settings = get_settings()
    tenant_id = auth_data.get("tenant_id", "default")

    # Collect connected providers from both stores (same logic as onboarding)
    connected_providers: set[str] = set()

    # 1. Check OAuth token store
    for p in ("pagerduty", "slack", "github", "datadog", "cloudwatch", "gitlab"):
        try:
            token_rec = await oauth_token_store.get_token(tenant_id, p)
            if token_rec and token_rec.access_token:
                connected_providers.add(p)
        except Exception as e:
            logger.debug("config_token_check_failed", provider=p, error=str(e))

    # 2. Check integration_configs table (some integrations stored here instead)
    try:
        from ...db.supabase_db import get_db

        db = get_db(use_admin=True)
        rows = (
            db.client.table("integration_configs")
            .select("type")
            .eq("tenant_id", tenant_id)
            .eq("is_active", True)
            .execute()
        )
        if rows.data:
            connected_providers.update(r["type"] for r in rows.data if r.get("type"))
    except Exception as e:
        logger.debug("config_integration_configs_check_failed", error=str(e))

    def is_connected(provider: str, env_fallback: bool = False) -> bool:
        return provider in connected_providers or env_fallback

    integrations = [
        {
            "name": "PagerDuty",
            "icon": "bell",
            "connected": is_connected("pagerduty", bool(settings.pagerduty_api_key)),
            "description": "Alert ingestion and incident sync",
        },
        {
            "name": "GitHub",
            "icon": "code",
            "connected": is_connected("github", bool(settings.github_token)),
            "description": "Recent deploys, commits, and PR context",
        },
        {
            "name": "Datadog",
            "icon": "chart",
            "connected": is_connected(
                "datadog", bool(settings.datadog_api_key and settings.datadog_app_key)
            ),
            "description": "Logs, metrics, and APM traces",
        },
        {
            "name": "Slack",
            "icon": "chat",
            "connected": is_connected("slack", bool(settings.slack_bot_token)),
            "description": "Context card delivery and notifications",
        },
        {
            "name": "AI Engine",
            "icon": "sparkles",
            "connected": bool(os.environ.get("AI_SERVICE_URL")),
            "description": "AI-powered analysis and verdicts",
        },
        {
            "name": "CloudWatch",
            "icon": "cloud",
            "connected": is_connected("cloudwatch", bool(settings.aws_region)),
            "description": "AWS logs and metrics",
        },
    ]

    # Platform info
    db_status = "Supabase" if settings.supabase_db_enabled else "In-memory"
    auth_status = "Google OAuth" if settings.supabase_auth_enabled else "Demo mode"

    return templates.TemplateResponse(
        request,
        "config.html",
        {
            "request": request,
            "integrations": integrations,
            "version": "0.1.0",
            "db_status": db_status,
            "auth_status": auth_status,
            "page_title": "Settings",
        },
    )
