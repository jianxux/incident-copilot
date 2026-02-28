"""Slack incident channel lifecycle management.

Handles channel creation, context card posting/updating, suggested actions,
status updates, and channel archival for incident response.
"""

from __future__ import annotations

import asyncio
import json
import re

import structlog
from slack_sdk.web.async_client import AsyncWebClient

from ..config import Settings, get_settings
from .oauth_tokens import oauth_token_store

logger = structlog.get_logger()


async def get_slack_client(
    tenant_id: str | None, settings: Settings | None = None
) -> AsyncWebClient | None:
    """Resolve a Slack client using OAuth store first, env var fallback."""
    settings = settings or get_settings()
    token: str | None = None

    if tenant_id:
        try:
            token = await oauth_token_store.get_access_token(tenant_id, "slack")
        except Exception as e:
            logger.warning("slack_oauth_token_lookup_failed", tenant_id=tenant_id, error=str(e))

    if not token:
        token = settings.slack_bot_token or None

    if not token:
        logger.debug("slack_no_token_available", tenant_id=tenant_id)
        return None

    return AsyncWebClient(token=token)


def sanitize_channel_name(short_id: str, service_name: str) -> str:
    """Create a sanitized Slack channel name for an incident."""
    raw = f"inc-{short_id}-{service_name}"
    name = raw.lower()
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name)
    name = name.strip("-")
    return name[:80]


async def create_incident_channel(
    tenant_id: str | None,
    short_id: str,
    service_name: str,
    title: str,
    responder_slack_ids: list[str] | None = None,
) -> dict | None:
    """Create a dedicated Slack channel for an incident."""
    client = await get_slack_client(tenant_id)
    if not client:
        return None

    channel_name = sanitize_channel_name(short_id, service_name)

    try:
        resp = await client.conversations_create(name=channel_name)
        if not resp.get("ok"):
            logger.error("slack_channel_create_failed", error=resp.get("error"), name=channel_name)
            return None

        channel_id = resp["channel"]["id"]
        logger.info("slack_channel_created", channel_id=channel_id, name=channel_name)

        # Set topic
        topic = title[:250]
        try:
            await client.conversations_setTopic(channel=channel_id, topic=topic)
        except Exception as e:
            logger.warning("slack_set_topic_failed", channel_id=channel_id, error=str(e))

        # Invite responders
        if responder_slack_ids:
            for user_id in responder_slack_ids:
                try:
                    await client.conversations_invite(channel=channel_id, users=user_id)
                except Exception as e:
                    logger.warning(
                        "slack_invite_failed",
                        channel_id=channel_id,
                        user_id=user_id,
                        error=str(e),
                    )

        return {"channel_id": channel_id, "channel_name": channel_name}

    except Exception as e:
        logger.error("slack_channel_create_error", error=str(e), name=channel_name)
        return None


async def post_context_card(
    tenant_id: str | None,
    channel_id: str,
    blocks: list[dict],
    fallback_text: str,
) -> str | None:
    """Post a context card message. Returns the message ts."""
    client = await get_slack_client(tenant_id)
    if not client:
        return None

    try:
        resp = await client.chat_postMessage(
            channel=channel_id,
            text=fallback_text,
            blocks=blocks,
            unfurl_links=False,
        )
        ts = resp.get("ts")
        logger.info("slack_context_card_posted", channel_id=channel_id, ts=ts)
        return ts
    except Exception as e:
        logger.error("slack_context_card_post_failed", channel_id=channel_id, error=str(e))
        return None


async def update_context_card(
    tenant_id: str | None,
    channel_id: str,
    ts: str,
    blocks: list[dict],
    fallback_text: str,
) -> bool:
    """Update an existing context card message in-place."""
    client = await get_slack_client(tenant_id)
    if not client:
        return False

    try:
        resp = await client.chat_update(
            channel=channel_id,
            ts=ts,
            text=fallback_text,
            blocks=blocks,
        )
        ok = resp.get("ok", False)
        logger.info("slack_context_card_updated", channel_id=channel_id, ts=ts, ok=ok)
        return bool(ok)
    except Exception as e:
        logger.error("slack_context_card_update_failed", channel_id=channel_id, ts=ts, error=str(e))
        return False


async def post_suggested_actions(
    tenant_id: str | None,
    channel_id: str,
    actions: list,
    incident_id: str,
) -> str | None:
    """Post suggested actions as interactive Block Kit buttons."""
    client = await get_slack_client(tenant_id)
    if not client:
        return None

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "⚡ Suggested Actions", "emoji": True},
        }
    ]

    for action in actions:
        action_id = action.id
        value_payload = json.dumps({"action_id": action_id, "incident_id": incident_id})

        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(
            action.risk_level.value if hasattr(action.risk_level, "value") else str(action.risk_level),
            "⚪",
        )

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{risk_emoji} *{action.description}*\nRisk: {action.risk_level.value if hasattr(action.risk_level, 'value') else action.risk_level} | Requires approval: {'Yes' if action.requires_approval else 'No'}",
                },
            }
        )
        blocks.append(
            {
                "type": "actions",
                "block_id": f"action_buttons:{action_id}",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Approve", "emoji": True},
                        "action_id": f"action_approve:{action_id}",
                        "value": value_payload,
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Reject", "emoji": True},
                        "action_id": f"action_reject:{action_id}",
                        "value": value_payload,
                        "style": "danger",
                    },
                ],
            }
        )

    try:
        resp = await client.chat_postMessage(
            channel=channel_id,
            text="Suggested actions for incident",
            blocks=blocks,
            unfurl_links=False,
        )
        ts = resp.get("ts")
        logger.info("slack_suggested_actions_posted", channel_id=channel_id, incident_id=incident_id, ts=ts)
        return ts
    except Exception as e:
        logger.error("slack_suggested_actions_post_failed", channel_id=channel_id, error=str(e))
        return None


async def post_status_update(
    tenant_id: str | None,
    channel_id: str,
    status: str,
    message: str,
    incident_id: str = "",
    user: str | None = None,
) -> bool:
    """Post a status update to the incident channel."""
    client = await get_slack_client(tenant_id)
    if not client:
        return False

    status_emoji = {
        "acknowledged": "👀",
        "escalated": "🔺",
        "resolved": "✅",
    }.get(status.lower(), "ℹ️")

    user_str = f" by {user}" if user else ""
    text = f"{status_emoji} *Status: {status.upper()}*{user_str}\n{message}"

    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
    ]

    if status.lower() == "resolved" and incident_id:
        blocks.append(
            {
                "type": "actions",
                "block_id": f"resolution_actions:{incident_id}",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "📝 Generate Postmortem", "emoji": True},
                        "action_id": "generate_postmortem",
                        "value": incident_id,
                        "style": "primary",
                    }
                ],
            }
        )

    try:
        await client.chat_postMessage(
            channel=channel_id,
            text=f"Status update: {status}",
            blocks=blocks,
            unfurl_links=False,
        )
        logger.info("slack_status_update_posted", channel_id=channel_id, status=status)
        return True
    except Exception as e:
        logger.error("slack_status_update_failed", channel_id=channel_id, error=str(e))
        return False


async def archive_channel(tenant_id: str | None, channel_id: str) -> bool:
    """Archive a Slack channel."""
    client = await get_slack_client(tenant_id)
    if not client:
        return False

    try:
        resp = await client.conversations_archive(channel=channel_id)
        ok = resp.get("ok", False)
        logger.info("slack_channel_archived", channel_id=channel_id, ok=ok)
        return bool(ok)
    except Exception as e:
        logger.error("slack_channel_archive_failed", channel_id=channel_id, error=str(e))
        return False


async def schedule_archive(
    tenant_id: str | None, channel_id: str, delay_hours: int = 24
) -> None:
    """Schedule channel archival after a delay."""

    async def _delayed_archive():
        await asyncio.sleep(delay_hours * 3600)
        await archive_channel(tenant_id, channel_id)

    asyncio.create_task(_delayed_archive())
    logger.info(
        "slack_channel_archive_scheduled",
        channel_id=channel_id,
        delay_hours=delay_hours,
    )
