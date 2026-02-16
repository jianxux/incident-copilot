"""AI Adapter — provides the same interfaces, delegating to the remote AI service.

When AI_SERVICE_URL is set, calls the proprietary AI service via HTTP.
Otherwise, returns stub responses.
"""

from __future__ import annotations

import enum
from typing import List, Optional

import structlog
from pydantic import BaseModel

from .client import ai_client

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Model stubs (so callers can import the types)
# ---------------------------------------------------------------------------

try:
    from enum import StrEnum as _StrEnum
except ImportError:

    class _StrEnum(str, enum.Enum):  # type: ignore[no-redef]
        pass


class MessageRole(_StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    role: MessageRole = MessageRole.USER
    content: str = ""
    timestamp: Optional[str] = None


class IncidentSession(BaseModel):
    incident_id: str = ""
    messages: List[ChatMessage] = []  # noqa: RUF012


class CompressedLogs(BaseModel):
    compressed: list = []  # noqa: RUF012
    total: int = 0
    kept: int = 0


class Verdict(BaseModel):
    verdict: str = ""
    confidence: float = 0
    suggested_actions: List[str] = []  # noqa: RUF012
    root_cause: str = ""


class ConfidenceLevel(_StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Adapter classes — delegate to AI service client
# ---------------------------------------------------------------------------


class LogSummarizer:
    """Drop-in replacement for ai.summarizer.LogSummarizer."""

    def __init__(self, settings=None):
        self._settings = settings

    async def summarize(
        self,
        logs,
        service_name=None,
        similar_incidents=None,
        **kwargs,
    ) -> str:
        log_dicts = [l if isinstance(l, dict) else {"message": str(l)} for l in logs]
        result = await ai_client.summarize_logs(log_dicts, similar_incidents)
        return result.get("summary", "")


class VerdictEngine:
    """Drop-in replacement for ai.verdict.VerdictEngine."""

    def __init__(self, settings=None):
        self._settings = settings

    async def generate_verdict(self, alert_data=None, deploys=None, log_summary="", metrics=None, similar_incidents=None, **kwargs):
        # Support both direct alert_data and individual fields from orchestrator
        if alert_data is None and kwargs:
            alert_data = {
                "title": kwargs.get("title", ""),
                "service_name": kwargs.get("service_name", ""),
                "severity": kwargs.get("severity", ""),
                "triggered_at": str(kwargs.get("triggered_at", "")),
            }
        if deploys is None and "recent_deploys" in kwargs:
            deploys = kwargs.get("recent_deploys")
        if log_summary == "" and isinstance(kwargs.get("log_summary"), dict):
            log_summary = str(kwargs.get("log_summary", ""))
        if metrics is None and "topology" in kwargs:
            metrics = kwargs.get("topology")
        return await ai_client.generate_verdict(
            alert_data=alert_data or {},
            deploys=deploys or [],
            log_summary=log_summary if isinstance(log_summary, str) else str(log_summary),
            metrics=metrics,
            similar_incidents=similar_incidents,
        )


class LogCompressor:
    """Drop-in replacement for ai.log_compressor.LogCompressor."""

    def __init__(self, *args, **kwargs):
        pass

    async def compress(self, logs, **kwargs):
        log_dicts = [l if isinstance(l, dict) else {"message": str(l)} for l in logs]
        result = await ai_client.compress_logs(log_dicts)
        return CompressedLogs(**result)

    def compress_sync(self, logs, **kwargs):
        return CompressedLogs(compressed=logs[:50], total=len(logs), kept=min(len(logs), 50))


class AICopilot:
    """Drop-in replacement for ai.copilot.AICopilot."""

    def __init__(self, settings=None):
        self._settings = settings
        self._sessions: dict = {}

    async def get_or_create_session(self, incident_id: str, context=None):
        if incident_id not in self._sessions:
            self._sessions[incident_id] = IncidentSession(incident_id=incident_id)
        return self._sessions[incident_id]

    async def chat(self, incident_id: str, message: str, context=None, **kwargs):
        result = await ai_client.chat(
            session_id=incident_id,
            message=message,
            context=context if isinstance(context, dict) else None,
        )
        msg = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=result.get("response", ""),
        )
        session = await self.get_or_create_session(incident_id)
        session.messages.append(msg)
        return msg

    async def generate_summary(self, incident_id: str) -> dict | None:
        summary = await ai_client.generate_summary(incident_id, {})
        return {"summary": summary}

    async def suggest_next_steps(self, incident_id: str) -> list[str]:
        return await ai_client.suggest_next_steps({})

    async def search_past_incidents(self, *args, **kwargs):
        return []
