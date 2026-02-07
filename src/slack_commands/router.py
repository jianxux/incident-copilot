"""FastAPI routes for Slack slash commands."""

import hashlib
import hmac
import time
from urllib.parse import parse_qs

import structlog
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from ..config import get_settings
from .commands import CommandContext, command_handler

logger = structlog.get_logger()
router = APIRouter(prefix="/slack/commands", tags=["slack-commands"])


def verify_slack_signature(
    body: bytes, timestamp: str, signature: str, signing_secret: str
) -> bool:
    if not signing_secret:
        return True
    try:
        if abs(int(time.time()) - int(timestamp)) > 300:
            return False
    except (ValueError, TypeError):
        return False
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected_sig = (
        "v0="
        + hmac.new(signing_secret.encode(), sig_basestring.encode(), hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected_sig, signature)


@router.post("")
async def handle_slash_command(
    request: Request,
    x_slack_signature: str | None = Header(None, alias="X-Slack-Signature"),
    x_slack_request_timestamp: str | None = Header(None, alias="X-Slack-Request-Timestamp"),
):
    settings = get_settings()
    body = await request.body()
    if x_slack_signature and x_slack_request_timestamp:
        if not verify_slack_signature(
            body,
            x_slack_request_timestamp,
            x_slack_signature,
            settings.slack_signing_secret,
        ):
            raise HTTPException(status_code=401, detail="Invalid signature")
    elif settings.slack_signing_secret:
        raise HTTPException(status_code=401, detail="Missing signature headers")
    form_data = parse_qs(body.decode("utf-8"))
    ctx = CommandContext(
        user_id=form_data.get("user_id", [""])[0],
        channel_id=form_data.get("channel_id", [""])[0],
        team_id=form_data.get("team_id", [""])[0],
        command=form_data.get("command", [""])[0],
        text=form_data.get("text", [""])[0],
        response_url=form_data.get("response_url", [""])[0],
    )
    response = await command_handler.handle(ctx)
    return JSONResponse(content=response)


@router.get("/health")
async def health():
    return {"status": "healthy", "service": "slack-commands"}
