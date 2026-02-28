"""Slack App Manifest generation for one-click app setup."""

import json
import urllib.parse


def generate_manifest(app_url: str) -> dict:
    """Generate a Slack App Manifest v2 for Incident Copilot.

    Args:
        app_url: Base URL of the deployment (e.g. "https://app.example.com").
                 Trailing slashes are stripped.

    Returns:
        A JSON-serializable dict representing the Slack App Manifest.
    """
    app_url = app_url.rstrip("/")

    return {
        "_metadata": {
            "major_version": 2,
            "minor_version": 0,
        },
        "display_information": {
            "name": "Incident Copilot",
            "description": "AI-powered incident management copilot",
            "long_description": (
                "Incident Copilot helps on-call engineers troubleshoot faster "
                "by auto-assembling context when alerts fire. It fetches logs, "
                "metrics, and deployment history, then synthesizes an analysis "
                "with actionable recommendations — all within Slack."
            ),
            "background_color": "#e05a3a",
        },
        "features": {
            "app_home": {
                "home_tab_enabled": True,
                "messages_tab_enabled": True,
                "messages_tab_read_only_enabled": False,
            },
            "bot_user": {
                "display_name": "Incident Copilot",
                "always_online": True,
            },
            "slash_commands": [
                {
                    "command": "/incident",
                    "description": "Manage incidents",
                    "url": f"{app_url}/api/slack/commands",
                    "usage_hint": "[create|list|update|resolve]",
                    "should_escape": False,
                },
                {
                    "command": "/copilot",
                    "description": "Ask the AI copilot",
                    "url": f"{app_url}/api/slack/commands",
                    "usage_hint": "[question or service name]",
                    "should_escape": False,
                },
            ],
        },
        "oauth_config": {
            "redirect_urls": [
                f"{app_url}/api/integrations/oauth/slack/callback",
            ],
            "scopes": {
                "bot": [
                    "channels:manage",
                    "channels:join",
                    "channels:read",
                    "chat:write",
                    "chat:write.public",
                    "commands",
                    "im:history",
                    "im:read",
                    "im:write",
                    "users:read",
                    "users:read.email",
                    "reactions:write",
                    "files:write",
                ],
            },
        },
        "settings": {
            "event_subscriptions": {
                "request_url": f"{app_url}/api/slack/events",
                "bot_events": [
                    "message.channels",
                    "message.im",
                    "app_mention",
                    "member_joined_channel",
                ],
            },
            "interactivity": {
                "is_enabled": True,
                "request_url": f"{app_url}/api/slack/interactions",
            },
            "org_deploy_enabled": False,
            "socket_mode_enabled": False,
            "token_rotation_enabled": False,
        },
    }


def generate_manifest_url(app_url: str) -> str:
    """Return the Slack 'create from manifest' URL with encoded manifest JSON.

    Args:
        app_url: Base URL of the deployment.

    Returns:
        Full URL that opens Slack's app creation page with the manifest pre-filled.
    """
    manifest = generate_manifest(app_url)
    encoded = urllib.parse.quote(json.dumps(manifest, separators=(",", ":")))
    return f"https://api.slack.com/apps?new_app=1&manifest_json={encoded}"
