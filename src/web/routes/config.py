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

    # Check OAuth token store (per-tenant) first, fall back to env vars
    async def is_connected(provider: str, env_fallback: bool = False) -> bool:
        """Check if a provider is connected via OAuth store or env var."""
        try:
            token_rec = await oauth_token_store.get_token(tenant_id, provider)
            if token_rec and token_rec.access_token:
                return True
        except Exception as e:
            logger.warning("config_page_token_check_failed", provider=provider, error=str(e))
        return env_fallback

    integrations = [
        {
            "name": "PagerDuty",
            "icon": "bell",
            "connected": await is_connected("pagerduty", bool(settings.pagerduty_api_key)),
            "description": "Alert ingestion and incident sync",
        },
        {
            "name": "GitHub",
            "icon": "code",
            "connected": await is_connected("github", bool(settings.github_token)),
            "description": "Recent deploys, commits, and PR context",
        },
        {
            "name": "Datadog",
            "icon": "chart",
            "connected": await is_connected("datadog", bool(settings.datadog_api_key and settings.datadog_app_key)),
            "description": "Logs, metrics, and APM traces",
        },
        {
            "name": "Slack",
            "icon": "chat",
            "connected": await is_connected("slack", bool(settings.slack_bot_token)),
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
            "connected": await is_connected("cloudwatch", bool(settings.aws_region)),
            "description": "AWS logs and metrics",
        },
    ]

    # Platform info
    db_status = "Supabase" if settings.supabase_db_enabled else "In-memory"
    auth_status = "Google OAuth" if settings.supabase_auth_enabled else "Demo mode"

    return templates.TemplateResponse(
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
