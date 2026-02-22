"""WebSocket adapter for web-based Copilot chat."""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ...ai import AICopilot
from ...config import get_settings
from ...web.store import incident_store

logger = structlog.get_logger()
router = APIRouter(tags=["copilot-web"])

_web_copilot: AICopilot | None = None


class WebChatMessage(BaseModel):
    """Inbound WebSocket message from chat UI."""

    action: str = "chat"
    message: str = ""


def get_web_copilot() -> AICopilot:
    """Get or create singleton Copilot instance for web adapter."""
    global _web_copilot
    if _web_copilot is None:
        _web_copilot = AICopilot(get_settings())
    return _web_copilot


def _iso_now() -> str:
    """Return the current UTC timestamp as ISO-8601 string."""
    return datetime.now(UTC).isoformat()


async def _ensure_session(incident_id: str, copilot: AICopilot) -> None:
    """Ensure a Copilot session exists for the incident."""
    if copilot.get_session(incident_id):
        return

    incident = await incident_store.get_incident(incident_id)
    context_card = incident.context_card if incident else None
    context = None
    if context_card is not None:
        context = context_card.model_dump() if hasattr(context_card, "model_dump") else context_card
    session = await copilot.get_or_create_session(
        incident_id=incident_id,
        context=context,
    )
    if incident and incident.service_name:
        session.service_name = incident.service_name


@router.websocket("/ws/copilot/{incident_id}")
async def copilot_websocket(websocket: WebSocket, incident_id: str):
    """Real-time Copilot chat for the dashboard web UI."""
    await websocket.accept()
    copilot = get_web_copilot()

    try:
        await _ensure_session(incident_id, copilot)
        await websocket.send_json(
            {
                "type": "system",
                "message": "Connected to Copilot",
                "timestamp": _iso_now(),
            }
        )

        while True:
            payload = await websocket.receive_json()
            incoming = WebChatMessage.model_validate(payload)
            action = incoming.action.lower().strip()

            if action == "summary":
                summary = await copilot.generate_summary(incident_id)
                summary_text = (
                    summary.get("summary") if summary else "No summary available yet."
                )
                await websocket.send_json(
                    {
                        "type": "assistant",
                        "message": summary_text,
                        "timestamp": _iso_now(),
                    }
                )
                continue

            if action == "suggest":
                suggestions = await copilot.suggest_next_steps(incident_id)
                if suggestions:
                    text = "\n".join(f"- {item}" for item in suggestions)
                else:
                    text = "No suggestions available yet."
                await websocket.send_json(
                    {
                        "type": "assistant",
                        "message": text,
                        "timestamp": _iso_now(),
                    }
                )
                continue

            message = incoming.message.strip()
            if not message:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Message cannot be empty",
                        "timestamp": _iso_now(),
                    }
                )
                continue

            await websocket.send_json(
                {
                    "type": "assistant_typing",
                    "message": "Generating...",
                    "timestamp": _iso_now(),
                }
            )

            response = await copilot.chat(incident_id=incident_id, user_message=message)
            await websocket.send_json(
                {
                    "type": "assistant",
                    "message": response,
                    "timestamp": _iso_now(),
                }
            )

    except WebSocketDisconnect:
        logger.info("copilot_websocket_disconnected", incident_id=incident_id)
    except Exception as exc:
        logger.error(
            "copilot_websocket_error",
            incident_id=incident_id,
            error=str(exc),
        )
        await websocket.close(code=1011)
