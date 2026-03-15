"""Slack adapter routes for AI Copilot thread conversations."""

import hashlib
import hmac
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from urllib.parse import parse_qs

import structlog
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slack_sdk.web.async_client import AsyncWebClient

from ...api.copilot import get_copilot
from ...config import get_settings
from ..thread_registry import thread_registry

logger = structlog.get_logger()
router = APIRouter(prefix="/api/slack", tags=["slack-copilot"])


class SlackChallengeResponse(BaseModel):
    """Slack URL verification challenge response."""

    challenge: str


class SlackCommandResponse(BaseModel):
    """Slack slash command response payload."""

    response_type: str = "ephemeral"
    text: str


class IncidentRateLimiter:
    """Simple in-memory per-incident rate limiter."""

    def __init__(self, limit: int = 10, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, incident_id: str) -> bool:
        """Return True when the incident is below the configured rate limit."""
        now = time.time()
        cutoff = now - self.window_seconds
        incident_events = self._events[incident_id]

        while incident_events and incident_events[0] < cutoff:
            incident_events.popleft()

        if len(incident_events) >= self.limit:
            return False

        incident_events.append(now)
        return True


_rate_limiter = IncidentRateLimiter(limit=10, window_seconds=60)


def verify_slack_signature(
    body: bytes,
    timestamp: str | None,
    signature: str | None,
    signing_secret: str,
) -> bool:
    """Verify Slack request signature."""
    if not signing_secret:
        return True

    if not timestamp or not signature:
        return False

    try:
        if abs(int(time.time()) - int(timestamp)) > 300:
            return False
    except (TypeError, ValueError):
        return False

    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected_sig = (
        "v0="
        + hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected_sig, signature)


async def _get_slack_client(team_id: str | None = None) -> AsyncWebClient:
    """Create a Slack web client using OAuth store first, env var fallback."""
    from ...integrations.slack_lifecycle import get_slack_client

    settings = get_settings()
    client = await get_slack_client(team_id, settings)
    if client:
        return client
    # Ultimate fallback
    return AsyncWebClient(token=settings.slack_bot_token)


def _parse_slash_command(body: bytes) -> dict[str, str]:
    """Parse URL-encoded slash command payload."""
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}


async def _handle_thread_message(payload: dict) -> None:
    """Handle an incoming Slack thread message event."""
    event = payload.get("event", {})
    team_id = payload.get("team_id", "")
    channel_id = event.get("channel", "")
    thread_ts = event.get("thread_ts", "")
    text = (event.get("text") or "").strip()

    if not thread_ts:
        logger.debug("copilot_slack_event_ignored_no_thread")
        return

    if event.get("bot_id") or event.get("subtype") == "bot_message":
        logger.debug("copilot_slack_event_ignored_bot")
        return

    if not text:
        logger.debug("copilot_slack_event_ignored_empty_text")
        return

    incident_id = await thread_registry.get_incident_id(team_id, channel_id, thread_ts)
    if not incident_id:
        logger.debug(
            "copilot_slack_event_ignored_unmapped_thread",
            team_id=team_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
        )
        return

    if not _rate_limiter.allow(incident_id):
        logger.warning("copilot_slack_rate_limited", incident_id=incident_id)
        return

    copilot = get_copilot()
    response = await copilot.chat(incident_id=incident_id, user_message=text)

    client = await _get_slack_client(team_id)
    await client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts,
        text=response[:3500],
    )

    logger.info(
        "copilot_slack_thread_response_sent",
        incident_id=incident_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
    )


async def _handle_app_mention(payload: dict) -> None:
    """Handle an @app_mention event — works in channels and threads."""
    event = payload.get("event", {})
    team_id = payload.get("team_id", "")
    channel_id = event.get("channel", "")
    thread_ts = event.get("thread_ts") or event.get("ts", "")
    text = (event.get("text") or "").strip()

    if event.get("bot_id") or event.get("subtype") == "bot_message":
        logger.debug("copilot_slack_mention_ignored_bot")
        return

    if not text:
        logger.debug("copilot_slack_mention_ignored_empty_text")
        return

    # Strip the bot mention from the text (e.g. "<@U12345> summarize" → "summarize")
    import re as _re

    text = _re.sub(r"<@[A-Z0-9]+>\s*", "", text).strip()
    if not text:
        text = "help"

    # Try to find an incident context from thread registry
    incident_id = None
    if thread_ts:
        incident_id = await thread_registry.get_incident_id(
            team_id, channel_id, thread_ts
        )

    if incident_id:
        if not _rate_limiter.allow(incident_id):
            logger.warning(
                "copilot_slack_mention_rate_limited", incident_id=incident_id
            )
            return

        copilot = get_copilot()
        response = await copilot.chat(incident_id=incident_id, user_message=text)
    else:
        response = (
            "👋 I'm the Incident Copilot! Mention me in an incident thread to ask questions, "
            "or use `/copilot summary <incident_id>` to get a summary."
        )

    client = await _get_slack_client(team_id)
    await client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts,
        text=response[:3500],
    )

    logger.info(
        "copilot_slack_mention_response_sent",
        incident_id=incident_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
    )


@router.post("/events")
async def handle_slack_events(
    request: Request,
    x_slack_signature: str | None = Header(None, alias="X-Slack-Signature"),
    x_slack_request_timestamp: str | None = Header(
        None, alias="X-Slack-Request-Timestamp"
    ),
):
    """Handle Slack Events API callbacks for Copilot thread interactions."""
    body = await request.body()
    settings = get_settings()

    if not verify_slack_signature(
        body=body,
        timestamp=x_slack_request_timestamp,
        signature=x_slack_signature,
        signing_secret=settings.slack_signing_secret,
    ):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    payload = await request.json()
    event_type = payload.get("type")

    if event_type == "url_verification":
        challenge = payload.get("challenge", "")
        return SlackChallengeResponse(challenge=challenge)

    if event_type != "event_callback":
        return JSONResponse(content={"ok": True})

    event = payload.get("event", {})
    event_subtype = event.get("type")

    if event_subtype == "message":
        try:
            await _handle_thread_message(payload)
        except Exception as exc:
            logger.error("copilot_slack_message_error", error=str(exc))

    elif event_subtype == "app_mention":
        try:
            await _handle_app_mention(payload)
        except Exception as exc:
            logger.error("copilot_slack_app_mention_error", error=str(exc))

    return JSONResponse(content={"ok": True})


async def _resolve_incident_id_from_command(command: dict[str, str]) -> str | None:
    """Resolve target incident for slash command payload."""
    text = (command.get("text") or "").strip()
    parts = text.split()
    if len(parts) >= 2:
        return parts[1]

    team_id = command.get("team_id", "")
    channel_id = command.get("channel_id", "")
    thread_ts = command.get("thread_ts", "")
    if thread_ts:
        return await thread_registry.get_incident_id(team_id, channel_id, thread_ts)

    return None


def _command_action(text: str) -> str:
    """Extract slash command action token."""
    parts = text.strip().split()
    if not parts:
        return ""
    return parts[0].lower()


def _format_summary(summary: dict | None) -> str:
    """Format summary payload for Slack."""
    if not summary:
        return "Unable to generate a summary for this incident right now."

    title = summary.get("title") or "Incident Summary"
    summary_text = summary.get("summary") or "No summary available."
    root_cause = summary.get("root_cause") or "Unknown"
    resolution = summary.get("resolution") or "In progress"
    generated_at = datetime.now(UTC).strftime("%H:%M UTC")

    return (
        f"*{title}*\n"
        f"{summary_text}\n"
        f"*Root cause:* {root_cause}\n"
        f"*Resolution:* {resolution}\n"
        f"_Generated {generated_at}_"
    )


def _format_suggestions(suggestions: list[str]) -> str:
    """Format suggested next steps for Slack."""
    if not suggestions:
        return "No suggestions available yet."
    bullet_lines = "\n".join(f"• {item}" for item in suggestions[:5])
    return f"*Suggested next steps*\n{bullet_lines}"


@router.post("/commands")
async def handle_slack_commands(
    request: Request,
    x_slack_signature: str | None = Header(None, alias="X-Slack-Signature"),
    x_slack_request_timestamp: str | None = Header(
        None, alias="X-Slack-Request-Timestamp"
    ),
):
    """Handle /copilot slash commands."""
    body = await request.body()
    settings = get_settings()

    if not verify_slack_signature(
        body=body,
        timestamp=x_slack_request_timestamp,
        signature=x_slack_signature,
        signing_secret=settings.slack_signing_secret,
    ):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    command = _parse_slash_command(body)
    action = _command_action(command.get("text", ""))
    incident_id = await _resolve_incident_id_from_command(command)

    if action not in {"summary", "catchup", "suggest"}:
        return SlackCommandResponse(
            text="Use `/copilot summary <incident_id>`, `/copilot catchup <incident_id>`, or `/copilot suggest <incident_id>`."
        )

    if not incident_id:
        return SlackCommandResponse(
            text="No incident context found. Provide an incident ID, for example: `/copilot summary INC-123`."
        )

    copilot = get_copilot()
    session = copilot.get_session(incident_id)
    if not session:
        return SlackCommandResponse(
            text=f"No active copilot session for `{incident_id}`. Start by chatting in the incident thread."
        )

    if action in {"summary", "catchup"}:
        summary = await copilot.generate_summary(incident_id)
        return SlackCommandResponse(text=_format_summary(summary))

    suggestions = await copilot.suggest_next_steps(incident_id)
    return SlackCommandResponse(text=_format_suggestions(suggestions))


@router.post("/interactions")
async def handle_slack_interactions(
    request: Request,
    x_slack_signature: str | None = Header(None, alias="X-Slack-Signature"),
    x_slack_request_timestamp: str | None = Header(
        None, alias="X-Slack-Request-Timestamp"
    ),
):
    """Handle Slack interactive component payloads (button clicks, etc.)."""
    import json as _json
    from urllib.parse import parse_qs as _parse_qs

    from ...integrations.slack_interactions import handle_interaction
    from ...integrations.slack import SlackAdapter
    from ...memory.feedback import FeedbackStore

    body = await request.body()
    settings = get_settings()

    if not verify_slack_signature(
        body=body,
        timestamp=x_slack_request_timestamp,
        signature=x_slack_signature,
        signing_secret=settings.slack_signing_secret,
    ):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # Slack sends interaction payloads as URL-encoded form with a "payload" field
    parsed = _parse_qs(body.decode("utf-8"), keep_blank_values=True)
    payload_raw = parsed.get("payload", [""])[0]
    if not payload_raw:
        return JSONResponse(content={"ok": True})

    payload = _json.loads(payload_raw)

    # Try memory feedback handler first
    slack_adapter = SlackAdapter(settings)
    feedback_store = FeedbackStore()
    handled = await slack_adapter.handle_feedback_interaction(payload, feedback_store)
    if handled:
        return JSONResponse(content={"ok": True})

    # Route to general interaction handler
    result = await handle_interaction(payload)
    if result:
        return JSONResponse(content=result)

    return JSONResponse(content={"ok": True})
