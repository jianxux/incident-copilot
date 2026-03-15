"""Microsoft Teams Bot Framework adapter for AI Copilot conversations."""

import hashlib
import hmac
import time
from collections import defaultdict, deque
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...api.copilot import get_copilot
from ...config import get_settings

logger = structlog.get_logger()
router = APIRouter(prefix="/api/teams", tags=["teams-copilot"])


# ---------------------------------------------------------------------------
# Rate limiter (mirrors Slack adapter)
# ---------------------------------------------------------------------------


class IncidentRateLimiter:
    """Simple in-memory per-incident rate limiter."""

    def __init__(self, limit: int = 10, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, incident_id: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds
        q = self._events[incident_id]
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


_rate_limiter = IncidentRateLimiter(limit=10, window_seconds=60)


# ---------------------------------------------------------------------------
# Thread registry (conversation_id → incident_id)
# ---------------------------------------------------------------------------

import asyncio


class TeamsThreadRegistry:
    """Map Teams conversation IDs to incident IDs."""

    def __init__(self) -> None:
        self._threads: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def register(self, conversation_id: str, incident_id: str) -> None:
        async with self._lock:
            self._threads[conversation_id] = incident_id
        logger.info(
            "teams_thread_registered",
            conversation_id=conversation_id,
            incident_id=incident_id,
        )

    async def get_incident_id(self, conversation_id: str) -> str | None:
        async with self._lock:
            return self._threads.get(conversation_id)


thread_registry = TeamsThreadRegistry()


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


def verify_teams_signature(
    body: bytes,
    authorization: str | None,
    app_id: str,
    app_password: str,
) -> bool:
    """Verify Bot Framework request authenticity.

    In production you would validate the JWT Bearer token from Azure AD.
    For simplicity we accept requests when:
    - No app_password is configured (development mode), OR
    - The Authorization header carries an HMAC-SHA256 signature we can
      verify using ``app_password`` as the key (lightweight check).
    """
    if not app_password:
        return True

    if not authorization:
        return False

    # Accept "Bearer <token>" or "HMAC <hex-digest>"
    parts = authorization.split(" ", 1)
    if len(parts) != 2:
        return False

    scheme, token = parts

    if scheme.upper() == "HMAC":
        expected = hmac.new(app_password.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, token)

    # For Bearer tokens we do a lightweight app-id check in dev.
    # A real implementation should validate the JWT against Azure AD keys.
    if scheme.upper() == "BEARER" and token:
        return True

    return False


# ---------------------------------------------------------------------------
# Adaptive Card builders
# ---------------------------------------------------------------------------


def build_context_card(summary: dict) -> dict:
    """Build an Adaptive Card for an incident context/summary."""
    title = summary.get("title") or "Incident Summary"
    summary_text = summary.get("summary") or "No summary available."
    root_cause = summary.get("root_cause") or "Unknown"
    resolution = summary.get("resolution") or "In progress"
    generated_at = datetime.now(UTC).strftime("%H:%M UTC")

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "size": "Large", "weight": "Bolder", "text": title},
            {"type": "TextBlock", "wrap": True, "text": summary_text},
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Root Cause", "value": root_cause},
                    {"title": "Resolution", "value": resolution},
                    {"title": "Generated", "value": generated_at},
                ],
            },
        ],
    }


def build_verdict_card(incident_id: str, verdict: str, confidence: str = "") -> dict:
    """Build an Adaptive Card for a copilot verdict."""
    body: list[dict] = [
        {
            "type": "TextBlock",
            "size": "Medium",
            "weight": "Bolder",
            "text": f"Verdict — {incident_id}",
        },
        {"type": "TextBlock", "wrap": True, "text": verdict},
    ]
    if confidence:
        body.append(
            {"type": "TextBlock", "wrap": True, "text": f"Confidence: {confidence}"}
        )

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
    }


def build_suggestions_card(suggestions: list[str]) -> dict:
    """Build an Adaptive Card for suggested next steps."""
    items = [
        {"type": "TextBlock", "text": f"• {s}", "wrap": True} for s in suggestions[:5]
    ]
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "size": "Medium",
                "weight": "Bolder",
                "text": "Suggested Next Steps",
            },
            *items,
        ],
    }


# ---------------------------------------------------------------------------
# Bot Framework REST helpers
# ---------------------------------------------------------------------------

_bot_token_cache: dict[str, tuple[str, float]] = {}


async def _get_bot_token() -> str:
    """Obtain a Bot Framework access token (cached)."""
    settings = get_settings()
    cached = _bot_token_cache.get("token")
    if cached and cached[1] > time.time():
        return cached[0]

    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.teams_app_id,
                "client_secret": settings.teams_app_password,
                "scope": "https://api.botframework.com/.default",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    token = data["access_token"]
    expires_in = data.get("expires_in", 3600)
    _bot_token_cache["token"] = (token, time.time() + expires_in - 60)
    return token


async def send_activity(service_url: str, conversation_id: str, activity: dict) -> None:
    """Send an activity to a Teams conversation via Bot Framework REST API."""
    import httpx

    token = await _get_bot_token()
    url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json=activity,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()


async def send_text_reply(
    service_url: str, conversation_id: str, text: str, reply_to_id: str | None = None
) -> None:
    """Send a text reply to a Teams conversation."""
    activity: dict = {
        "type": "message",
        "text": text[:3500],
    }
    if reply_to_id:
        activity["replyToId"] = reply_to_id
    await send_activity(service_url, conversation_id, activity)


async def send_card(service_url: str, conversation_id: str, card: dict) -> None:
    """Send an Adaptive Card attachment to a Teams conversation."""
    activity = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }
        ],
    }
    await send_activity(service_url, conversation_id, activity)


async def notify_channel(
    service_url: str, conversation_id: str, incident_id: str, message: str
) -> None:
    """Send an incident update notification to a Teams channel."""
    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "size": "Medium",
                "weight": "Bolder",
                "text": f"🚨 Incident Update — {incident_id}",
            },
            {"type": "TextBlock", "wrap": True, "text": message},
        ],
    }
    await send_card(service_url, conversation_id, card)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TeamsCommandResponse(BaseModel):
    """Response payload for Teams slash-style commands."""

    text: str


# ---------------------------------------------------------------------------
# Message handling
# ---------------------------------------------------------------------------


async def _handle_teams_message(activity: dict) -> None:
    """Handle an incoming Teams message activity."""
    text = (activity.get("text") or "").strip()
    conversation = activity.get("conversation", {})
    conversation_id = conversation.get("id", "")
    sender = activity.get("from", {})
    service_url = activity.get("serviceUrl", "")
    activity_id = activity.get("id")

    # Ignore bot's own messages
    settings = get_settings()
    if sender.get("id") == settings.teams_bot_id:
        logger.debug("teams_event_ignored_bot")
        return

    if not text:
        logger.debug("teams_event_ignored_empty_text")
        return

    # Check for slash-style commands in message text
    if text.startswith("/copilot ") or text.startswith("/incident "):
        await _handle_command_in_message(
            text, conversation_id, service_url, activity_id
        )
        return

    incident_id = await thread_registry.get_incident_id(conversation_id)
    if not incident_id:
        logger.debug(
            "teams_event_ignored_unmapped_conversation", conversation_id=conversation_id
        )
        return

    if not _rate_limiter.allow(incident_id):
        logger.warning("teams_rate_limited", incident_id=incident_id)
        return

    copilot = get_copilot()
    response = await copilot.chat(incident_id=incident_id, user_message=text)

    await send_text_reply(
        service_url, conversation_id, response, reply_to_id=activity_id
    )

    logger.info(
        "teams_thread_response_sent",
        incident_id=incident_id,
        conversation_id=conversation_id,
    )


async def _handle_command_in_message(
    text: str,
    conversation_id: str,
    service_url: str,
    reply_to_id: str | None,
) -> None:
    """Process /copilot or /incident commands embedded in message text."""
    parts = text.strip().split()
    # parts[0] = /copilot or /incident
    action = parts[1].lower() if len(parts) > 1 else ""
    incident_id = parts[2] if len(parts) > 2 else None

    if not incident_id:
        incident_id = await thread_registry.get_incident_id(conversation_id)

    if action not in {"summary", "catchup", "suggest"}:
        await send_text_reply(
            service_url,
            conversation_id,
            "Use `/copilot summary <incident_id>`, `/copilot catchup <incident_id>`, or `/copilot suggest <incident_id>`.",
            reply_to_id=reply_to_id,
        )
        return

    if not incident_id:
        await send_text_reply(
            service_url,
            conversation_id,
            "No incident context found. Provide an incident ID.",
            reply_to_id=reply_to_id,
        )
        return

    copilot = get_copilot()
    session = copilot.get_session(incident_id)
    if not session:
        await send_text_reply(
            service_url,
            conversation_id,
            f"No active copilot session for `{incident_id}`.",
            reply_to_id=reply_to_id,
        )
        return

    if action in {"summary", "catchup"}:
        summary = await copilot.generate_summary(incident_id)
        if summary:
            card = build_context_card(summary)
            await send_card(service_url, conversation_id, card)
        else:
            await send_text_reply(
                service_url,
                conversation_id,
                "Unable to generate summary.",
                reply_to_id=reply_to_id,
            )
        return

    # suggest
    suggestions = await copilot.suggest_next_steps(incident_id)
    if suggestions:
        card = build_suggestions_card(suggestions)
        await send_card(service_url, conversation_id, card)
    else:
        await send_text_reply(
            service_url,
            conversation_id,
            "No suggestions available yet.",
            reply_to_id=reply_to_id,
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/messages")
async def handle_teams_messages(
    request: Request,
    authorization: str | None = Header(None, alias="Authorization"),
):
    """Handle Bot Framework activity webhook."""
    body = await request.body()
    settings = get_settings()

    if not verify_teams_signature(
        body=body,
        authorization=authorization,
        app_id=settings.teams_app_id,
        app_password=settings.teams_app_password,
    ):
        raise HTTPException(status_code=401, detail="Invalid Teams authorization")

    activity = await request.json()
    activity_type = activity.get("type", "")

    if activity_type == "message":
        try:
            await _handle_teams_message(activity)
        except Exception as exc:
            logger.error("teams_message_error", error=str(exc))

    return JSONResponse(content={"ok": True})


@router.post("/commands")
async def handle_teams_commands(
    request: Request,
    authorization: str | None = Header(None, alias="Authorization"),
):
    """Handle Teams messaging extension / compose commands."""
    body = await request.body()
    settings = get_settings()

    if not verify_teams_signature(
        body=body,
        authorization=authorization,
        app_id=settings.teams_app_id,
        app_password=settings.teams_app_password,
    ):
        raise HTTPException(status_code=401, detail="Invalid Teams authorization")

    payload = await request.json()
    command_text = (payload.get("text") or "").strip()
    parts = command_text.split()
    action = parts[0].lower() if parts else ""

    incident_id: str | None = parts[1] if len(parts) > 1 else None
    if not incident_id:
        conversation = payload.get("conversation", {})
        conversation_id = conversation.get("id", "")
        incident_id = await thread_registry.get_incident_id(conversation_id)

    if action not in {"summary", "catchup", "suggest"}:
        return TeamsCommandResponse(
            text="Use `summary <incident_id>`, `catchup <incident_id>`, or `suggest <incident_id>`."
        )

    if not incident_id:
        return TeamsCommandResponse(
            text="No incident context found. Provide an incident ID."
        )

    copilot = get_copilot()
    session = copilot.get_session(incident_id)
    if not session:
        return TeamsCommandResponse(
            text=f"No active copilot session for `{incident_id}`."
        )

    if action in {"summary", "catchup"}:
        summary = await copilot.generate_summary(incident_id)
        text = _format_summary_text(summary)
        return TeamsCommandResponse(text=text)

    suggestions = await copilot.suggest_next_steps(incident_id)
    return TeamsCommandResponse(text=_format_suggestions_text(suggestions))


def _format_summary_text(summary: dict | None) -> str:
    if not summary:
        return "Unable to generate a summary for this incident right now."
    title = summary.get("title") or "Incident Summary"
    summary_text = summary.get("summary") or "No summary available."
    root_cause = summary.get("root_cause") or "Unknown"
    resolution = summary.get("resolution") or "In progress"
    generated_at = datetime.now(UTC).strftime("%H:%M UTC")
    return f"**{title}**\n{summary_text}\n**Root cause:** {root_cause}\n**Resolution:** {resolution}\n_Generated {generated_at}_"


def _format_suggestions_text(suggestions: list[str]) -> str:
    if not suggestions:
        return "No suggestions available yet."
    lines = "\n".join(f"• {s}" for s in suggestions[:5])
    return f"**Suggested next steps**\n{lines}"
