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

from ..auth.service import auth_service
from ..config import Settings, get_settings
from ..db.supabase_db import get_db
from ..security import decrypt_json
from ..supabase_client import is_supabase_db_enabled
from .oauth_tokens import oauth_token_store

logger = structlog.get_logger()
_slack_team_to_tenant: dict[str, str] = {}
_SLACK_TEAM_ID_RE = re.compile(r"^T[A-Z0-9]+$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


def register_slack_team_mapping(team_id: str, tenant_id: str) -> None:
    """Cache Slack team_id -> app tenant_id mapping."""
    if not team_id or not tenant_id:
        return
    _slack_team_to_tenant[team_id] = tenant_id


def _looks_like_slack_team_id(value: str) -> bool:
    return bool(_SLACK_TEAM_ID_RE.match(value)) and not _looks_like_uuid(value)


def _looks_like_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))


async def _resolve_tenant_id_from_slack_team_id(team_id: str) -> str | None:
    cached = _slack_team_to_tenant.get(team_id)
    if cached:
        return cached

    if not is_supabase_db_enabled():
        return None

    try:
        rows = await get_db(use_admin=True).list_tenants_with_slack_integration()
    except Exception as e:
        logger.warning("slack_team_mapping_query_failed", team_id=team_id, error=str(e))
        return None

    for row in rows:
        tenant_id = row.get("id")
        if not tenant_id:
            continue
        integrations = row.get("integrations") or {}
        if not isinstance(integrations, dict):
            continue
        slack = integrations.get("slack") or {}
        if not isinstance(slack, dict):
            continue
        encrypted = slack.get("encrypted")
        if not encrypted:
            continue
        try:
            payload = decrypt_json(encrypted)
        except Exception:
            continue
        oauth = payload.get("oauth") if isinstance(payload, dict) else None
        team = oauth.get("team") if isinstance(oauth, dict) else None
        mapped_team_id = team.get("id") if isinstance(team, dict) else None
        if mapped_team_id and tenant_id:
            _slack_team_to_tenant[mapped_team_id] = tenant_id
        if mapped_team_id == team_id:
            return str(tenant_id)

    return None


async def get_slack_client(
    tenant_id: str | None, settings: Settings | None = None
) -> AsyncWebClient | None:
    """Resolve a Slack client using OAuth store first, env var fallback."""
    settings = settings or get_settings()
    token: str | None = None
    resolved_tenant_id = tenant_id

    if tenant_id:
        try:
            token = await oauth_token_store.get_access_token(tenant_id, "slack")
        except Exception as e:
            logger.warning("slack_oauth_token_lookup_failed", tenant_id=tenant_id, error=str(e))

    if not token and tenant_id and _looks_like_slack_team_id(tenant_id):
        mapped_tenant_id = await _resolve_tenant_id_from_slack_team_id(tenant_id)
        if mapped_tenant_id:
            resolved_tenant_id = mapped_tenant_id
            try:
                token = await oauth_token_store.get_access_token(mapped_tenant_id, "slack")
            except Exception as e:
                logger.warning(
                    "slack_oauth_token_lookup_failed",
                    tenant_id=mapped_tenant_id,
                    team_id=tenant_id,
                    error=str(e),
                )

    if not token and resolved_tenant_id:
        try:
            tenant = await auth_service.get_tenant(resolved_tenant_id)
            if tenant:
                encrypted = (tenant.integrations.get("slack") or {}).get("encrypted")
                if encrypted:
                    slack_integration = decrypt_json(encrypted)
                    oauth_data = slack_integration.get("oauth", {}) if isinstance(slack_integration, dict) else {}
                    token = oauth_data.get("bot_token")
                    team = oauth_data.get("team") if isinstance(oauth_data, dict) else None
                    mapped_team_id = team.get("id") if isinstance(team, dict) else None
                    if mapped_team_id:
                        register_slack_team_mapping(mapped_team_id, resolved_tenant_id)
        except Exception as e:
            logger.warning(
                "slack_tenant_integration_token_lookup_failed",
                tenant_id=resolved_tenant_id,
                error=str(e),
            )

    if not token:
        token = settings.slack_bot_token or None

    if not token:
        logger.warning("slack_no_token_available", tenant_id=tenant_id)
        return None

    logger.info(
        "slack_client_resolved",
        tenant_id=resolved_tenant_id or tenant_id,
        input_tenant_id=tenant_id,
        token_prefix=token[:10] + "...",
    )
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
) -> dict:
    """Create a dedicated Slack channel for an incident."""
    client = await get_slack_client(tenant_id)
    if not client:
        msg = "No Slack token available"
        logger.error("slack_channel_create_failed", error=msg)
        raise RuntimeError(msg)

    channel_name = sanitize_channel_name(short_id, service_name)

    try:
        resp = await client.conversations_create(name=channel_name)
        if not resp.get("ok"):
            error_msg = resp.get("error") or "unknown_error"
            logger.error("slack_channel_create_failed", error=error_msg, name=channel_name)
            raise RuntimeError(error_msg)

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

    except RuntimeError:
        raise
    except Exception as e:
        logger.error("slack_channel_create_error", error=str(e), name=channel_name)
        raise RuntimeError(str(e)) from e


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


def _severity_badge(severity: str) -> str:
    """Return emoji badge for severity level."""
    s = severity.upper()
    if s in ("P1", "SEV1", "CRITICAL"):
        return "🔴"
    if s in ("P2", "SEV2", "HIGH"):
        return "🟠"
    if s in ("P3", "SEV3", "MEDIUM", "WARNING"):
        return "🟡"
    return "🟢"


def build_incident_notification_blocks(
    incident_id: str,
    title: str,
    service: str,
    severity: str,
    triggered_at: str,
    summary: str | None = None,
    tenant_id: str | None = None,
) -> list[dict]:
    """Build Block Kit blocks for the shared-channel incident notification card."""
    badge = _severity_badge(severity)
    header_text = f"{badge} {severity.upper()} — {title}"

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header_text[:150], "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Service:* `{service}`"},
                {"type": "mrkdwn", "text": f"*Severity:* {badge} {severity.upper()}"},
                {"type": "mrkdwn", "text": f"*Incident:* `{incident_id[:12]}`"},
                {"type": "mrkdwn", "text": f"*Time:* {triggered_at}"},
            ],
        },
    ]

    if summary:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": summary[:500]},
            }
        )

    # War room button
    blocks.append(
        {
            "type": "actions",
            "block_id": f"warroom_actions:{incident_id[:12]}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🚨 Start War Room", "emoji": True},
                    "action_id": "start_warroom",
                    "value": json.dumps({"incident_id": incident_id, "service": service, "tenant_id": tenant_id}),
                    "style": "danger",
                },
            ],
        }
    )

    return blocks


async def post_incident_notification(
    tenant_id: str | None,
    channel: str,
    incident_id: str,
    title: str,
    service: str,
    severity: str,
    triggered_at: str,
    summary: str | None = None,
) -> dict | None:
    """Post an incident notification card to the shared incidents channel.

    Returns ``{'channel_id': str, 'ts': str}`` on success or ``None``.
    """
    client = await get_slack_client(tenant_id)
    if not client:
        return None

    blocks = build_incident_notification_blocks(
        incident_id=incident_id,
        title=title,
        service=service,
        severity=severity,
        triggered_at=triggered_at,
        summary=summary,
        tenant_id=tenant_id,
    )
    fallback = f"{_severity_badge(severity)} {severity.upper()} | {title} | {service}"

    try:
        resp = await client.chat_postMessage(
            channel=channel,
            text=fallback,
            blocks=blocks,
            unfurl_links=False,
        )
        ts = resp.get("ts")
        channel_id = resp.get("channel")
        logger.info(
            "slack_incident_notification_posted",
            channel=channel,
            channel_id=channel_id,
            ts=ts,
            incident_id=incident_id,
        )
        return {"channel_id": channel_id, "ts": ts}
    except Exception as e:
        logger.error("slack_incident_notification_failed", channel=channel, error=str(e))
        return None


async def create_warroom_from_notification(
    tenant_id: str | None,
    incident_id: str,
    service: str,
    original_channel_id: str | None = None,
    original_ts: str | None = None,
    context_blocks: list[dict] | None = None,
) -> dict:
    """Create a war room channel on demand and link it back.

    Returns ``{'channel_id': str, 'channel_name': str}``.
    """
    short_id = incident_id[:8]
    channel_info = await create_incident_channel(
        tenant_id=tenant_id,
        short_id=short_id,
        service_name=service,
        title=f"War room for {incident_id}",
    )
    warroom_id = channel_info["channel_id"]
    warroom_name = channel_info["channel_name"]
    client = await get_slack_client(tenant_id)

    if client:
        # Copy context card into war room
        if context_blocks:
            try:
                await client.chat_postMessage(
                    channel=warroom_id,
                    text=f"Incident context for {incident_id}",
                    blocks=context_blocks,
                    unfurl_links=False,
                )
            except Exception as e:
                logger.warning("slack_warroom_context_copy_failed", error=str(e))

        # Post link back to #incidents channel
        if original_channel_id and original_ts:
            try:
                await client.chat_postMessage(
                    channel=original_channel_id,
                    text=f"🏠 War room created: <#{warroom_id}|{warroom_name}>",
                    thread_ts=original_ts,
                    unfurl_links=False,
                )
            except Exception as e:
                logger.warning("slack_warroom_backlink_failed", error=str(e))

    logger.info(
        "slack_warroom_created",
        incident_id=incident_id,
        warroom_channel_id=warroom_id,
        warroom_name=warroom_name,
    )
    return {"channel_id": warroom_id, "channel_name": warroom_name}


async def post_update_to_incident(
    tenant_id: str | None,
    warroom_channel_id: str | None,
    incidents_channel_id: str | None,
    original_ts: str | None,
    text: str,
    blocks: list[dict] | None = None,
) -> bool:
    """Post an update to the war room or thread under the original notification."""
    client = await get_slack_client(tenant_id)
    if not client:
        return False

    target_channel = warroom_channel_id or incidents_channel_id
    if not target_channel:
        return False

    kwargs: dict = {
        "channel": target_channel,
        "text": text,
        "unfurl_links": False,
    }
    if blocks:
        kwargs["blocks"] = blocks
    # Thread under original message when posting to incidents channel (no war room)
    if not warroom_channel_id and original_ts:
        kwargs["thread_ts"] = original_ts

    try:
        await client.chat_postMessage(**kwargs)
        return True
    except Exception as e:
        logger.error("slack_update_post_failed", channel=target_channel, error=str(e))
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
