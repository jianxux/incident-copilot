"""Dashboard settings page route."""

import os

from fastapi import Request
from fastapi.responses import HTMLResponse

from ...config import get_settings
from .common import router, templates


@router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    """Settings page showing integration status and platform info."""
    settings = get_settings()

    integrations = [
        {
            "name": "PagerDuty",
            "icon": "bell",
            "connected": bool(settings.pagerduty_api_key),
            "description": "Alert ingestion and incident sync",
        },
        {
            "name": "GitHub",
            "icon": "code",
            "connected": bool(settings.github_token),
            "description": "Recent deploys, commits, and PR context",
        },
        {
            "name": "Datadog",
            "icon": "chart",
            "connected": bool(settings.datadog_api_key and settings.datadog_app_key),
            "description": "Logs, metrics, and APM traces",
        },
        {
            "name": "Slack",
            "icon": "chat",
            "connected": bool(settings.slack_bot_token),
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
            "connected": bool(settings.aws_region),
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
