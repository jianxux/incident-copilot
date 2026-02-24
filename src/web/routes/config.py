"""Configuration and settings routes."""

from fastapi import Request
from fastapi.responses import HTMLResponse

from ...config import get_settings
from .common import router, templates

@router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    """Configuration page showing API key status."""
    settings = get_settings()

    config_items = [
        {
            "name": "PagerDuty API Key",
            "value": settings.pagerduty_api_key,
            "env_var": "PAGERDUTY_API_KEY",
            "description": "Used to fetch incident details",
        },
        {
            "name": "PagerDuty Webhook Secret",
            "value": settings.pagerduty_webhook_secret,
            "env_var": "PAGERDUTY_WEBHOOK_SECRET",
            "description": "Validates webhook signatures",
        },
        {
            "name": "GitHub Token",
            "value": settings.github_token,
            "env_var": "GITHUB_TOKEN",
            "description": "Fetches recent deploys and commits",
        },
        {
            "name": "GitHub Organization",
            "value": settings.github_org,
            "env_var": "GITHUB_ORG",
            "description": "Organization for repo lookups",
            "show_full": True,
        },
        {
            "name": "Datadog API Key",
            "value": settings.datadog_api_key,
            "env_var": "DATADOG_API_KEY",
            "description": "Fetches logs and metrics",
        },
        {
            "name": "Datadog App Key",
            "value": settings.datadog_app_key,
            "env_var": "DATADOG_APP_KEY",
            "description": "Required for Datadog API access",
        },
        {
            "name": "Datadog Site",
            "value": settings.datadog_site,
            "env_var": "DATADOG_SITE",
            "description": "Datadog regional endpoint",
            "show_full": True,
        },
        {
            "name": "Slack Bot Token",
            "value": settings.slack_bot_token,
            "env_var": "SLACK_BOT_TOKEN",
            "description": "Posts context cards to Slack",
        },
        {
            "name": "Slack Default Channel",
            "value": settings.slack_default_channel,
            "env_var": "SLACK_DEFAULT_CHANNEL",
            "description": "Default channel for notifications",
            "show_full": True,
        },
        {
            "name": "Anthropic API Key",
            "value": settings.anthropic_api_key,
            "env_var": "ANTHROPIC_API_KEY",
            "description": "AI-powered log summarization",
        },
        {
            "name": "AI Model",
            "value": settings.ai_model,
            "env_var": "AI_MODEL",
            "description": "Claude model for analysis",
            "show_full": True,
        },
    ]

    return templates.TemplateResponse(
        "config.html",
        {
            "request": request,
            "config_items": config_items,
            "page_title": "Configuration",
        },
    )
